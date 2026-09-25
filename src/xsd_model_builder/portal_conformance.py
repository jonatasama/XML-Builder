from __future__ import annotations

import argparse
import hashlib
import html.parser
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from .conformance import ConformanceReport, run_conformance
from .paths import project_root


class _SchemaLinkParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href and href.lower().endswith(".xsd"):
            self.links.append(href)


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "XsdXmlBuilder/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                return response.read()
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError(f"Download não concluído: {url}")


def _write_binary_if_changed(path: Path, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return digest


def _extract_zip(archive: Path, destination: Path) -> int:
    count = 0
    with zipfile.ZipFile(archive) as package:
        for member in package.infolist():
            name = member.filename.replace("\\", "/")
            path = Path(name)
            if member.is_dir():
                continue
            if path.is_absolute() or ".." in path.parts or ":" in name:
                raise ValueError(f"Caminho inseguro no ZIP {archive.name}: {name}")
            target = (destination / path).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError(f"Arquivo fora da pasta de destino: {name}")
            if not target.name.lower().endswith(".xsd"):
                continue
            _write_binary_if_changed(target, package.read(member))
            count += 1
    return count


def sync_packages(manifest: dict[str, object], destination: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for item in manifest["packages"]:
        model = item["model"]
        route = item["route"]
        filename = item["file"]
        url = (
            f"https://dfe-portal.svrs.rs.gov.br/{route}/DownloadArquivoEstatico/"
            f"?tipoArquivo=2&nomeArquivo={urllib.parse.quote(filename)}"
        )
        package_dir = destination / model / Path(filename).stem
        archive_path = destination / model / filename
        try:
            if archive_path.is_file():
                digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
            else:
                digest = _write_binary_if_changed(archive_path, _get(url))
            count = _extract_zip(archive_path, package_dir)
            if count == 0:
                raise ValueError("Pacote sem arquivos .xsd")
            supplements: list[dict[str, str]] = []
            for supplement in item.get("supplements", []):
                source_file = (
                    destination
                    / model
                    / Path(supplement["from_package"]).stem
                    / supplement["path"]
                )
                if not source_file.is_file():
                    raise FileNotFoundError(f"Dependência oficial ausente: {source_file}")
                _write_binary_if_changed(package_dir / supplement["target"], source_file.read_bytes())
                supplements.append(
                    {
                        "source_package": supplement["from_package"],
                        "source_file": str(source_file),
                        "target_file": str(package_dir / supplement["target"]),
                    }
                )
            result: dict[str, object] = {
                "model": model,
                "kind": "package",
                "source": url,
                "archive": str(archive_path),
                "folder": str(package_dir),
                "sha256": digest,
                "xsd_count": count,
                "supplements": supplements,
                "status": "downloaded",
            }
        except Exception as exc:
            result = {
                "model": model,
                "kind": "package",
                "source": url,
                "folder": str(package_dir),
                "status": "download_failed",
                "message": str(exc),
            }
        results.append(result)
        print(f"{model}: {filename}: {result['status']}", flush=True)
    return results


def sync_directories(manifest: dict[str, object], destination: Path) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    for item in manifest["operational_directories"]:
        model = item["model"]
        directory = item["path"]
        source = f"https://dfe-portal.svrs.rs.gov.br/Schemas/{directory}/"
        target_dir = destination / model / f"operational-{directory}"
        try:
            parser = _SchemaLinkParser()
            parser.feed(_get(source).decode("utf-8", errors="replace"))
            names: list[str] = []
            for href in parser.links:
                url = urllib.parse.urljoin(source, href)
                name = Path(urllib.parse.urlparse(url).path).name
                if name and name not in names:
                    names.append(name)
            def download_schema(name: str) -> None:
                target = target_dir / name
                if target.is_file():
                    return
                _write_binary_if_changed(target, _get(urllib.parse.urljoin(source, name)))

            with ThreadPoolExecutor(max_workers=12) as pool:
                futures = {pool.submit(download_schema, name): name for name in names}
                for future in as_completed(futures):
                    future.result()
            snapshot_digest = hashlib.sha256()
            for name in sorted(names):
                snapshot_digest.update(name.encode("utf-8"))
                snapshot_digest.update(hashlib.sha256((target_dir / name).read_bytes()).digest())
            result: dict[str, object] = {
                "model": model,
                "kind": "operational",
                "source": source,
                "folder": str(target_dir),
                "xsd_count": len(names),
                "sha256": snapshot_digest.hexdigest(),
                "roots": item["roots"],
                "status": "downloaded",
            }
        except Exception as exc:
            result = {
                "model": model,
                "kind": "operational",
                "source": source,
                "folder": str(target_dir),
                "status": "download_failed",
                "message": str(exc),
            }
        results.append(result)
        print(f"{model}: {directory}: {result['status']}", flush=True)
    return results


def _report_summary(report: ConformanceReport) -> dict[str, object]:
    failures = [
        {
            "schema": case.schema,
            "root": case.root,
            "mode": case.mode,
            "choice": case.choice,
            "message": case.message,
        }
        for case in report.cases
        if case.status == "failed"
    ]
    return {
        "schemas_found": report.schemas_found,
        "schemas_with_roots": report.schemas_with_roots,
        "passed": report.passed,
        "failed": report.failed,
        "skipped": report.skipped,
        "compatible": report.compatible,
        "failures": failures,
    }


def _write_markdown(output: Path, sources: list[dict[str, object]], manifest: dict[str, object]) -> None:
    lines = [
        "# Conformidade estrutural dos XSDs SVRS",
        "",
        f"Verificação: {datetime.now().astimezone().isoformat(timespec='seconds')}.",
        f"Fontes catalogadas no [portal SVRS]({manifest['portal']}) em {manifest['checked_on']}.",
        "",
        "A coluna OK indica geração e validação XSD dos casos mínimo, completo e das alternativas",
        "de `xs:choice` testadas. Regras fiscais externas ao XSD, assinatura e autorização",
        "pelo ambiente SEFAZ exigem testes específicos adicionais.",
        "",
        "Nos diretórios operacionais, as raízes testadas são as versões atuais listadas",
        "em `portal-svrs-sources.json`; arquivos antigos presentes no mesmo diretório não",
        "são contados como um único pacote de versão.",
        "",
        "| Família | Fonte | XSDs | Raízes testadas | Casos OK | Falhas | Situação |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for source in sources:
        conformance = source.get("conformance", {})
        name = Path(source["folder"]).name.replace("|", "\\|")
        label = f"[{name}]({source['source']})"
        status = (
            "Aprovado" if conformance.get("compatible")
            else "Download pendente" if source["status"] != "downloaded"
            else "Incompatível / inconclusivo"
        )
        lines.append(
            f"| {source['model']} | {label} | {source.get('xsd_count', '—')} "
            f"| {conformance.get('schemas_with_roots', '—')} "
            f"| {conformance.get('passed', '—')} | {conformance.get('failed', '—')} | {status} |"
        )
    lines.extend(["", "## Falhas e pendências", ""])
    found = False
    for source in sources:
        failures = source.get("conformance", {}).get("failures", [])
        if source["status"] == "downloaded" and not failures:
            continue
        found = True
        lines.append(f"### {source['model']}: {Path(source['folder']).name}")
        lines.append("")
        if source["status"] != "downloaded":
            lines.append(f"Download: {source.get('message', 'não concluído')}")
        for failure in failures[:12]:
            label = f"{failure.get('schema', '')} / {failure.get('root', '')}".strip(" / ")
            message = failure.get("message", "").replace("\n", " ")
            lines.append(f"- `{label}`: {message}")
        if len(failures) > 12:
            lines.append(f"- Mais {len(failures) - 12} falha(s) constam no relatório JSON.")
        lines.append("")
    if not found:
        lines.append("Nenhuma falha nos pacotes e diretórios testados.")
        lines.append("")
    lines.extend(["## Áreas do portal sem XSD de documento próprio publicado", ""])
    for item in manifest["no_document_schema"]:
        lines.append(f"- [{item['model']}](https://dfe-portal.svrs.rs.gov.br/{item['route']}/Documentos): {item['reason']}")
    lines.extend([
        "",
        "Observação: o menu do portal chama a nota de energia elétrica de **NF3e**. A grafia",
        "'NFPSe' da imagem foi tratada como referência a essa área do portal.",
        "",
        "Os ZIPs originais e seus hashes SHA-256 estão em `SVRS Oficiais` e",
        "`CONFORMIDADE-SVRS.json`. Quando um ZIP oficial omite um XSD necessário,",
        "a dependência usada de outro ZIP oficial fica registrada no relatório JSON.",
        "",
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="xsdxml-portal")
    parser.add_argument("--manifest", type=Path, default=project_root() / "portal-svrs-sources.json")
    parser.add_argument("--destination", type=Path, default=project_root() / "SVRS Oficiais")
    parser.add_argument("--report", type=Path, default=project_root() / "CONFORMIDADE-SVRS.json")
    parser.add_argument("--markdown", type=Path, default=project_root() / "CONFORMIDADE-SVRS.md")
    parser.add_argument("--sync", action="store_true", help="Baixa os XSDs publicados no portal.")
    parser.add_argument("--operational", action="store_true", help="Inclui os diretórios /Schemas/ operacionais.")
    parser.add_argument("--check", action="store_true", help="Executa a suíte nos pacotes baixados.")
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    destination = args.destination.resolve()
    index_path = destination / "_sources.json"
    if args.sync:
        sources = sync_packages(manifest, destination)
        if args.operational:
            sources.extend(sync_directories(manifest, destination))
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps(sources, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    elif index_path.is_file():
        sources = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        parser.error("Nenhum pacote sincronizado. Use --sync primeiro.")

    if args.check:
        for source in sources:
            if source["status"] != "downloaded":
                continue
            print(f"Verificando {source['model']}: {Path(source['folder']).name}", flush=True)
            try:
                report = run_conformance(
                    Path(source["folder"]),
                    schema_names=set(source["roots"]) if source["kind"] == "operational" else None,
                )
                source["conformance"] = _report_summary(report)
                print(f"  OK={report.passed} falhas={report.failed}", flush=True)
            except Exception as exc:
                source["conformance"] = {"compatible": False, "failed": 1, "failures": [{"message": str(exc)}]}
                print(f"  FALHA: {exc}", flush=True)

    output = {
        "portal": manifest["portal"],
        "manifest_checked_on": manifest["checked_on"],
        "sources": sources,
        "no_document_schema": manifest["no_document_schema"],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _write_markdown(args.markdown, sources, manifest)
    print(f"Relatório: {args.report.resolve()}")
    print(f"Resumo: {args.markdown.resolve()}")
    return 1 if any(
        source["status"] != "downloaded"
        or (args.check and not source.get("conformance", {}).get("compatible"))
        for source in sources
    ) else 0


if __name__ == "__main__":
    sys.exit(main())

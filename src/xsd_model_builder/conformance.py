from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from lxml import etree

from .generator import GenerationOptions, XsdModelGenerator
from .schema import XS, SchemaCandidate, XsdCatalog, discover_schemas


PARTICLE_NAMES = {"element", "sequence", "choice", "all", "group", "any"}


@dataclass(frozen=True)
class ConformanceCase:
    schema: str
    root: str
    mode: str
    choice: int
    status: str
    elements: int = 0
    attributes: int = 0
    warnings: int = 0
    message: str = ""


@dataclass
class ConformanceReport:
    folder: str
    generated_at: str
    schemas_found: int
    schemas_with_roots: int
    cases: list[ConformanceCase] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(case.status == "passed" for case in self.cases)

    @property
    def failed(self) -> int:
        return sum(case.status == "failed" for case in self.cases)

    @property
    def skipped(self) -> int:
        return sum(case.status == "skipped" for case in self.cases)

    @property
    def compatible(self) -> bool:
        return self.failed == 0 and self.passed > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "folder": self.folder,
            "generated_at": self.generated_at,
            "schemas_found": self.schemas_found,
            "schemas_with_roots": self.schemas_with_roots,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "compatible": self.compatible,
            "cases": [asdict(case) for case in self.cases],
        }

    def write_json(self, output: Path) -> None:
        output = output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def _choice_width(catalog: XsdCatalog) -> int:
    maximum = 1
    for document in catalog.documents.values():
        for choice in document.root.iterfind(f".//{XS}choice"):
            alternatives = [
                child
                for child in choice
                if isinstance(child.tag, str)
                and etree.QName(child).localname in PARTICLE_NAMES
                and child.get("maxOccurs", "1") != "0"
            ]
            maximum = max(maximum, len(alternatives))
    return maximum


def _root_declaration(catalog: XsdCatalog, root_name: str) -> etree._Element:
    matches = [qname for qname in catalog.root_elements() if qname[1] == root_name]
    if len(matches) != 1:
        raise ValueError(f"Raiz não unívoca: {root_name}")
    return catalog.get_element(matches[0])


def _case_variants(catalog: XsdCatalog) -> Iterable[tuple[str, int]]:
    yield "minimal", 0
    for choice_index in range(_choice_width(catalog)):
        yield "complete", choice_index


def run_conformance(
    folder: Path,
    *,
    repeat_count: int = 1,
    max_choice_variants: int = 100,
    schema_names: set[str] | None = None,
) -> ConformanceReport:
    """Gera e valida todas as raízes documentais alcançáveis na pasta informada."""

    folder = folder.resolve()
    candidates = discover_schemas(folder)
    rooted = [
        candidate for candidate in candidates
        if candidate.global_elements
        and (schema_names is None or candidate.path.name in schema_names)
    ]
    report = ConformanceReport(
        folder=str(folder),
        generated_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        schemas_found=len(candidates),
        schemas_with_roots=len(rooted),
    )
    if schema_names is not None:
        discovered = {candidate.path.name for candidate in rooted}
        for missing in sorted(schema_names - discovered):
            report.cases.append(
                ConformanceCase(
                    schema=missing,
                    root="",
                    mode="load",
                    choice=0,
                    status="failed",
                    message="XSD operacional solicitado não está disponível ou não declara raiz global.",
                )
            )

    for candidate in rooted:
        _run_candidate(
            report,
            candidate,
            repeat_count=repeat_count,
            max_choice_variants=max_choice_variants,
        )
    return report


def _run_candidate(
    report: ConformanceReport,
    candidate: SchemaCandidate,
    *,
    repeat_count: int,
    max_choice_variants: int,
) -> None:
    relative_schema = candidate.relative_path.replace("\\", "/")
    try:
        catalog = XsdCatalog(candidate.path)
    except Exception as exc:
        for root_name in candidate.global_elements:
            report.cases.append(
                ConformanceCase(
                    schema=relative_schema,
                    root=root_name,
                    mode="load",
                    choice=0,
                    status="failed",
                    message=str(exc),
                )
            )
        return

    variants = list(_case_variants(catalog))
    if len(variants) - 1 > max_choice_variants:
        variants = variants[: max_choice_variants + 1]

    for root_name in candidate.global_elements:
        declaration = _root_declaration(catalog, root_name)
        if declaration.get("abstract", "false") == "true":
            report.cases.append(
                ConformanceCase(
                    schema=relative_schema,
                    root=root_name,
                    mode="all",
                    choice=0,
                    status="skipped",
                    message="Elemento global abstrato; não pode ser raiz de uma instância XML.",
                )
            )
            continue

        for mode, choice_index in variants:
            try:
                result = XsdModelGenerator(
                    catalog,
                    GenerationOptions(
                        include_optional=mode == "complete",
                        repeat_count=repeat_count,
                        choice_index=choice_index,
                        validate=True,
                        pretty_print=False,
                    ),
                ).generate(root_name)
                report.cases.append(
                    ConformanceCase(
                        schema=relative_schema,
                        root=root_name,
                        mode=mode,
                        choice=choice_index + 1,
                        status="passed",
                        elements=sum(1 for _ in result.root.iter()),
                        attributes=sum(len(element.attrib) for element in result.root.iter()),
                        warnings=len(result.warnings),
                    )
                )
            except Exception as exc:
                report.cases.append(
                    ConformanceCase(
                        schema=relative_schema,
                        root=root_name,
                        mode=mode,
                        choice=choice_index + 1,
                        status="failed",
                        message=str(exc),
                    )
                )

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .conformance import run_conformance
from .errors import XsdModelError


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xsdxml-check",
        description="Gera e valida todas as raízes XML de um pacote de schemas XSD.",
    )
    parser.add_argument("folder", type=Path, help="Pasta a verificar recursivamente.")
    parser.add_argument("--report", type=Path, help="Relatório JSON de saída.")
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=1,
        help="Quantidade de ocorrências para partículas repetíveis (padrão: 1).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        report = run_conformance(args.folder, repeat_count=max(args.repeat_count, 1))
    except (XsdModelError, OSError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2

    if args.report:
        report.write_json(args.report)
        print(f"Relatório: {args.report.resolve()}")
    print(f"Pasta: {report.folder}")
    print(
        f"XSDs: {report.schemas_found}; com raízes: {report.schemas_with_roots}; "
        f"casos OK: {report.passed}; falhas: {report.failed}; ignorados: {report.skipped}"
    )
    for case in report.cases:
        if case.status == "failed":
            print(
                f"FALHA: {case.schema} :: {case.root} :: {case.mode} "
                f"choice {case.choice}\n{case.message}",
                file=sys.stderr,
            )
    return 0 if report.compatible else 1


if __name__ == "__main__":
    raise SystemExit(main())


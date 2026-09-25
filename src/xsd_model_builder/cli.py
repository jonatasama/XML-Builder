from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .errors import XsdModelError
from .generator import GenerationOptions, XsdModelGenerator
from .paths import suggested_output_path
from .schema import XsdCatalog, format_qname
from .validator import validate_xml


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xsdxml",
        description="Gera um modelo XML diretamente de um conjunto XSD.",
    )
    parser.add_argument("--schema", required=True, type=Path, help="Arquivo XSD raiz.")
    parser.add_argument("--root", help="Nome local do elemento XML raiz.")
    parser.add_argument("--namespace", help="Namespace do elemento raiz, se necessário.")
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "XML de saída (padrão: Modelos XML Gerados na raiz do projeto; "
            "no app macOS, em ~/Documents)."
        ),
    )
    parser.add_argument("--xml", type=Path, help="Valida um XML existente contra --schema.")
    parser.add_argument(
        "--mode",
        choices=("complete", "minimal"),
        default="complete",
        help="Completo inclui partículas opcionais; mínimo usa apenas as obrigatórias.",
    )
    parser.add_argument(
        "--repeat-count",
        type=int,
        default=1,
        help="Quantidade de exemplos para partículas repetíveis (padrão: 1).",
    )
    parser.add_argument(
        "--choice-index",
        type=int,
        default=1,
        help="Alternativa global de xs:choice, iniciando em 1 (padrão: 1).",
    )
    parser.add_argument("--no-validate", action="store_true", help="Não valida o XML gerado.")
    parser.add_argument("--compact", action="store_true", help="Grava o XML sem indentação.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.xml:
            qname = validate_xml(args.schema, args.xml)
            print(f"XML válido: {args.xml.resolve()}")
            print(f"Schema: {args.schema.resolve()}")
            print(f"Raiz: {format_qname(qname)}")
            return 0
        catalog = XsdCatalog(args.schema)
        roots = catalog.root_elements()
        if args.root:
            root_name = args.root
        elif len(roots) == 1:
            root_name = roots[0][1]
        else:
            available = ", ".join(format_qname(item) for item in roots) or "nenhum"
            raise XsdModelError(
                "Informe --root. Elementos globais disponíveis no schema raiz: " + available
            )

        options = GenerationOptions(
            include_optional=args.mode == "complete",
            repeat_count=args.repeat_count,
            choice_index=max(args.choice_index - 1, 0),
            validate=not args.no_validate,
            pretty_print=not args.compact,
        )
        result = XsdModelGenerator(catalog, options).generate(
            root_name,
            root_namespace=args.namespace,
        )
        output = (args.output or suggested_output_path(root_name)).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(result.xml_bytes(pretty_print=not args.compact))
        print(f"XML criado: {output}")
        print(f"Schema: {result.schema_path}")
        print(f"Raiz: {format_qname(result.root_qname)}")
        print(f"Validação XSD: {'OK' if result.validated else 'não executada'}")
        for warning in result.warnings:
            print(f"AVISO: {warning}", file=sys.stderr)
        return 0
    except (XsdModelError, ValueError) as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

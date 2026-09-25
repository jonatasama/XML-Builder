from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .access_key import prepare_access_key
from .errors import NFeAbiError
from .service import (
    build_document,
    default_schema_dir,
    load_json,
    load_xml,
    validate_existing_xml,
    write_result,
)


def _schema_dir(value: str | None) -> Path:
    return Path(value).resolve() if value else default_schema_dir().resolve()


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nfeabi",
        description="Monta, valida e assina XML da NF-e ABI v1.00.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    build = subparsers.add_parser("build", help="Monta uma NF-e ABI a partir de JSON.")
    build.add_argument("--input", required=True, type=Path, help="Arquivo JSON de entrada.")
    build.add_argument("--output", required=True, type=Path, help="XML que será criado.")
    build.add_argument("--schema-dir", help="Diretório do pacote PL_NFeABI_1.00.")
    mode = build.add_mutually_exclusive_group(required=True)
    mode.add_argument("--unsigned", action="store_true", help="Gera rascunho sem Signature.")
    mode.add_argument("--pfx", type=Path, help="Certificado PKCS#12/PFX com chave RSA.")
    build.add_argument(
        "--pfx-password-env",
        default="NFEABI_PFX_PASSWORD",
        help="Variável de ambiente com a senha do PFX.",
    )

    validate = subparsers.add_parser("validate", help="Valida XML existente.")
    validate.add_argument("--xml", required=True, type=Path)
    validate.add_argument("--schema-dir", help="Diretório do pacote PL_NFeABI_1.00.")
    validate.add_argument("--allow-unsigned", action="store_true")

    key = subparsers.add_parser("key", help="Calcula a chave de acesso do JSON.")
    key.add_argument("--input", required=True, type=Path)
    return parser


def _print_warnings(issues: list[object]) -> None:
    for issue in issues:
        if getattr(issue, "severity", None) == "warning":
            print(str(issue), file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    try:
        if args.command == "key":
            document = load_json(args.input)
            print(prepare_access_key(document))
            return 0

        if args.command == "build":
            schema_dir = _schema_dir(args.schema_dir)
            password = os.environ.get(args.pfx_password_env) if args.pfx else None
            result = build_document(
                load_json(args.input),
                schema_dir,
                pfx_path=args.pfx.resolve() if args.pfx else None,
                pfx_password=password,
            )
            write_result(result, args.output.resolve())
            _print_warnings(result.issues)
            state = "assinado" if result.signed else "rascunho sem assinatura"
            print(f"XML {state} criado: {args.output.resolve()}")
            print(f"Chave de acesso: {result.access_key}")
            return 0

        if args.command == "validate":
            access_key, issues, signed = validate_existing_xml(
                load_xml(args.xml),
                _schema_dir(args.schema_dir),
                allow_unsigned=args.allow_unsigned,
            )
            _print_warnings(issues)
            state = "com assinatura válida" if signed else "rascunho sem assinatura"
            print(f"XML válido ({state}).")
            print(f"Chave de acesso: {access_key}")
            return 0

    except NFeAbiError as exc:
        print(f"ERRO: {exc}", file=sys.stderr)
        return 2
    return 1


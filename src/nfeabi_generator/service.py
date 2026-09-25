from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from lxml import etree

from .access_key import prepare_access_key
from .builder import SchemaJsonBuilder, serialize_compact_xml
from .constants import XMLDSIG_NAMESPACE
from .errors import BusinessValidationError, InputError
from .rules import ValidationIssue, validate_business
from .schema import SchemaCatalog, SchemaValidator
from .signing import sign_xml, verify_xml_signature


@dataclass
class BuildResult:
    root: etree._Element
    access_key: str
    issues: list[ValidationIssue]
    signed: bool

    def xml_bytes(self) -> bytes:
        return serialize_compact_xml(self.root)


def default_schema_dir() -> Path:
    configured = os.environ.get("NFEABI_SCHEMA_DIR")
    if configured:
        return Path(configured)
    return (
        Path(__file__).resolve().parents[2]
        / "SVRS Oficiais"
        / "NFeABI"
        / "PL_NFeABI_1.00"
        / "PL_NFeABI_1.00"
    )


def load_json(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream, parse_float=Decimal)
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"Não foi possível ler {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise InputError("A raiz do arquivo JSON deve ser um objeto.")
    return value


def build_document(
    source: dict[str, object],
    schema_dir: Path,
    pfx_path: Path | None = None,
    pfx_password: str | None = None,
) -> BuildResult:
    data = copy.deepcopy(source)
    access_key = prepare_access_key(data)
    issues = validate_business(data, access_key)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        detail = "\n".join(str(issue) for issue in errors)
        raise BusinessValidationError(f"Falhas de negócio:\n{detail}")

    schema_path = schema_dir / "NFeABI_v1.00.xsd"
    catalog = SchemaCatalog(schema_path)
    builder = SchemaJsonBuilder(catalog)
    root_payload = data["NFeABI"]
    root = builder.build("NFeABI", root_payload)

    validator = SchemaValidator(schema_path)
    if pfx_path is None:
        validator.validate(root, allow_unsigned=True)
        signed = False
    else:
        sign_xml(root, pfx_path, pfx_password)
        validator.validate(root)
        verify_xml_signature(root)
        signed = True

    return BuildResult(root, access_key, issues, signed)


def write_result(result: BuildResult, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result.xml_bytes())


def load_xml(path: Path) -> etree._Element:
    parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
    try:
        return etree.parse(str(path), parser).getroot()
    except (OSError, etree.XMLSyntaxError) as exc:
        raise InputError(f"Não foi possível ler o XML {path}: {exc}") from exc


def validate_existing_xml(
    root: etree._Element,
    schema_dir: Path,
    allow_unsigned: bool = False,
) -> tuple[str, list[ValidationIssue], bool]:
    validator = SchemaValidator(schema_dir / "NFeABI_v1.00.xsd")
    validator.validate(root, allow_unsigned=allow_unsigned)

    has_signature = root.find(f"{{{XMLDSIG_NAMESPACE}}}Signature") is not None
    if has_signature:
        verify_xml_signature(root)
    elif not allow_unsigned:
        raise InputError("XML não assinado; use --allow-unsigned somente para rascunhos.")

    data = xml_to_document(root)
    access_key = prepare_access_key(data)
    issues = validate_business(data, access_key)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        detail = "\n".join(str(issue) for issue in errors)
        raise BusinessValidationError(f"Falhas de negócio:\n{detail}")
    return access_key, issues, has_signature


def xml_to_document(root: etree._Element) -> dict[str, object]:
    def convert(element: etree._Element) -> object:
        children = [child for child in element if isinstance(child.tag, str)]
        attributes = {"@" + name: value for name, value in element.attrib.items()}
        if not children:
            if attributes:
                result: dict[str, object] = dict(attributes)
                result["$text"] = element.text or ""
                return result
            return element.text or ""

        result = dict(attributes)
        for child in children:
            if etree.QName(child).namespace == XMLDSIG_NAMESPACE:
                continue
            name = etree.QName(child).localname
            value = convert(child)
            if name not in result:
                result[name] = value
            else:
                current = result[name]
                if not isinstance(current, list):
                    result[name] = [current]
                result[name].append(value)
        return result

    return {etree.QName(root).localname: convert(root)}

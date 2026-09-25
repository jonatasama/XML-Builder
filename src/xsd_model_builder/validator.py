from __future__ import annotations

from pathlib import Path

from lxml import etree

from .errors import GeneratedXmlValidationError, SchemaLoadError


def validate_xml(schema_path: Path, xml_path: Path) -> tuple[str, str]:
    """Valida um XML existente contra um XSD raiz e seus include/import."""

    schema_path = schema_path.resolve()
    xml_path = xml_path.resolve()
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False)
    try:
        schema = etree.XMLSchema(etree.parse(str(schema_path), parser))
    except (OSError, etree.XMLSyntaxError, etree.XMLSchemaParseError) as exc:
        raise SchemaLoadError(f"Não foi possível compilar {schema_path}: {exc}") from exc
    try:
        document = etree.parse(str(xml_path), parser)
    except (OSError, etree.XMLSyntaxError) as exc:
        raise GeneratedXmlValidationError(f"Não foi possível ler {xml_path}: {exc}") from exc
    if not schema.validate(document):
        details = "\n".join(
            f"linha {error.line}: {error.message}" for error in schema.error_log[:25]
        )
        raise GeneratedXmlValidationError(
            f"XML inválido para {schema_path.name}:\n{details}"
        )
    qname = etree.QName(document.getroot())
    return qname.namespace or "", qname.localname


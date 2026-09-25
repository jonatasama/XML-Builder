from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from lxml import etree

from .constants import NFEABI_NAMESPACE, XMLDSIG_NAMESPACE, XML_SCHEMA_NAMESPACE
from .errors import InputError, SchemaValidationError

XS = f"{{{XML_SCHEMA_NAMESPACE}}}"


class SchemaCatalog:
    """Catálogo mínimo de declarações XSD 1.0 ligadas por xs:include."""

    def __init__(self, root_schema: Path):
        self.root_schema = root_schema.resolve()
        self.target_namespace = NFEABI_NAMESPACE
        self.complex_types: dict[str, etree._Element] = {}
        self.simple_types: dict[str, etree._Element] = {}
        self.global_elements: dict[str, etree._Element] = {}
        self._loaded: set[Path] = set()
        self._load(self.root_schema)

    @staticmethod
    def _parse(path: Path) -> etree._ElementTree:
        parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_comments=False)
        return etree.parse(str(path), parser)

    def _load(self, path: Path) -> None:
        path = path.resolve()
        if path in self._loaded:
            return
        if not path.is_file():
            raise InputError(f"Schema não encontrado: {path}")
        self._loaded.add(path)

        tree = self._parse(path)
        schema = tree.getroot()
        target_namespace = schema.get("targetNamespace")
        if target_namespace:
            self.target_namespace = target_namespace

        for node in schema.findall(f"{XS}complexType"):
            if node.get("name"):
                self.complex_types[node.get("name")] = node
        for node in schema.findall(f"{XS}simpleType"):
            if node.get("name"):
                self.simple_types[node.get("name")] = node
        for node in schema.findall(f"{XS}element"):
            if node.get("name"):
                self.global_elements[node.get("name")] = node

        for include in schema.findall(f"{XS}include"):
            location = include.get("schemaLocation")
            if location:
                self._load(path.parent / location)

    def complex_type_for(self, element_decl: etree._Element) -> etree._Element | None:
        inline = element_decl.find(f"{XS}complexType")
        if inline is not None:
            return inline
        type_name = element_decl.get("type")
        if not type_name:
            return None
        return self.complex_types.get(type_name.split(":")[-1])


class SchemaValidator:
    def __init__(self, schema_path: Path):
        self.schema_path = schema_path.resolve()
        parser = etree.XMLParser(resolve_entities=False, no_network=True)
        self.schema = etree.XMLSchema(etree.parse(str(self.schema_path), parser))

    def validate(self, root: etree._Element, allow_unsigned: bool = False) -> None:
        candidate = deepcopy(root)
        signature = candidate.find(f"{{{XMLDSIG_NAMESPACE}}}Signature")
        if signature is None and allow_unsigned:
            from .signing import append_placeholder_signature

            target = candidate.find(f"{{{NFEABI_NAMESPACE}}}infNFeABI")
            target_id = target.get("Id") if target is not None else None
            append_placeholder_signature(candidate, target_id or "NFeABI" + "0" * 44)

        if self.schema.validate(candidate):
            return

        messages = []
        for error in self.schema.error_log:
            messages.append(f"linha {error.line}: {error.message}")
        detail = "\n".join(messages) if messages else "Erro XSD sem detalhe."
        raise SchemaValidationError(
            f"XML não atende a {self.schema_path.name}:\n{detail}"
        )


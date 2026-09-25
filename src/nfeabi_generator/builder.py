from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from lxml import etree

from .constants import NFEABI_NAMESPACE, XMLDSIG_NAMESPACE
from .errors import InputError
from .schema import SchemaCatalog, XS


class SchemaJsonBuilder:
    """Converte JSON em XML obedecendo a ordem declarada pelo XSD."""

    def __init__(self, catalog: SchemaCatalog):
        self.catalog = catalog

    def build(self, root_name: str, payload: object) -> etree._Element:
        declaration = self.catalog.global_elements.get(root_name)
        if declaration is None:
            raise InputError(f"Elemento global não encontrado no schema: {root_name}")
        root = etree.Element(
            etree.QName(self.catalog.target_namespace, root_name),
            nsmap={None: self.catalog.target_namespace},
        )
        self._populate(root, declaration, payload, root_name)
        return root

    def _populate(
        self,
        xml_element: etree._Element,
        declaration: etree._Element,
        payload: object,
        path: str,
    ) -> None:
        complex_type = self.catalog.complex_type_for(declaration)
        if complex_type is None:
            if isinstance(payload, (Mapping, list)) or payload is None:
                raise InputError(f"{path} deve possuir um valor escalar.")
            xml_element.text = self._scalar(payload)
            return

        if not isinstance(payload, Mapping):
            raise InputError(f"{path} deve ser um objeto JSON.")

        consumed: set[str] = set()
        for attribute in complex_type.findall(f"{XS}attribute"):
            name = attribute.get("name")
            if not name:
                continue
            key = "@" + name
            if key in payload:
                consumed.add(key)
                value = payload[key]
                if value is not None:
                    if str(value) == "":
                        raise InputError(f"Atributo vazio não permitido: {path}/{key}")
                    xml_element.set(name, self._scalar(value))

        particle = self._first_particle(complex_type)
        if particle is not None:
            self._emit_particle(xml_element, particle, payload, consumed, path)

        unknown = sorted(
            key
            for key in payload
            if key not in consumed and not key.startswith("$")
        )
        if unknown:
            raise InputError(
                f"Campos não reconhecidos em {path}: {', '.join(unknown)}"
            )

    @staticmethod
    def _first_particle(complex_type: etree._Element) -> etree._Element | None:
        for tag in ("sequence", "choice", "all"):
            particle = complex_type.find(f"{XS}{tag}")
            if particle is not None:
                return particle
        return None

    def _emit_particle(
        self,
        parent: etree._Element,
        particle: etree._Element,
        payload: Mapping[str, object],
        consumed: set[str],
        path: str,
    ) -> None:
        kind = etree.QName(particle).localname
        if kind in {"sequence", "all"}:
            for child in particle:
                local = etree.QName(child).localname
                if local == "element":
                    self._emit_declared_element(parent, child, payload, consumed, path)
                elif local in {"sequence", "choice", "all"}:
                    self._emit_particle(parent, child, payload, consumed, path)
                elif local == "any" and "$any" in payload:
                    raise InputError(
                        f"{path}/$any ainda não é suportado pelo montador da NF-e principal."
                    )
            return

        if kind == "choice":
            candidates: list[tuple[str, etree._Element]] = []
            for child in particle:
                if etree.QName(child).localname != "element":
                    continue
                name = self._element_name(child)
                if name in payload and payload[name] is not None:
                    candidates.append((name, child))
            if len(candidates) > 1:
                names = ", ".join(name for name, _ in candidates)
                raise InputError(f"Escolha exclusiva violada em {path}: {names}")
            if candidates:
                self._emit_declared_element(
                    parent, candidates[0][1], payload, consumed, path
                )

    def _emit_declared_element(
        self,
        parent: etree._Element,
        declaration: etree._Element,
        payload: Mapping[str, object],
        consumed: set[str],
        path: str,
    ) -> None:
        name = self._element_name(declaration)
        if name not in payload:
            return
        consumed.add(name)
        value = payload[name]
        if value is None:
            return

        repeated = declaration.get("maxOccurs", "1") != "1"
        if repeated and not isinstance(value, list):
            raise InputError(f"{path}/{name} deve ser um array JSON.")
        if not repeated and isinstance(value, list):
            raise InputError(f"{path}/{name} não aceita um array JSON.")

        values = value if isinstance(value, list) else [value]
        for index, item in enumerate(values, start=1):
            ref = declaration.get("ref", "")
            namespace = (
                XMLDSIG_NAMESPACE
                if ref.startswith("ds:")
                else self.catalog.target_namespace
            )
            child = etree.SubElement(parent, etree.QName(namespace, name))
            item_path = f"{path}/{name}"
            if repeated:
                item_path += f"[{index}]"
            self._populate(child, declaration, item, item_path)

    @staticmethod
    def _element_name(declaration: etree._Element) -> str:
        name = declaration.get("name")
        if name:
            return name
        ref = declaration.get("ref")
        if ref:
            return ref.split(":")[-1]
        raise InputError("Declaração xs:element sem name/ref.")

    @staticmethod
    def _scalar(value: object) -> str:
        if isinstance(value, bool):
            raise InputError("Valores booleanos devem ser informados como códigos string.")
        if isinstance(value, Decimal):
            return format(value, "f")
        text = str(value)
        if text == "":
            raise InputError("Elementos vazios não são permitidos; omita a tag opcional.")
        return text


def serialize_compact_xml(root: etree._Element) -> bytes:
    body = etree.tostring(root, encoding="UTF-8", xml_declaration=False, pretty_print=False)
    return b'<?xml version="1.0" encoding="UTF-8"?>' + body


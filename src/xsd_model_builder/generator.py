from __future__ import annotations

import base64
import re
import warnings
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree

from .errors import GeneratedXmlValidationError, GenerationError, SchemaLoadError
from .schema import XS, XSD_NAMESPACE, XsdCatalog, format_qname


@dataclass(frozen=True)
class GenerationOptions:
    include_optional: bool = True
    repeat_count: int = 1
    choice_index: int = 0
    max_depth: int = 64
    validate: bool = True
    pretty_print: bool = True

    def __post_init__(self) -> None:
        if self.repeat_count < 1:
            raise ValueError("repeat_count deve ser pelo menos 1.")
        if self.max_depth < 2:
            raise ValueError("max_depth deve ser pelo menos 2.")


@dataclass
class GenerationResult:
    root: etree._Element
    warnings: list[str]
    schema_path: Path
    root_qname: tuple[str, str]
    validated: bool

    def xml_bytes(self, pretty_print: bool = True) -> bytes:
        return etree.tostring(
            self.root,
            encoding="UTF-8",
            xml_declaration=True,
            pretty_print=pretty_print,
        )


@dataclass
class SimpleSpec:
    builtin: str = "string"
    enumerations: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    length: int | None = None
    min_length: int | None = None
    max_length: int | None = None
    min_inclusive: str | None = None
    max_inclusive: str | None = None
    min_exclusive: str | None = None
    max_exclusive: str | None = None
    total_digits: int | None = None
    fraction_digits: int | None = None
    list_item: SimpleSpec | None = None


class _UnmaterializableWildcard(Exception):
    """Sinaliza um wildcard strict sem declaração disponível no schema carregado."""


class XsdModelGenerator:
    """Sintetiza um exemplo XML diretamente das declarações de um XSD 1.0."""

    def __init__(self, catalog: XsdCatalog, options: GenerationOptions | None = None):
        self.catalog = catalog
        self.options = options or GenerationOptions()
        self.warnings: list[str] = list(catalog.warnings)
        self._id_counter = 0
        self._active_types: list[int] = []
        self._enumeration_counters: dict[tuple[str, ...], int] = {}

    def generate(self, root_name: str, root_namespace: str | None = None) -> GenerationResult:
        roots = self.catalog.root_elements()
        if root_namespace is None:
            matches = [qname for qname in roots if qname[1] == root_name]
            if len(matches) != 1:
                available = ", ".join(format_qname(item) for item in roots) or "nenhum"
                raise GenerationError(
                    f"Elemento raiz '{root_name}' não é unívoco. Disponíveis: {available}."
                )
            root_qname = matches[0]
        else:
            root_qname = (root_namespace, root_name)

        declaration = self.catalog.get_element(root_qname)
        use_default_namespace = (
            self.catalog.root_document.root.get("elementFormDefault") == "qualified"
        )
        nsmap = self.catalog.preferred_prefixes(root_qname[0])
        if root_qname[0] and not use_default_namespace:
            nsmap.pop(None, None)
            prefix = "tns"
            suffix = 1
            while prefix in nsmap:
                prefix = f"tns{suffix}"
                suffix += 1
            nsmap[prefix] = root_qname[0]

        root_tag = etree.QName(*root_qname) if root_qname[0] else root_qname[1]
        root = etree.Element(root_tag, nsmap=nsmap or None)
        self._populate_element(root, declaration, declaration, depth=0)

        validated = False
        if self.options.validate:
            self._validate(root)
            validated = True
        return GenerationResult(
            root=root,
            warnings=list(dict.fromkeys(self.warnings)),
            schema_path=self.catalog.root_schema,
            root_qname=root_qname,
            validated=validated,
        )

    def _populate_element(
        self,
        xml_element: etree._Element,
        element_use: etree._Element,
        declaration: etree._Element,
        depth: int,
    ) -> None:
        if depth > self.options.max_depth:
            raise GenerationError(
                f"Profundidade máxima excedida em {etree.QName(xml_element).localname}."
            )

        complex_type = self.catalog.complex_type_for(element_use)
        if complex_type is not None:
            self._populate_complex(xml_element, complex_type, depth + 1)
            return

        xml_element.text = self._sample_for_declaration(element_use, declaration)

    def _populate_complex(
        self,
        xml_element: etree._Element,
        complex_type: etree._Element,
        depth: int,
    ) -> None:
        identity = id(complex_type)
        if identity in self._active_types:
            self.warnings.append(
                f"Recursão interrompida no tipo de {etree.QName(xml_element).localname}."
            )
            return
        if depth > self.options.max_depth:
            self.warnings.append(
                f"Profundidade limitada em {etree.QName(xml_element).localname}."
            )
            return

        self._active_types.append(identity)
        try:
            simple_content = complex_type.find(f"{XS}simpleContent")
            if simple_content is not None:
                self._populate_simple_content(xml_element, simple_content, depth)
                return

            complex_content = complex_type.find(f"{XS}complexContent")
            if complex_content is not None:
                self._populate_complex_content(xml_element, complex_content, depth)
                return

            self._populate_complex_body(xml_element, complex_type, depth)
        finally:
            self._active_types.pop()

    def _populate_simple_content(
        self,
        xml_element: etree._Element,
        simple_content: etree._Element,
        depth: int,
    ) -> None:
        derivation = simple_content.find(f"{XS}extension")
        if derivation is None:
            derivation = simple_content.find(f"{XS}restriction")
        if derivation is None:
            xml_element.text = "EXEMPLO"
            return

        base = derivation.get("base")
        if base:
            qname = self.catalog.resolve_qname(base, derivation)
            if qname[0] == XSD_NAMESPACE:
                spec = SimpleSpec(builtin=qname[1])
            else:
                spec = self._spec_from_simple(self.catalog.simple_types.get(qname))
            if etree.QName(derivation).localname == "restriction":
                self._apply_facets(spec, derivation)
            xml_element.text = self._sample_from_spec(spec)
        else:
            inline = derivation.find(f"{XS}simpleType")
            xml_element.text = self._sample_from_spec(self._spec_from_simple(inline)) if inline is not None else "EXEMPLO"
        self._emit_attributes(xml_element, derivation, depth)

    def _populate_complex_content(
        self,
        xml_element: etree._Element,
        complex_content: etree._Element,
        depth: int,
    ) -> None:
        extension = complex_content.find(f"{XS}extension")
        restriction = complex_content.find(f"{XS}restriction")
        derivation = extension if extension is not None else restriction
        if derivation is None:
            return

        if extension is not None and extension.get("base"):
            qname = self.catalog.resolve_qname(extension.get("base", ""), extension)
            base_type = self.catalog.complex_types.get(qname)
            if base_type is not None:
                self._populate_complex(xml_element, base_type, depth + 1)
        self._populate_complex_body(xml_element, derivation, depth)

    def _populate_complex_body(
        self,
        xml_element: etree._Element,
        container: etree._Element,
        depth: int,
    ) -> None:
        for child in container:
            if not isinstance(child.tag, str):
                continue
            kind = etree.QName(child).localname
            if kind in {"sequence", "choice", "all", "group"}:
                self._emit_particle(xml_element, child, depth + 1)
                break
        self._emit_attributes(xml_element, container, depth)

    def _emit_particle(
        self,
        parent: etree._Element,
        particle: etree._Element,
        depth: int,
        *,
        ignore_occurs: bool = False,
    ) -> None:
        kind = etree.QName(particle).localname
        occurrences = 1 if ignore_occurs else self._occurrence_count(particle)
        if occurrences == 0:
            return

        if kind == "element":
            self._emit_element(parent, particle, occurrences, depth)
            return

        if kind == "any":
            self._emit_any(parent, particle, occurrences)
            return

        if kind == "group":
            group = self.catalog.resolve_group(particle)
            body = next(
                (
                    child
                    for child in group
                    if isinstance(child.tag, str)
                    if etree.QName(child).localname in {"sequence", "choice", "all"}
                ),
                None,
            )
            if body is None:
                return
            for _ in range(occurrences):
                self._emit_particle(parent, body, depth + 1, ignore_occurs=True)
            return

        if kind == "choice":
            alternatives = [
                child
                for child in particle
                if isinstance(child.tag, str)
                if etree.QName(child).localname
                in {"element", "sequence", "choice", "all", "group", "any"}
                and child.get("maxOccurs", "1") != "0"
            ]
            if not alternatives:
                return
            selected_index = min(self.options.choice_index, len(alternatives) - 1)
            selected = alternatives[selected_index]
            for _ in range(occurrences):
                self._emit_particle(parent, selected, depth + 1)
            if len(alternatives) > 1:
                names = [self._particle_label(item) for item in alternatives]
                self.warnings.append(
                    f"xs:choice em {etree.QName(parent).localname}: usada alternativa "
                    f"'{names[selected_index]}'; demais: {', '.join(names[:selected_index] + names[selected_index + 1:])}."
                )
            return

        if kind in {"sequence", "all"}:
            for _ in range(occurrences):
                for child in particle:
                    if not isinstance(child.tag, str):
                        continue
                    child_kind = etree.QName(child).localname
                    if child_kind in {
                        "element",
                        "sequence",
                        "choice",
                        "all",
                        "group",
                        "any",
                    }:
                        self._emit_particle(parent, child, depth + 1)
            return

    def _emit_element(
        self,
        parent: etree._Element,
        element_use: etree._Element,
        occurrences: int,
        depth: int,
    ) -> None:
        declaration = self.catalog.element_declaration(element_use)
        namespace, name = self.catalog.element_qname(element_use)
        for _ in range(occurrences):
            tag = etree.QName(namespace, name) if namespace else name
            child = etree.SubElement(parent, tag)
            try:
                self._populate_element(child, element_use, declaration, depth + 1)
            except _UnmaterializableWildcard as exc:
                parent.remove(child)
                if element_use.get("minOccurs", "1") == "0":
                    self.warnings.append(
                        f"Elemento opcional '{name}' omitido: {exc}"
                    )
                    return
                raise GenerationError(
                    f"Não foi possível materializar o elemento obrigatório '{name}': {exc}"
                ) from exc

    def _emit_any(
        self,
        parent: etree._Element,
        particle: etree._Element,
        occurrences: int,
    ) -> None:
        namespace_rule = particle.get("namespace", "##any")
        process = particle.get("processContents", "strict")
        if process == "strict" and particle.get("minOccurs", "1") == "0":
            self.warnings.append(
                f"xs:any opcional e strict em {etree.QName(parent).localname} foi omitido, "
                "pois não há declaração concreta selecionada para o wildcard."
            )
            return
        if process == "strict":
            raise _UnmaterializableWildcard(
                "xs:any obrigatório com processContents='strict' não identifica "
                "qual declaração global deve ocupar o conteúdo."
            )
        document_namespace = self.catalog.document_for(particle).target_namespace
        tokens = namespace_rule.split()
        if "##local" in tokens:
            namespace = ""
        elif "##targetNamespace" in tokens:
            namespace = document_namespace
        elif "##other" in tokens or "##any" in tokens:
            namespace = "urn:xsd-model-builder:any"
        else:
            namespace = next((item for item in tokens if not item.startswith("##")), "")

        for index in range(1, occurrences + 1):
            name = "conteudoExemplo" if occurrences == 1 else f"conteudoExemplo{index}"
            tag = etree.QName(namespace, name) if namespace else name
            child = etree.SubElement(parent, tag)
            child.text = "EXEMPLO"
        self.warnings.append(
            f"xs:any ({namespace_rule}, {process}) em {etree.QName(parent).localname} "
            "foi representado por conteúdo genérico."
        )

    def _emit_attributes(
        self,
        xml_element: etree._Element,
        container: etree._Element,
        depth: int,
    ) -> None:
        for child in container:
            if not isinstance(child.tag, str):
                continue
            kind = etree.QName(child).localname
            if kind == "attribute":
                self._emit_attribute(xml_element, child)
            elif kind == "attributeGroup":
                group = self.catalog.resolve_attribute_group(child)
                self._emit_attributes(xml_element, group, depth + 1)
            elif kind == "anyAttribute":
                self.warnings.append(
                    f"xs:anyAttribute não foi materializado em {etree.QName(xml_element).localname}."
                )

    def _emit_attribute(self, xml_element: etree._Element, use: etree._Element) -> None:
        declaration = self.catalog.attribute_declaration(use)
        effective_use = use.get("use") or declaration.get("use") or "optional"
        if effective_use == "prohibited":
            return
        if effective_use != "required" and not self.options.include_optional:
            return
        namespace, name = self.catalog.attribute_qname(use)
        qname = etree.QName(namespace, name) if namespace else name
        if qname in xml_element.attrib:
            return
        xml_element.set(qname, self._sample_for_declaration(use, declaration))

    def _occurrence_count(self, particle: etree._Element) -> int:
        minimum = _parse_occurs(particle.get("minOccurs", "1"), default=1)
        maximum_text = particle.get("maxOccurs", "1")
        if maximum_text == "unbounded":
            maximum: int | None = None
        else:
            maximum = _parse_occurs(maximum_text, default=1)
        if maximum == 0:
            return 0
        if not self.options.include_optional:
            return minimum
        desired = max(minimum, self.options.repeat_count if maximum != 1 else 1)
        return min(desired, maximum) if maximum is not None else desired

    def _sample_for_declaration(
        self,
        use: etree._Element,
        declaration: etree._Element,
    ) -> str:
        for node in (use, declaration):
            fixed = node.get("fixed")
            if fixed is not None:
                return fixed
        for node in (use, declaration):
            default = node.get("default")
            if default is not None:
                return default

        simple_type = self.catalog.simple_type_for(declaration)
        if simple_type is None and use is not declaration:
            simple_type = self.catalog.simple_type_for(use)
        if simple_type is not None:
            return self._sample_from_spec(self._spec_from_simple(simple_type))

        lexical = declaration.get("type") or use.get("type")
        if lexical:
            return self._sample_for_type(lexical, declaration if declaration.get("type") else use)
        return "EXEMPLO"

    def _sample_for_type(self, lexical: str, context: etree._Element) -> str:
        qname = self.catalog.resolve_qname(lexical, context)
        if qname[0] == XSD_NAMESPACE:
            return self._sample_from_spec(SimpleSpec(builtin=qname[1]))
        simple_type = self.catalog.simple_types.get(qname)
        if simple_type is not None:
            return self._sample_from_spec(self._spec_from_simple(simple_type))
        if qname in self.catalog.complex_types:
            return "EXEMPLO"
        self.warnings.append(f"Tipo não resolvido: {format_qname(qname)}.")
        return "EXEMPLO"

    def _spec_from_simple(
        self,
        simple_type: etree._Element | None,
        seen: set[int] | None = None,
    ) -> SimpleSpec:
        if simple_type is None:
            return SimpleSpec()
        seen = set() if seen is None else seen
        if id(simple_type) in seen:
            return SimpleSpec()
        seen.add(id(simple_type))

        restriction = simple_type.find(f"{XS}restriction")
        if restriction is not None:
            base = restriction.get("base")
            if base:
                qname = self.catalog.resolve_qname(base, restriction)
                if qname[0] == XSD_NAMESPACE:
                    spec = SimpleSpec(builtin=qname[1])
                else:
                    spec = self._spec_from_simple(self.catalog.simple_types.get(qname), seen)
            else:
                spec = self._spec_from_simple(restriction.find(f"{XS}simpleType"), seen)
            self._apply_facets(spec, restriction)
            return spec

        list_node = simple_type.find(f"{XS}list")
        if list_node is not None:
            item_type = list_node.get("itemType")
            if item_type:
                qname = self.catalog.resolve_qname(item_type, list_node)
                item_spec = (
                    SimpleSpec(builtin=qname[1])
                    if qname[0] == XSD_NAMESPACE
                    else self._spec_from_simple(self.catalog.simple_types.get(qname), seen)
                )
            else:
                item_spec = self._spec_from_simple(list_node.find(f"{XS}simpleType"), seen)
            return SimpleSpec(builtin="list", list_item=item_spec)

        union = simple_type.find(f"{XS}union")
        if union is not None:
            members = union.get("memberTypes", "").split()
            if members:
                qname = self.catalog.resolve_qname(members[0], union)
                return (
                    SimpleSpec(builtin=qname[1])
                    if qname[0] == XSD_NAMESPACE
                    else self._spec_from_simple(self.catalog.simple_types.get(qname), seen)
                )
            inline = union.find(f"{XS}simpleType")
            return self._spec_from_simple(inline, seen)
        return SimpleSpec()

    @staticmethod
    def _apply_facets(spec: SimpleSpec, restriction: etree._Element) -> None:
        enumerations = [
            node.get("value", "") for node in restriction.findall(f"{XS}enumeration")
        ]
        if enumerations:
            spec.enumerations = enumerations
        spec.patterns.extend(
            node.get("value", "") for node in restriction.findall(f"{XS}pattern")
        )
        scalar_facets = {
            "length": ("length", int),
            "minLength": ("min_length", int),
            "maxLength": ("max_length", int),
            "minInclusive": ("min_inclusive", str),
            "maxInclusive": ("max_inclusive", str),
            "minExclusive": ("min_exclusive", str),
            "maxExclusive": ("max_exclusive", str),
            "totalDigits": ("total_digits", int),
            "fractionDigits": ("fraction_digits", int),
        }
        for facet_name, (attribute, converter) in scalar_facets.items():
            node = restriction.find(f"{XS}{facet_name}")
            if node is not None and node.get("value") is not None:
                setattr(spec, attribute, converter(node.get("value")))

    def _sample_from_spec(self, spec: SimpleSpec) -> str:
        if spec.enumerations:
            key = tuple(spec.enumerations)
            index = self._enumeration_counters.get(key, 0)
            self._enumeration_counters[key] = index + 1
            return spec.enumerations[index % len(spec.enumerations)]
        if spec.list_item is not None:
            return self._sample_from_spec(spec.list_item)

        if spec.builtin == "base64Binary":
            byte_count = spec.length if spec.length is not None else spec.min_length
            byte_count = max(byte_count or 1, 1)
            return base64.b64encode(bytes(byte_count)).decode("ascii")
        if spec.builtin == "hexBinary":
            byte_count = spec.length if spec.length is not None else spec.min_length
            byte_count = max(byte_count or 1, 1)
            return "00" * byte_count

        sample = _builtin_sample(spec, self._next_id)
        selected_pattern: str | None = None
        for pattern in reversed(spec.patterns):
            candidate = _sample_from_pattern(pattern)
            if candidate is not None:
                sample = candidate
                selected_pattern = pattern
                break

        target_length = spec.length if spec.length is not None else spec.min_length
        if target_length is not None and len(sample) < target_length:
            expanded = (
                _sample_from_pattern(selected_pattern, min_length=target_length)
                if selected_pattern is not None
                else None
            )
            if expanded is not None and len(expanded) >= target_length:
                sample = expanded
            else:
                fill = _fill_character(spec, sample)
                sample += fill * (target_length - len(sample))
        maximum = spec.length if spec.length is not None else spec.max_length
        if maximum is not None and len(sample) > maximum:
            sample = sample[:maximum]
        return sample

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"id{self._id_counter}"

    def _validate(self, root: etree._Element) -> None:
        try:
            parser = etree.XMLParser(resolve_entities=False, no_network=True)
            schema = etree.XMLSchema(etree.parse(str(self.catalog.root_schema), parser))
        except (OSError, etree.XMLSchemaParseError, etree.XMLSyntaxError) as exc:
            raise SchemaLoadError(
                f"O schema raiz não pôde ser compilado: {self.catalog.root_schema.name}: {exc}"
            ) from exc
        if schema.validate(root):
            return
        messages = [
            f"linha {error.line}: {error.message}" for error in schema.error_log[:25]
        ]
        raise GeneratedXmlValidationError(
            "O modelo foi montado, mas não passou pelo próprio XSD:\n"
            + "\n".join(messages)
        )

    @staticmethod
    def _particle_label(particle: etree._Element) -> str:
        kind = etree.QName(particle).localname
        return particle.get("name") or particle.get("ref") or kind


def _parse_occurs(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _builtin_sample(spec: SimpleSpec, next_id: Callable[[], str]) -> str:
    builtin = spec.builtin
    if builtin in {"boolean"}:
        return "true"
    if builtin in {"date"}:
        return "2026-01-01"
    if builtin in {"dateTime"}:
        return "2026-01-01T12:00:00-03:00"
    if builtin in {"time"}:
        return "12:00:00-03:00"
    if builtin == "duration":
        return "P1D"
    if builtin == "gYear":
        return "2026"
    if builtin == "gYearMonth":
        return "2026-01"
    if builtin == "gMonth":
        return "--01"
    if builtin == "gMonthDay":
        return "--01-01"
    if builtin == "gDay":
        return "---01"
    if builtin == "base64Binary":
        return "AA=="
    if builtin == "hexBinary":
        return "00"
    if builtin == "anyURI":
        return "https://example.invalid/modelo"
    if builtin == "QName":
        return "string"
    if builtin == "language":
        return "pt-BR"
    if builtin == "ID":
        return next_id()
    if builtin in {"IDREF", "IDREFS"}:
        return "id1"
    if builtin in {"NCName", "Name", "NMTOKEN", "ENTITY"}:
        return "EXEMPLO"
    if builtin in {
        "decimal",
        "float",
        "double",
        "integer",
        "nonPositiveInteger",
        "negativeInteger",
        "long",
        "int",
        "short",
        "byte",
        "nonNegativeInteger",
        "unsignedLong",
        "unsignedInt",
        "unsignedShort",
        "unsignedByte",
        "positiveInteger",
    }:
        return _numeric_sample(spec)
    return "EXEMPLO"


def _numeric_sample(spec: SimpleSpec) -> str:
    value = Decimal("0")
    try:
        if spec.min_inclusive is not None:
            value = Decimal(spec.min_inclusive)
        elif spec.min_exclusive is not None:
            value = Decimal(spec.min_exclusive) + Decimal("1")
        elif spec.builtin in {"positiveInteger"}:
            value = Decimal("1")
        elif spec.builtin in {"negativeInteger"}:
            value = Decimal("-1")
    except InvalidOperation:
        value = Decimal("0")

    if spec.max_inclusive is not None:
        try:
            value = min(value, Decimal(spec.max_inclusive))
        except InvalidOperation:
            pass
    if spec.max_exclusive is not None:
        try:
            value = min(value, Decimal(spec.max_exclusive) - Decimal("1"))
        except InvalidOperation:
            pass

    if spec.fraction_digits:
        return f"{value:.{spec.fraction_digits}f}"
    if spec.builtin in {"decimal", "float", "double"}:
        return format(value, "f")
    return str(int(value))


def _fill_character(spec: SimpleSpec, sample: str) -> str:
    if sample and sample[-1].isdigit():
        return "0"
    if spec.builtin in {"hexBinary"}:
        return "0"
    return "X"


def _sample_from_pattern(pattern: str, *, min_length: int | None = None) -> str | None:
    normalized = _escape_xsd_anchor_literals(pattern)
    normalized = re.sub(r"\\p\{[^}]+\}", "A", normalized)
    normalized = normalized.replace(r"\i", "A").replace(r"\c", "A")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            import sre_parse

            parsed = sre_parse.parse(normalized)
        tokens = list(parsed)
        sample = _emit_regex_tokens(tokens)
        if min_length is not None and len(sample) < min_length:
            budget = [min_length - len(sample)]
            sample = _emit_regex_tokens(tokens, budget)
        return sample
    except Exception:
        return None


def _escape_xsd_anchor_literals(pattern: str) -> str:
    """Em regex XSD, ^ e $ são caracteres comuns, não âncoras."""
    output: list[str] = []
    escaped = False
    in_class = False
    for character in pattern:
        if escaped:
            output.append(character)
            escaped = False
            continue
        if character == "\\":
            output.append(character)
            escaped = True
            continue
        if character == "[":
            in_class = True
        elif character == "]":
            in_class = False
        if character in {"^", "$"} and not in_class:
            output.append("\\")
        output.append(character)
    return "".join(output)


def _emit_regex_tokens(
    tokens: list[tuple[object, object]],
    growth_budget: list[int] | None = None,
) -> str:
    output: list[str] = []
    for operation, argument in tokens:
        name = str(operation)
        if name == "LITERAL":
            output.append(chr(argument))
        elif name == "NOT_LITERAL":
            output.append("A" if chr(argument) != "A" else "B")
        elif name == "ANY":
            output.append("A")
        elif name == "IN":
            output.append(_emit_character_class(argument))
        elif name in {"MAX_REPEAT", "MIN_REPEAT", "POSSESSIVE_REPEAT"}:
            minimum, maximum, nested = argument
            unit = _emit_regex_tokens(list(nested))
            count = minimum
            if growth_budget is not None and growth_budget[0] > 0 and unit:
                capacity = None if maximum == 2**32 - 1 else max(maximum - minimum, 0)
                wanted = (growth_budget[0] + len(unit) - 1) // len(unit)
                added = wanted if capacity is None else min(wanted, capacity)
                count += added
                growth_budget[0] = max(growth_budget[0] - added * len(unit), 0)
            output.append(unit * count)
        elif name == "SUBPATTERN":
            output.append(_emit_regex_tokens(list(argument[-1]), growth_budget))
        elif name == "BRANCH":
            branches = argument[1]
            selected = next(
                (branch for branch in branches if _emit_regex_tokens(list(branch))),
                branches[0],
            )
            output.append(_emit_regex_tokens(list(selected), growth_budget))
        elif name == "CATEGORY":
            output.append(_category_character(str(argument)))
        elif name in {"AT", "ASSERT", "ASSERT_NOT"}:
            continue
    return "".join(output)


def _emit_character_class(tokens: list[tuple[object, object]]) -> str:
    negate = any(str(operation) == "NEGATE" for operation, _ in tokens)
    if negate:
        excluded = [item for item in tokens if str(item[0]) != "NEGATE"]
        for candidate in ("A", "0", "_", "-", " "):
            if not any(_character_matches_class_token(candidate, item) for item in excluded):
                return candidate
        return "A"
    for operation, argument in tokens:
        name = str(operation)
        if name == "LITERAL":
            char = chr(argument)
            return char
        elif name == "RANGE":
            char = chr(argument[0])
            return char
        elif name == "CATEGORY":
            return _category_character(str(argument))
    return "A"


def _character_matches_class_token(
    character: str,
    token: tuple[object, object],
) -> bool:
    operation, argument = token
    name = str(operation)
    if name == "LITERAL":
        return character == chr(argument)
    if name == "RANGE":
        return chr(argument[0]) <= character <= chr(argument[1])
    if name == "CATEGORY":
        category = str(argument)
        if "NOT_" in category:
            positive = category.replace("NOT_", "")
            return not _character_matches_class_token(
                character,
                (operation, positive),
            )
        if "DIGIT" in category:
            return character.isdigit()
        if "SPACE" in category:
            return character.isspace()
        if "WORD" in category:
            return character.isalnum() or character == "_"
    return False


def _category_character(category: str) -> str:
    if "DIGIT" in category:
        return "0"
    if "SPACE" in category:
        return " "
    return "A"

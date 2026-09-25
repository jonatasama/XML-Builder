from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from lxml import etree

from .errors import SchemaLoadError


XSD_NAMESPACE = "http://www.w3.org/2001/XMLSchema"
XS = f"{{{XSD_NAMESPACE}}}"


@dataclass(frozen=True)
class SchemaCandidate:
    path: Path
    relative_path: str
    target_namespace: str
    global_elements: tuple[str, ...]

    @property
    def display_name(self) -> str:
        roots = ", ".join(self.global_elements) if self.global_elements else "sem raiz"
        return f"{self.relative_path}  [{roots}]"


@dataclass
class SchemaDocument:
    path: Path
    tree: etree._ElementTree
    target_namespace: str

    @property
    def root(self) -> etree._Element:
        return self.tree.getroot()


def _secure_parser() -> etree.XMLParser:
    return etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        remove_comments=False,
        huge_tree=False,
    )


def discover_schemas(folder: Path) -> list[SchemaCandidate]:
    folder = folder.resolve()
    if not folder.is_dir():
        raise SchemaLoadError(f"Pasta de schemas não encontrada: {folder}")

    candidates: list[SchemaCandidate] = []
    parse_errors: list[str] = []
    for path in sorted(folder.rglob("*.xsd"), key=lambda item: str(item).lower()):
        try:
            root = etree.parse(str(path), _secure_parser()).getroot()
        except (OSError, etree.XMLSyntaxError) as exc:
            parse_errors.append(f"{path.name}: {exc}")
            continue
        if root.tag != f"{XS}schema":
            continue
        elements = tuple(
            node.get("name", "")
            for node in root.findall(f"{XS}element")
            if node.get("name")
        )
        candidates.append(
            SchemaCandidate(
                path=path.resolve(),
                relative_path=str(path.relative_to(folder)),
                target_namespace=root.get("targetNamespace", ""),
                global_elements=elements,
            )
        )

    if not candidates:
        detail = "\n".join(parse_errors[:5])
        suffix = f"\n{detail}" if detail else ""
        raise SchemaLoadError(f"Nenhum arquivo XSD válido encontrado em {folder}.{suffix}")
    return candidates


class XsdCatalog:
    """Catálogo QName-aware de declarações ligadas por include/import."""

    def __init__(self, root_schema: Path):
        self.root_schema = root_schema.resolve()
        self.documents: dict[tuple[Path, str], SchemaDocument] = {}
        self._document_by_root: dict[int, SchemaDocument] = {}
        self.elements: dict[tuple[str, str], etree._Element] = {}
        self.complex_types: dict[tuple[str, str], etree._Element] = {}
        self.simple_types: dict[tuple[str, str], etree._Element] = {}
        self.groups: dict[tuple[str, str], etree._Element] = {}
        self.attribute_groups: dict[tuple[str, str], etree._Element] = {}
        self.attributes: dict[tuple[str, str], etree._Element] = {}
        self.warnings: list[str] = []
        self._load(self.root_schema, inherited_namespace=None)
        self.root_document = self._root_document()

    def _root_document(self) -> SchemaDocument:
        matches = [
            document
            for (path, _), document in self.documents.items()
            if path == self.root_schema
        ]
        if not matches:
            raise SchemaLoadError(f"Schema raiz não carregado: {self.root_schema}")
        return matches[0]

    def _load(self, path: Path, inherited_namespace: str | None) -> None:
        path = path.resolve()
        if not path.is_file():
            raise SchemaLoadError(f"Schema referenciado não encontrado: {path}")
        try:
            tree = etree.parse(str(path), _secure_parser())
        except (OSError, etree.XMLSyntaxError) as exc:
            raise SchemaLoadError(f"Não foi possível ler {path}: {exc}") from exc

        root = tree.getroot()
        if root.tag != f"{XS}schema":
            raise SchemaLoadError(f"Arquivo não contém xs:schema: {path}")
        declared_namespace = root.get("targetNamespace")
        effective_namespace = declared_namespace or inherited_namespace or ""
        key = (path, effective_namespace)
        if key in self.documents:
            return

        document = SchemaDocument(path, tree, effective_namespace)
        self.documents[key] = document
        self._document_by_root[id(root)] = document
        self._index_document(document)

        for include in root.findall(f"{XS}include"):
            location = include.get("schemaLocation")
            if location:
                self._load(path.parent / location, effective_namespace)

        for imported in root.findall(f"{XS}import"):
            location = imported.get("schemaLocation")
            namespace = imported.get("namespace") or ""
            if location:
                self._load(path.parent / location, namespace)
            else:
                self.warnings.append(
                    f"Import sem schemaLocation ignorado em {path.name}: {namespace or '(sem namespace)'}"
                )

    def _index_document(self, document: SchemaDocument) -> None:
        maps = {
            "element": self.elements,
            "complexType": self.complex_types,
            "simpleType": self.simple_types,
            "group": self.groups,
            "attributeGroup": self.attribute_groups,
            "attribute": self.attributes,
        }
        for local_name, destination in maps.items():
            for node in document.root.findall(f"{XS}{local_name}"):
                name = node.get("name")
                if name:
                    destination[(document.target_namespace, name)] = node

    def document_for(self, node: etree._Element) -> SchemaDocument:
        root = node.getroottree().getroot()
        document = self._document_by_root.get(id(root))
        if document is not None:
            return document
        for candidate in self.documents.values():
            if candidate.path == Path(node.base or "").resolve():
                return candidate
        raise SchemaLoadError("Não foi possível identificar o schema de uma declaração.")

    def resolve_qname(
        self,
        lexical: str,
        context: etree._Element,
        *,
        default_to_target: bool = True,
    ) -> tuple[str, str]:
        if ":" in lexical:
            prefix, local_name = lexical.split(":", 1)
            namespace = context.nsmap.get(prefix)
            if namespace is None:
                raise SchemaLoadError(f"Prefixo não declarado '{prefix}' em {context.base}.")
            return namespace, local_name

        local_name = lexical
        namespace = context.nsmap.get(None)
        if namespace:
            return namespace, local_name
        if default_to_target:
            return self.document_for(context).target_namespace, local_name
        return "", local_name

    def root_elements(self) -> list[tuple[str, str]]:
        namespace = self.root_document.target_namespace
        return [
            (namespace, node.get("name", ""))
            for node in self.root_document.root.findall(f"{XS}element")
            if node.get("name")
        ]

    def get_element(self, qname: tuple[str, str]) -> etree._Element:
        try:
            return self.elements[qname]
        except KeyError as exc:
            raise SchemaLoadError(f"Elemento global não encontrado: {format_qname(qname)}") from exc

    def element_declaration(self, use: etree._Element) -> etree._Element:
        ref = use.get("ref")
        return self.get_element(self.resolve_qname(ref, use)) if ref else use

    def element_qname(self, use: etree._Element) -> tuple[str, str]:
        ref = use.get("ref")
        if ref:
            return self.resolve_qname(ref, use)
        name = use.get("name")
        if not name:
            raise SchemaLoadError("xs:element sem name/ref.")
        parent = use.getparent()
        is_global = parent is not None and parent.tag == f"{XS}schema"
        document = self.document_for(use)
        qualified = is_global or use.get("form") == "qualified"
        if use.get("form") is None:
            qualified = qualified or document.root.get("elementFormDefault") == "qualified"
        return (document.target_namespace if qualified else "", name)

    def attribute_declaration(self, use: etree._Element) -> etree._Element:
        ref = use.get("ref")
        if not ref:
            return use
        qname = self.resolve_qname(ref, use)
        try:
            return self.attributes[qname]
        except KeyError as exc:
            raise SchemaLoadError(f"Atributo global não encontrado: {format_qname(qname)}") from exc

    def attribute_qname(self, use: etree._Element) -> tuple[str, str]:
        ref = use.get("ref")
        if ref:
            return self.resolve_qname(ref, use)
        name = use.get("name")
        if not name:
            raise SchemaLoadError("xs:attribute sem name/ref.")
        document = self.document_for(use)
        qualified = use.get("form") == "qualified"
        if use.get("form") is None:
            qualified = document.root.get("attributeFormDefault") == "qualified"
        return (document.target_namespace if qualified else "", name)

    def resolve_type(self, lexical: str, context: etree._Element) -> etree._Element | None:
        qname = self.resolve_qname(lexical, context)
        if qname[0] == XSD_NAMESPACE:
            return None
        complex_type = self.complex_types.get(qname)
        return complex_type if complex_type is not None else self.simple_types.get(qname)

    def complex_type_for(self, element_use: etree._Element) -> etree._Element | None:
        declaration = self.element_declaration(element_use)
        inline = declaration.find(f"{XS}complexType")
        if inline is not None:
            return inline
        lexical = declaration.get("type")
        if not lexical:
            return None
        qname = self.resolve_qname(lexical, declaration)
        return self.complex_types.get(qname)

    def simple_type_for(self, declaration: etree._Element) -> etree._Element | None:
        inline = declaration.find(f"{XS}simpleType")
        if inline is not None:
            return inline
        lexical = declaration.get("type")
        if not lexical:
            return None
        qname = self.resolve_qname(lexical, declaration)
        return self.simple_types.get(qname)

    def resolve_group(self, use: etree._Element) -> etree._Element:
        ref = use.get("ref")
        if not ref:
            return use
        qname = self.resolve_qname(ref, use)
        try:
            return self.groups[qname]
        except KeyError as exc:
            raise SchemaLoadError(f"Grupo não encontrado: {format_qname(qname)}") from exc

    def resolve_attribute_group(self, use: etree._Element) -> etree._Element:
        ref = use.get("ref")
        if not ref:
            return use
        qname = self.resolve_qname(ref, use)
        try:
            return self.attribute_groups[qname]
        except KeyError as exc:
            raise SchemaLoadError(
                f"Grupo de atributos não encontrado: {format_qname(qname)}"
            ) from exc

    def preferred_prefixes(self, root_namespace: str) -> dict[str | None, str]:
        nsmap: dict[str | None, str] = {}
        if root_namespace:
            nsmap[None] = root_namespace
        used_prefixes: set[str] = set()
        counter = 1
        namespaces = sorted(
            {
                document.target_namespace
                for document in self.documents.values()
                if document.target_namespace
                and document.target_namespace not in {root_namespace, XSD_NAMESPACE}
            }
        )
        for namespace in namespaces:
            preferred = None
            for document in self.documents.values():
                for prefix, uri in document.root.nsmap.items():
                    if uri == namespace and prefix and prefix not in {"xs", "xsd"}:
                        preferred = prefix
                        break
                if preferred:
                    break
            while preferred is None or preferred in used_prefixes:
                preferred = f"ns{counter}"
                counter += 1
            used_prefixes.add(preferred)
            nsmap[preferred] = namespace
        return nsmap


def format_qname(qname: tuple[str, str]) -> str:
    namespace, local_name = qname
    return f"{{{namespace}}}{local_name}" if namespace else local_name

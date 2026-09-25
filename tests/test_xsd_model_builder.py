from __future__ import annotations

import base64
import tempfile
import unittest
from pathlib import Path

from lxml import etree

from xsd_model_builder import (
    GenerationOptions,
    XsdCatalog,
    XsdModelGenerator,
    discover_schemas,
    validate_xml,
)
from xsd_model_builder.errors import GeneratedXmlValidationError


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_DIR = PROJECT_DIR / "SVRS Oficiais" / "NFeABI" / "PL_NFeABI_1.00" / "PL_NFeABI_1.00"


CUSTOM_SCHEMA = r"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:t="urn:teste:generico"
           targetNamespace="urn:teste:generico"
           elementFormDefault="unqualified">
  <xs:element name="documento" type="t:TDocumento"/>
  <xs:complexType name="TDocumento">
    <xs:sequence>
      <xs:element name="codigo">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:pattern value="[A-Z]{2}[0-9]{3}"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <!-- Comentários dentro de partículas devem ser ignorados. -->
      <xs:element name="serie">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:pattern value="^0{0,4}\d{1,5}$"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="texto">
        <xs:simpleType>
          <xs:restriction base="xs:string">
            <xs:pattern value="[\s\S]*[^\s][\s\S]*"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="hash">
        <xs:simpleType>
          <xs:restriction base="xs:base64Binary">
            <xs:length value="20"/>
          </xs:restriction>
        </xs:simpleType>
      </xs:element>
      <xs:element name="opcional" type="xs:string" minOccurs="0"/>
      <xs:choice>
        <xs:element name="pessoaFisica" type="xs:string"/>
        <xs:element name="pessoaJuridica" type="xs:string"/>
      </xs:choice>
      <xs:element name="item" type="xs:integer" minOccurs="1" maxOccurs="3"/>
      <xs:any namespace="##other" processContents="strict" minOccurs="0" maxOccurs="unbounded"/>
    </xs:sequence>
    <xs:attribute name="versao" use="required" fixed="1.0"/>
    <xs:attribute name="observacao" type="xs:string" use="optional"/>
  </xs:complexType>
</xs:schema>
"""


STRICT_WILDCARD_SCHEMA = r"""<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <xs:element name="documento">
    <xs:complexType>
      <xs:sequence>
        <xs:element name="conteudoExterno" minOccurs="0">
          <xs:complexType>
            <xs:sequence>
              <xs:any processContents="strict"/>
            </xs:sequence>
          </xs:complexType>
        </xs:element>
      </xs:sequence>
    </xs:complexType>
  </xs:element>
</xs:schema>
"""


class GenericXsdBuilderTests(unittest.TestCase):
    def test_discovers_xsd_files_and_global_roots(self) -> None:
        candidates = discover_schemas(SCHEMA_DIR)
        names = {item.path.name: item.global_elements for item in candidates}
        self.assertIn("NFeABI_v1.00.xsd", names)
        self.assertEqual(("NFeABI",), names["NFeABI_v1.00.xsd"])

    def test_generates_complete_nfeabi_structure_using_only_xsd(self) -> None:
        catalog = XsdCatalog(SCHEMA_DIR / "NFeABI_v1.00.xsd")
        result = XsdModelGenerator(
            catalog,
            GenerationOptions(include_optional=True, validate=True),
        ).generate("NFeABI")

        namespaces = {
            "n": "http://www.portalfiscal.inf.br/nfeabi",
            "ds": "http://www.w3.org/2000/09/xmldsig#",
        }
        self.assertTrue(result.validated)
        self.assertIsNotNone(result.root.find("n:infNFeABI/n:NFref", namespaces))
        self.assertIsNotNone(result.root.find("n:infNFeABI/n:pag", namespaces))
        self.assertIsNotNone(result.root.find("ds:Signature", namespaces))
        self.assertGreater(len(result.root.xpath(".//*")), 200)

    def test_generates_every_global_document_in_nfeabi_package(self) -> None:
        generated: list[tuple[str, str]] = []
        for candidate in discover_schemas(SCHEMA_DIR):
            for root_name in candidate.global_elements:
                result = XsdModelGenerator(
                    XsdCatalog(candidate.path),
                    GenerationOptions(include_optional=True, validate=True),
                ).generate(root_name)
                self.assertTrue(result.validated)
                generated.append((candidate.path.name, root_name))
        self.assertEqual(14, len(generated))

    def test_complete_and_minimal_modes_respect_optional_and_choice(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "modelo.xsd"
            schema_path.write_text(CUSTOM_SCHEMA, encoding="utf-8")

            complete = XsdModelGenerator(
                XsdCatalog(schema_path),
                GenerationOptions(include_optional=True, choice_index=1, validate=True),
            ).generate("documento")
            reparsed = etree.fromstring(complete.xml_bytes())
            self.assertEqual("AA000", reparsed.findtext("codigo"))
            self.assertEqual("^0$", reparsed.findtext("serie"))
            self.assertEqual("A", reparsed.findtext("texto"))
            self.assertEqual(20, len(base64.b64decode(reparsed.findtext("hash"))))
            self.assertIsNotNone(reparsed.find("opcional"))
            self.assertIsNone(reparsed.find("pessoaFisica"))
            self.assertIsNotNone(reparsed.find("pessoaJuridica"))
            self.assertEqual("1.0", reparsed.get("versao"))
            self.assertIsNotNone(reparsed.get("observacao"))

            minimal = XsdModelGenerator(
                XsdCatalog(schema_path),
                GenerationOptions(include_optional=False, validate=True),
            ).generate("documento")
            reparsed_minimal = etree.fromstring(minimal.xml_bytes())
            self.assertIsNone(reparsed_minimal.find("opcional"))
            self.assertIsNotNone(reparsed_minimal.find("pessoaFisica"))
            self.assertIsNone(reparsed_minimal.get("observacao"))

    def test_expands_a_pattern_wildcard_to_satisfy_min_length(self) -> None:
        schema = CUSTOM_SCHEMA.replace(
            '<xs:element name="opcional" type="xs:string" minOccurs="0"/>',
            '''<xs:element name="url">
              <xs:simpleType>
                <xs:restriction base="xs:string">
                  <xs:minLength value="40"/>
                  <xs:pattern value="https://.*\\?amb=[1-2]"/>
                </xs:restriction>
              </xs:simpleType>
            </xs:element>''',
        )
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "modelo.xsd"
            schema_path.write_text(schema, encoding="utf-8")
            result = XsdModelGenerator(XsdCatalog(schema_path)).generate("documento")
            value = result.root.findtext("url")
            self.assertGreaterEqual(len(value), 40)
            self.assertTrue(value.endswith("?amb=1"))

    def test_omits_optional_container_with_required_strict_wildcard(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "modelo.xsd"
            schema_path.write_text(STRICT_WILDCARD_SCHEMA, encoding="utf-8")
            result = XsdModelGenerator(XsdCatalog(schema_path)).generate("documento")
            self.assertTrue(result.validated)
            self.assertIsNone(result.root.find("conteudoExterno"))
            self.assertTrue(any("xs:any" in warning for warning in result.warnings))

    def test_validates_an_existing_xml_and_reports_invalid_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            schema_path = Path(directory) / "modelo.xsd"
            xml_path = Path(directory) / "modelo.xml"
            schema_path.write_text(CUSTOM_SCHEMA, encoding="utf-8")
            generated = XsdModelGenerator(XsdCatalog(schema_path)).generate("documento")
            xml_path.write_bytes(generated.xml_bytes())
            self.assertEqual(("urn:teste:generico", "documento"), validate_xml(schema_path, xml_path))
            xml_path.write_bytes(generated.xml_bytes().replace(b"AA000", b"INVALIDO"))
            with self.assertRaises(GeneratedXmlValidationError):
                validate_xml(schema_path, xml_path)

    def test_generates_nfse_101_complete_from_reported_schema(self) -> None:
        nfse_root = PROJECT_DIR.parent / "NFSE LOCACAO"
        schema_dirs = [
            nfse_root
            / "nfse-esquemas_xsd-v1-01-20260209"
            / "Schemas"
            / "1.01",
            nfse_root / "esquemas-nfse-rtc-v1-01-20260727",
        ]
        available = [item for item in schema_dirs if item.is_dir()]
        if not available:
            self.skipTest("Pacote NFSe 1.01 não está disponível neste workspace.")

        generated = 0
        for schema_dir in available:
            for schema_name, root_name in (
                ("DPS_v1.01.xsd", "DPS"),
                ("NFSe_v1.01.xsd", "NFSe"),
            ):
                result = XsdModelGenerator(
                    XsdCatalog(schema_dir / schema_name),
                    GenerationOptions(include_optional=True, validate=True),
                ).generate(root_name)
                self.assertTrue(result.validated)
                self.assertGreater(len(result.root.xpath(".//*")), 100)
                generated += 1
        self.assertGreaterEqual(generated, 2)

    def test_generates_nfe_model_55_with_binary_length_facet(self) -> None:
        schema_path = (
            PROJECT_DIR.parent
            / "NFe Modelo 55"
            / "PL_010d_NT2026.004"
            / "nfe_v4.00.xsd"
        )
        if not schema_path.is_file():
            self.skipTest("Pacote da NF-e modelo 55 não está disponível neste workspace.")

        result = XsdModelGenerator(
            XsdCatalog(schema_path),
            GenerationOptions(include_optional=True, validate=True),
        ).generate("NFe")
        namespace = {"n": "http://www.portalfiscal.inf.br/nfe"}
        hash_csrt = result.root.xpath("string(.//n:hashCSRT)", namespaces=namespace)
        self.assertTrue(result.validated)
        self.assertEqual(20, len(base64.b64decode(hash_csrt)))
        self.assertGreater(len(result.root.xpath(".//*")), 500)


if __name__ == "__main__":
    unittest.main()

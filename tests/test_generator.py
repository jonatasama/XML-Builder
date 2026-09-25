from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from lxml import etree

from nfeabi_generator.access_key import prepare_access_key
from nfeabi_generator.constants import NFEABI_NAMESPACE, XMLDSIG_NAMESPACE
from nfeabi_generator.errors import InputError
from nfeabi_generator.service import (
    build_document,
    load_json,
    validate_existing_xml,
)


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_DIR = PROJECT_DIR / "SVRS Oficiais" / "NFeABI" / "PL_NFeABI_1.00" / "PL_NFeABI_1.00"
EXAMPLE = PROJECT_DIR / "examples" / "nfeabi-completa.json"
EXPECTED_KEY = "42260984683408000103779010000000091076510666"


class AccessKeyTests(unittest.TestCase):
    def test_calculates_access_key_and_mutates_cdv_and_id(self) -> None:
        data = load_json(EXAMPLE)
        key = prepare_access_key(data)
        self.assertEqual(EXPECTED_KEY, key)
        inf = data["NFeABI"]["infNFeABI"]
        self.assertEqual("6", inf["ide"]["cDV"])
        self.assertEqual("NFeABI" + EXPECTED_KEY, inf["@Id"])

    def test_rejects_conflicting_digit(self) -> None:
        data = load_json(EXAMPLE)
        data["NFeABI"]["infNFeABI"]["ide"]["cDV"] = "9"
        with self.assertRaises(InputError):
            prepare_access_key(data)


class BuildTests(unittest.TestCase):
    def test_builds_unsigned_draft_in_schema_order(self) -> None:
        data = load_json(EXAMPLE)
        # Demonstra que a ordem do JSON não controla a ordem do XML.
        inf = data["NFeABI"]["infNFeABI"]
        data["NFeABI"]["infNFeABI"] = dict(reversed(list(inf.items())))

        result = build_document(data, SCHEMA_DIR)
        self.assertFalse(result.signed)
        self.assertEqual(EXPECTED_KEY, result.access_key)
        self.assertIsNone(result.root.find(f"{{{XMLDSIG_NAMESPACE}}}Signature"))

        children = [etree.QName(child).localname for child in result.root]
        self.assertEqual(["infNFeABI", "infNFeSupl"], children)
        inf_xml = result.root.find(f"{{{NFEABI_NAMESPACE}}}infNFeABI")
        inf_children = [etree.QName(child).localname for child in inf_xml]
        self.assertEqual(
            [
                "ide",
                "emit",
                "transmit",
                "adquirente",
                "imovel",
                "autXML",
                "infOper",
                "gInfTrib",
                "pag",
                "total",
                "infAdic",
                "infRespTec",
            ],
            inf_children,
        )

        self.assertEqual("1", inf_xml.findtext(f"{{{NFEABI_NAMESPACE}}}ide/{{{NFEABI_NAMESPACE}}}tpNF"))
        for tag in (
            "detOper",
            "indDeclarante",
            "pTransIndiv",
            "cCIB",
            "enquadramento",
            "areaTotal",
            "pTransImovel",
            "gRedAjusteImovel",
            "indRedSocial",
            "vRedSocial",
            "vRedAjusteIndiv",
            "detPagImovel",
            "infAdic",
        ):
            self.assertIsNotNone(
                inf_xml.find(f".//{{{NFEABI_NAMESPACE}}}{tag}"),
                f"Campo do modelo completo ausente: {tag}",
            )

        xml = result.xml_bytes()
        self.assertTrue(xml.startswith(b'<?xml version="1.0" encoding="UTF-8"?>'))
        self.assertNotIn(b">\n<", xml)

    def test_signed_document_passes_xsd_and_signature_verification(self) -> None:
        password = "senha-teste"
        with tempfile.TemporaryDirectory() as directory:
            pfx_path = Path(directory) / "teste.pfx"
            pfx_path.write_bytes(_create_test_pfx(password))
            result = build_document(
                load_json(EXAMPLE),
                SCHEMA_DIR,
                pfx_path=pfx_path,
                pfx_password=password,
            )
            self.assertTrue(result.signed)
            signature = result.root.find(f"{{{XMLDSIG_NAMESPACE}}}Signature")
            self.assertIsNotNone(signature)
            self.assertEqual(
                "Signature",
                etree.QName(list(result.root)[-1]).localname,
            )

            reparsed = etree.fromstring(result.xml_bytes())
            key, _, signed = validate_existing_xml(reparsed, SCHEMA_DIR)
            self.assertEqual(EXPECTED_KEY, key)
            self.assertTrue(signed)


def _create_test_pfx(password: str) -> bytes:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "Certificado sintetico NF-e ABI")]
    )
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .sign(private_key, hashes.SHA256())
    )
    return pkcs12.serialize_key_and_certificates(
        b"nfeabi-test",
        private_key,
        certificate,
        None,
        serialization.BestAvailableEncryption(password.encode("utf-8")),
    )


if __name__ == "__main__":
    unittest.main()

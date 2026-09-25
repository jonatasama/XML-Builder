from __future__ import annotations

import base64
import hashlib
from pathlib import Path

from lxml import etree

from .constants import (
    C14N_ALGORITHM,
    ENVELOPED_ALGORITHM,
    NFEABI_NAMESPACE,
    RSA_SHA1_ALGORITHM,
    SHA1_ALGORITHM,
    XMLDSIG_NAMESPACE,
)
from .errors import SignatureError


def _ds(local_name: str) -> etree.QName:
    return etree.QName(XMLDSIG_NAMESPACE, local_name)


def _canonicalize(element: etree._Element) -> bytes:
    return etree.tostring(
        element,
        method="c14n",
        exclusive=False,
        with_comments=False,
    )


def _signature_skeleton(root: etree._Element, target_id: str) -> tuple[etree._Element, etree._Element]:
    signature = etree.SubElement(
        root, _ds("Signature"), nsmap={None: XMLDSIG_NAMESPACE}
    )
    signed_info = etree.SubElement(signature, _ds("SignedInfo"))
    canonicalization = etree.SubElement(signed_info, _ds("CanonicalizationMethod"))
    canonicalization.set("Algorithm", C14N_ALGORITHM)
    signature_method = etree.SubElement(signed_info, _ds("SignatureMethod"))
    signature_method.set("Algorithm", RSA_SHA1_ALGORITHM)
    reference = etree.SubElement(signed_info, _ds("Reference"))
    reference.set("URI", "#" + target_id)
    transforms = etree.SubElement(reference, _ds("Transforms"))
    transform_enveloped = etree.SubElement(transforms, _ds("Transform"))
    transform_enveloped.set("Algorithm", ENVELOPED_ALGORITHM)
    transform_c14n = etree.SubElement(transforms, _ds("Transform"))
    transform_c14n.set("Algorithm", C14N_ALGORITHM)
    digest_method = etree.SubElement(reference, _ds("DigestMethod"))
    digest_method.set("Algorithm", SHA1_ALGORITHM)
    etree.SubElement(reference, _ds("DigestValue"))
    etree.SubElement(signature, _ds("SignatureValue"))
    key_info = etree.SubElement(signature, _ds("KeyInfo"))
    x509_data = etree.SubElement(key_info, _ds("X509Data"))
    etree.SubElement(x509_data, _ds("X509Certificate"))
    return signature, signed_info


def append_placeholder_signature(root: etree._Element, target_id: str) -> None:
    signature, _ = _signature_skeleton(root, target_id)
    signature.find(f".//{{{XMLDSIG_NAMESPACE}}}DigestValue").text = "AA=="
    signature.find(f"{{{XMLDSIG_NAMESPACE}}}SignatureValue").text = "AA=="
    signature.find(f".//{{{XMLDSIG_NAMESPACE}}}X509Certificate").text = "AA=="


def sign_xml(root: etree._Element, pfx_path: Path, password: str | None) -> None:
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
        from cryptography.hazmat.primitives.serialization import pkcs12
    except ImportError as exc:
        raise SignatureError(
            "Dependência 'cryptography' ausente. Instale o projeto com 'pip install -e .'."
        ) from exc

    if root.find(f"{{{XMLDSIG_NAMESPACE}}}Signature") is not None:
        raise SignatureError("O XML já possui Signature.")
    target = root.find(f"{{{NFEABI_NAMESPACE}}}infNFeABI")
    if target is None or not target.get("Id"):
        raise SignatureError("infNFeABI/@Id é obrigatório antes da assinatura.")

    try:
        pfx_data = pfx_path.read_bytes()
        private_key, certificate, _ = pkcs12.load_key_and_certificates(
            pfx_data, password.encode("utf-8") if password is not None else None
        )
    except Exception as exc:
        raise SignatureError(f"Não foi possível abrir o PFX: {exc}") from exc
    if private_key is None or certificate is None:
        raise SignatureError("O PFX deve conter chave privada e certificado.")
    if not isinstance(private_key, rsa.RSAPrivateKey):
        raise SignatureError("A assinatura NF-e ABI exige uma chave privada RSA.")

    signature, signed_info = _signature_skeleton(root, target.get("Id"))
    digest = hashlib.sha1(_canonicalize(target)).digest()
    signature.find(f".//{{{XMLDSIG_NAMESPACE}}}DigestValue").text = base64.b64encode(
        digest
    ).decode("ascii")

    signed_info_bytes = _canonicalize(signed_info)
    signed_value = private_key.sign(signed_info_bytes, padding.PKCS1v15(), hashes.SHA1())
    signature.find(f"{{{XMLDSIG_NAMESPACE}}}SignatureValue").text = base64.b64encode(
        signed_value
    ).decode("ascii")
    certificate_der = certificate.public_bytes(serialization.Encoding.DER)
    signature.find(f".//{{{XMLDSIG_NAMESPACE}}}X509Certificate").text = base64.b64encode(
        certificate_der
    ).decode("ascii")


def verify_xml_signature(root: etree._Element) -> None:
    try:
        from cryptography import x509
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError as exc:
        raise SignatureError("Dependência 'cryptography' ausente.") from exc

    signature = root.find(f"{{{XMLDSIG_NAMESPACE}}}Signature")
    if signature is None:
        raise SignatureError("Signature não encontrada.")
    signed_info = signature.find(f"{{{XMLDSIG_NAMESPACE}}}SignedInfo")
    reference = signed_info.find(f"{{{XMLDSIG_NAMESPACE}}}Reference") if signed_info is not None else None
    if signed_info is None or reference is None:
        raise SignatureError("SignedInfo/Reference ausente.")
    uri = reference.get("URI", "")
    if not uri.startswith("#"):
        raise SignatureError("Reference/@URI inválido.")
    target = root.xpath("//*[@Id=$identifier]", identifier=uri[1:])
    if len(target) != 1:
        raise SignatureError("Reference não identifica exatamente um elemento.")

    digest_text = reference.findtext(f"{{{XMLDSIG_NAMESPACE}}}DigestValue") or ""
    expected_digest = base64.b64encode(hashlib.sha1(_canonicalize(target[0])).digest()).decode(
        "ascii"
    )
    if digest_text != expected_digest:
        raise SignatureError("DigestValue diverge do conteúdo de infNFeABI.")

    signature_value = signature.findtext(f"{{{XMLDSIG_NAMESPACE}}}SignatureValue") or ""
    certificate_text = signature.findtext(
        f".//{{{XMLDSIG_NAMESPACE}}}X509Certificate"
    ) or ""
    try:
        certificate = x509.load_der_x509_certificate(base64.b64decode(certificate_text))
        certificate.public_key().verify(
            base64.b64decode(signature_value),
            _canonicalize(signed_info),
            padding.PKCS1v15(),
            hashes.SHA1(),
        )
    except InvalidSignature as exc:
        raise SignatureError("SignatureValue inválido.") from exc
    except Exception as exc:
        raise SignatureError(f"Falha ao verificar a assinatura: {exc}") from exc

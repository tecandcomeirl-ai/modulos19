"""Firma XMLDSig (enveloped, RSA-SHA256) dentro de ext:ExtensionContent."""
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from lxml import etree
from signxml import XMLSigner, methods

NS_DS = "http://www.w3.org/2000/09/xmldsig#"
NS_EXT = "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"


def sign_xml(xml_bytes, pfx_bytes, pfx_password):
    key, cert, _extra = pkcs12.load_key_and_certificates(
        pfx_bytes, (pfx_password or "").encode()
    )
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)

    root = etree.fromstring(xml_bytes)
    signer = XMLSigner(
        method=methods.enveloped,
        signature_algorithm="rsa-sha256",
        digest_algorithm="sha256",
        c14n_algorithm=C14N,
    )
    signed = signer.sign(root, key=key_pem, cert=cert_pem, reference_uri="")
    sig = signed.find("{%s}Signature" % NS_DS)
    sig.set("Id", "SignSUNAT")
    content = signed.find(".//{%s}ExtensionContent" % NS_EXT)
    signed.remove(sig)
    content.append(sig)
    return etree.tostring(signed, xml_declaration=True, encoding="UTF-8", standalone=False)

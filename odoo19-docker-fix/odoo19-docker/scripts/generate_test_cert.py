"""Genera un certificado digital AUTOFIRMADO (.pfx) para pruebas en el ambiente BETA de SUNAT.

Uso:   python3 scripts/generate_test_cert.py [RUC] [clave]
Salida: certs/beta_test.pfx

NO sirve para producción: allí SUNAT exige un certificado emitido por una entidad acreditada
(INDECOPI / Reniec u otra ECEP/EC).
"""
import datetime
import sys

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

ruc = sys.argv[1] if len(sys.argv) > 1 else "20000000001"
password = sys.argv[2] if len(sys.argv) > 2 else "beta1234"

key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([
    x509.NameAttribute(NameOID.COUNTRY_NAME, "PE"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EMPRESA DE PRUEBA SAC"),
    x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, ruc),
    x509.NameAttribute(NameOID.COMMON_NAME, "EMPRESA DE PRUEBA SAC"),
])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=730))
        .sign(key, hashes.SHA256()))
data = pkcs12.serialize_key_and_certificates(
    b"beta", key, cert, None, serialization.BestAvailableEncryption(password.encode()))
with open("certs/beta_test.pfx", "wb") as fh:
    fh.write(data)
print("Certificado creado: certs/beta_test.pfx | clave: %s | RUC: %s | vence: %s" % (
    password, ruc, (now + datetime.timedelta(days=730)).date()))

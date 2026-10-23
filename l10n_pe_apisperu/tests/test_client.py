"""Pruebas del cliente APIsPERU. Corren con Odoo o solas (python3 -m unittest)."""
from unittest import mock

import requests

try:
    from odoo.tests.common import BaseCase as Base, tagged
    from ..services import client
except ImportError:  # ejecución fuera de Odoo
    import importlib.util
    import pathlib
    import unittest

    Base = unittest.TestCase

    def tagged(*args, **kwargs):
        return lambda cls: cls

    _spec = importlib.util.spec_from_file_location(
        "apisperu_client", pathlib.Path(__file__).resolve().parent.parent / "services" / "client.py")
    client = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(client)

TOKEN = "SECRET-TOKEN-123"
VALID_RUC = "20131312955"  # RUC público de SUNAT (dígito verificador correcto)


def fake_response(status=200, json_data=None, text_json=True):
    resp = mock.Mock()
    resp.status_code = status
    if text_json:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


DNI_OK = {"dni": "12345678", "nombres": "JUAN CARLOS", "apellidoPaterno": "PEREZ",
          "apellidoMaterno": "GOMEZ", "codVerifica": 3}


@tagged("post_install", "-at_install")
class TestApisPeruClient(Base):
    # ------------------------------------------------------------ DNI correcto
    @mock.patch.object(client.requests, "get")
    def test_dni_ok(self, get):
        get.return_value = fake_response(200, DNI_OK)
        data = client.lookup_dni(" 1234-5678 ", TOKEN)
        self.assertEqual(data["document"], "12345678")
        self.assertEqual(data["check_digit"], "3")
        url = get.call_args[0][0]
        self.assertTrue(url.endswith("/dni/12345678"))
        self.assertEqual(get.call_args[1]["params"], {"token": TOKEN})

    def test_name_formats(self):
        data = {"first_names": "JUAN CARLOS", "last_name_paternal": "PEREZ", "last_name_maternal": "GOMEZ"}
        self.assertEqual(client.build_full_name(data), "PEREZ GOMEZ JUAN CARLOS")
        self.assertEqual(client.build_full_name(data, "first_last"), "JUAN CARLOS PEREZ GOMEZ")
        data["last_name_maternal"] = ""
        self.assertEqual(client.build_full_name(data), "PEREZ JUAN CARLOS")

    # ------------------------------------------------------------ validación local (no gasta consultas)
    @mock.patch.object(client.requests, "get")
    def test_invalid_numbers_do_not_call_api(self, get):
        for bad in ("1234567", "123456789", "abc", ""):
            with self.assertRaises(client.ApisPeruError) as ctx:
                client.lookup_dni(bad, TOKEN)
            self.assertEqual(ctx.exception.code, "invalid")
        for bad in ("20131312950", "30131312955", "2013131295"):  # dígito malo, prefijo malo, corto
            with self.assertRaises(client.ApisPeruError):
                client.lookup_ruc(bad, TOKEN)
        get.assert_not_called()

    def test_ruc_checksum(self):
        self.assertTrue(client.ruc_checksum_ok(VALID_RUC))
        self.assertFalse(client.ruc_checksum_ok("20131312954"))

    def test_missing_token(self):
        with self.assertRaises(client.ApisPeruError) as ctx:
            client.lookup_dni("12345678", "")
        self.assertEqual(ctx.exception.code, "config")

    # ------------------------------------------------------------ errores HTTP
    @mock.patch.object(client.requests, "get")
    def test_http_errors(self, get):
        cases = {401: "auth", 403: "auth", 404: "not_found", 429: "quota", 422: "invalid",
                 500: "server", 503: "server", 418: "response"}
        for status, code in cases.items():
            get.return_value = fake_response(status, {"message": "x"})
            with self.assertRaises(client.ApisPeruError) as ctx:
                client.lookup_dni("12345678", TOKEN)
            self.assertEqual(ctx.exception.code, code, "HTTP %s" % status)

    @mock.patch.object(client.requests, "get")
    def test_success_false_bodies(self, get):
        get.return_value = fake_response(200, {"success": False, "message": "Token inválido"})
        with self.assertRaises(client.ApisPeruError) as ctx:
            client.lookup_dni("12345678", TOKEN)
        self.assertEqual(ctx.exception.code, "auth")
        get.return_value = fake_response(200, {"success": False, "message": "No se encontró el DNI"})
        with self.assertRaises(client.ApisPeruError) as ctx:
            client.lookup_dni("12345678", TOKEN)
        self.assertEqual(ctx.exception.code, "not_found")

    @mock.patch.object(client.requests, "get")
    def test_bad_bodies(self, get):
        get.return_value = fake_response(200, text_json=False)  # no es JSON
        with self.assertRaises(client.ApisPeruError) as ctx:
            client.lookup_dni("12345678", TOKEN)
        self.assertEqual(ctx.exception.code, "response")
        get.return_value = fake_response(200, {"dni": "12345678", "nombres": "", "apellidoPaterno": "",
                                               "apellidoMaterno": ""})  # vacío => no encontrado
        with self.assertRaises(client.ApisPeruError) as ctx:
            client.lookup_dni("12345678", TOKEN)
        self.assertEqual(ctx.exception.code, "not_found")

    # ------------------------------------------------------------ red y SEGURIDAD del token
    @mock.patch.object(client.requests, "get")
    def test_network_errors_never_leak_token(self, get):
        leaky = "HTTPSConnectionPool: Max retries exceeded with url: /api/v1/dni/12345678?token=%s" % TOKEN
        for exc in (requests.Timeout(leaky), requests.ConnectionError(leaky), requests.RequestException(leaky)):
            get.side_effect = exc
            with self.assertRaises(client.ApisPeruError) as ctx:
                client.lookup_dni("12345678", TOKEN)
            self.assertEqual(ctx.exception.code, "network")
            self.assertNotIn(TOKEN, ctx.exception.message)
            self.assertNotIn(TOKEN, str(ctx.exception))
            self.assertIsNone(ctx.exception.__cause__)  # no encadena la excepción original (trae la URL)

    @mock.patch.object(client.requests, "get")
    def test_error_messages_never_contain_token(self, get):
        for status in (401, 404, 429, 500):
            get.return_value = fake_response(status, {"message": "ok"})
            with self.assertRaises(client.ApisPeruError) as ctx:
                client.lookup_dni("12345678", TOKEN)
            self.assertNotIn(TOKEN, ctx.exception.message)

    # ------------------------------------------------------------ RUC
    @mock.patch.object(client.requests, "get")
    def test_ruc_ok(self, get):
        get.return_value = fake_response(200, {
            "ruc": VALID_RUC, "razonSocial": "EMPRESA DE PRUEBA SAC", "nombreComercial": "-",
            "telefonos": ["999999999"], "estado": "ACTIVO", "condicion": "HABIDO",
            "direccion": "AV. PRUEBA 123", "departamento": "LIMA", "provincia": "LIMA",
            "distrito": "MIRAFLORES", "ubigeo": "150122"})
        data = client.lookup_ruc(VALID_RUC, TOKEN)
        self.assertEqual(data["name"], "EMPRESA DE PRUEBA SAC")
        self.assertEqual(data["trade_name"], "")
        self.assertEqual(data["district"], "MIRAFLORES")

    def test_mask(self):
        self.assertEqual(client.mask("12345678"), "12****78")
        self.assertEqual(client.mask("20131312955"), "20*******55")
        self.assertNotIn("3456", client.mask("12345678"))

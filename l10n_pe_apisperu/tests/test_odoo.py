from unittest import mock

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from ..services import client

DNI_OK = {"dni": "12345678", "nombres": "JUAN CARLOS", "apellidoPaterno": "PEREZ",
          "apellidoMaterno": "GOMEZ", "codVerifica": 3}


def fake_response(status=200, json_data=None):
    resp = mock.Mock()
    resp.status_code = status
    resp.json.return_value = json_data
    return resp


@tagged("post_install", "-at_install")
class TestApisPeruOdoo(TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.company.sudo().write({"apisperu_token": "TOKEN-TEST", "apisperu_name_format": "last_first"})

    def test_lookup_fills_partner_name(self):
        partner = self.env["res.partner"].create({"name": "12345678", "vat": "12345678"})
        with mock.patch.object(client.requests, "get", return_value=fake_response(200, DNI_OK)):
            partner.action_apisperu_lookup()
        self.assertEqual(partner.name, "PEREZ GOMEZ JUAN CARLOS")
        self.assertFalse(partner.is_company)

    def test_name_format_first_last(self):
        self.company.sudo().apisperu_name_format = "first_last"
        partner = self.env["res.partner"].create({"name": "x", "vat": "12345678"})
        with mock.patch.object(client.requests, "get", return_value=fake_response(200, DNI_OK)):
            partner.action_apisperu_lookup()
        self.assertEqual(partner.name, "JUAN CARLOS PEREZ GOMEZ")

    def test_error_becomes_user_error_without_token_leak(self):
        with mock.patch.object(client.requests, "get", return_value=fake_response(401, {"message": "x"})):
            with self.assertRaises(UserError) as ctx:
                self.env["apisperu.service"].lookup_dni("12345678")
        self.assertNotIn("TOKEN-TEST", str(ctx.exception))

    def test_invalid_number_does_not_call_api_nor_log(self):
        before = self.env["apisperu.log"].sudo().search_count([])
        with mock.patch.object(client.requests, "get") as get:
            with self.assertRaises(UserError):
                self.env["apisperu.service"].lookup_dni("123")
        get.assert_not_called()
        self.assertEqual(self.env["apisperu.log"].sudo().search_count([]), before)

    def test_log_is_masked(self):
        with mock.patch.object(client.requests, "get", return_value=fake_response(200, DNI_OK)):
            self.env["apisperu.service"].lookup_dni("12345678")
        log = self.env["apisperu.log"].sudo().search([], limit=1)
        self.assertEqual(log.masked_number, "12****78")
        self.assertTrue(log.success)

    def test_bulk_stops_on_first_error(self):
        partners = self.env["res.partner"].create([
            {"name": "11111111", "vat": "11111111"}, {"name": "22222222", "vat": "22222222"}])
        with mock.patch.object(client.requests, "get", return_value=fake_response(429, {})) as get:
            partners.action_apisperu_fill_names()
        self.assertEqual(get.call_count, 1)  # no sigue gastando consultas tras el límite

    def test_bulk_skips_partners_with_real_name(self):
        partner = self.env["res.partner"].create({"name": "MARIA LOPEZ", "vat": "12345678"})
        with mock.patch.object(client.requests, "get") as get:
            partner.action_apisperu_fill_names()
        get.assert_not_called()

    def test_wizard_creates_partner(self):
        wiz = self.env["apisperu.lookup.wizard"].create({"kind": "dni", "number": "12345678"})
        with mock.patch.object(client.requests, "get", return_value=fake_response(200, DNI_OK)):
            wiz.action_lookup()
        self.assertEqual(wiz.state, "done")
        action = wiz.action_create_partner()
        partner = self.env["res.partner"].browse(action["res_id"])
        self.assertEqual(partner.vat, "12345678")
        self.assertEqual(partner.name, "PEREZ GOMEZ JUAN CARLOS")

    def test_token_hidden_from_regular_users(self):
        user = self.env["res.users"].with_context(no_reset_password=True).create(
            {"name": "Usuario", "login": "apisperu_user"})  # por defecto: usuario interno
        company = self.company.with_user(user)
        with self.assertRaises(Exception):
            company.apisperu_token  # noqa: B018 - protegido por grupo base.group_system

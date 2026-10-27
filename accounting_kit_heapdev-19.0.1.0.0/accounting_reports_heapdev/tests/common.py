# -*- coding: utf-8 -*-
"""Shared fixtures for the heapdev accounting kit tests (Odoo 14-20, any chart of accounts)."""
from datetime import date

from odoo import release
from odoo.tests import common as _tc

V = release.version_info[0]
# Odoo 14: only SavepointCase sets up cls.env in setUpClass; 15+ TransactionCase does
_BaseCase = _tc.SavepointCase if V <= 14 else _tc.TransactionCase
TYPES14 = {
    "income": "account.data_account_type_revenue", "expense": "account.data_account_type_expenses",
    "asset_current": "account.data_account_type_current_assets", "liability_current": "account.data_account_type_current_liabilities",
    "asset_receivable": "account.data_account_type_receivable", "liability_payable": "account.data_account_type_payable",
    "asset_fixed": "account.data_account_type_fixed_assets", "asset_cash": "account.data_account_type_liquidity",
    "equity": "account.data_account_type_equity",
}


class AccKitCase(_BaseCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True, mail_create_nolog=True, mail_notrack=True))
        cls.company = cls.env.company
        cls.currency = cls.company.currency_id
        Journal = cls.env["account.journal"]
        cls.misc = Journal.search([("type", "=", "general"), ("company_id", "=", cls.company.id)], limit=1)
        cls.bank = Journal.search([("type", "=", "bank"), ("company_id", "=", cls.company.id)], limit=1)
        cls.sale_journal = Journal.search([("type", "=", "sale"), ("company_id", "=", cls.company.id)], limit=1)
        if not (cls.misc and cls.bank and cls.sale_journal):
            cls.skip_all = True
            return
        cls.skip_all = False
        cls.acc_income = cls._account("T90001", "Test Income", "income")
        cls.acc_expense = cls._account("T90002", "Test Expense", "expense")
        cls.acc_fixed = cls._account("T90003", "Test Fixed Asset", "asset_fixed")
        cls.acc_accum = cls._account("T90004", "Test Accumulated Depreciation", "asset_fixed")
        cls.acc_current = cls._account("T90005", "Test Current Asset", "asset_current", reconcile=True)
        cls.acc_liab = cls._account("T90006", "Test Current Liability", "liability_current", reconcile=True)
        cls.partner = cls.env["res.partner"].create({"name": "Heapdev Test Customer"})

    @classmethod
    def _account(cls, code, name, atype, reconcile=False):
        vals = {"code": code, "name": name, "reconcile": reconcile}
        if V <= 15:
            vals["user_type_id"] = cls.env.ref(TYPES14[atype]).id
        else:
            vals["account_type"] = atype
        if V < 18:
            vals["company_id"] = cls.company.id
        else:
            vals["company_ids"] = [(6, 0, cls.company.ids)]
        return cls.env["account.account"].create(vals)

    def setUp(self):
        super().setUp()
        if self.skip_all:
            self.skipTest("company has no chart of accounts / journals")

    def _entry(self, day, debit_acc, credit_acc, amount, partner=None, post=True):
        move = self.env["account.move"].create({
            "move_type": "entry", "date": day, "journal_id": self.misc.id, "ref": "heapdev test",
            "line_ids": [(0, 0, {"name": "d", "account_id": debit_acc.id, "debit": amount, "credit": 0.0, "partner_id": partner and partner.id}),
                         (0, 0, {"name": "c", "account_id": credit_acc.id, "debit": 0.0, "credit": amount, "partner_id": partner and partner.id})]})
        if post:
            move.action_post()
        return move

    def _invoice(self, day, amount, due=None, move_type="out_invoice", account=None):
        vals = {"move_type": move_type, "partner_id": self.partner.id, "invoice_date": day, "date": day,
                "invoice_line_ids": [(0, 0, {"name": "Service", "quantity": 1, "price_unit": amount,
                                             "account_id": (account or (self.acc_income if move_type == "out_invoice" else self.acc_expense)).id,
                                             "tax_ids": [(6, 0, [])]})]}
        if due:
            vals["invoice_date_due"] = due
        move = self.env["account.move"].create(vals)
        move.action_post()
        return move


TODAY = date.today()
Y0 = date(TODAY.year, 1, 1)

# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestPettyCashBook(TransactionCase):

    def setUp(self):
        super().setUp()
        self.book = self.env["petty.cash.book"].create({
            "name": "Front Desk", "opening_balance": 100.0})

    def test_balance_computation(self):
        self.env["petty.cash.line"].create([
            {"book_id": self.book.id, "name": "Float top-up", "line_type": "in",
             "amount": 50.0},
            {"book_id": self.book.id, "name": "Stationery", "line_type": "out",
             "amount": 30.0},
            {"book_id": self.book.id, "name": "Taxi", "line_type": "out",
             "amount": 20.0},
        ])
        self.assertAlmostEqual(self.book.total_in, 50.0)
        self.assertAlmostEqual(self.book.total_out, 50.0)
        self.assertAlmostEqual(self.book.balance, 100.0)  # 100 + 50 - 50
        self.assertEqual(self.book.line_count, 3)

    def test_signed_amount(self):
        line = self.env["petty.cash.line"].create({
            "book_id": self.book.id, "name": "Refund", "line_type": "in", "amount": 15.0})
        self.assertAlmostEqual(line.signed_amount, 15.0)
        line.line_type = "out"
        self.assertAlmostEqual(line.signed_amount, -15.0)

    def test_positive_amount_enforced(self):
        with self.assertRaises(ValidationError):
            self.env["petty.cash.line"].create({
                "book_id": self.book.id, "name": "Bad", "line_type": "out", "amount": 0.0})

    def test_report_renders(self):
        self.env["petty.cash.line"].create({
            "book_id": self.book.id, "name": "Snacks", "line_type": "out", "amount": 12.0})
        report = self.env["ir.actions.report"]._render_qweb_pdf(
            "petty_cash_book.action_report_petty_cash", self.book.ids)
        self.assertTrue(report[0])

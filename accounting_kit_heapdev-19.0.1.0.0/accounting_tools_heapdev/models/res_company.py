# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    acc_pdc_receivable_account_id = fields.Many2one("account.account", string="PDC Receivable Account",
                                                    help="Holds received post dated cheques until they are cleared.")
    acc_pdc_payable_account_id = fields.Many2one("account.account", string="PDC Payable Account",
                                                 help="Holds issued post dated cheques until they are presented.")

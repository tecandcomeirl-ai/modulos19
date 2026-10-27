# -*- coding: utf-8 -*-
from odoo import _, fields, models


class AccFollowupRun(models.TransientModel):
    _name = "acc.followup.run"
    _description = "Run Customer Follow-ups"

    date = fields.Date(default=fields.Date.context_today, required=True)
    level_ids = fields.Many2many("acc.followup.level", string="Levels", help="Leave empty for all levels.")
    send_emails = fields.Boolean(string="Send Emails", default=True)
    print_letters = fields.Boolean(string="Print Letters", default=True)
    create_activities = fields.Boolean(string="Schedule Manual Actions", default=True)
    only_due = fields.Boolean(string="Only Partners With Action Due", default=True)

    def _partners(self):
        Partner = self.env["res.partner"]
        partners = Partner.search([("acc_has_overdue", "=", True), ("parent_id", "=", False)])
        if self.only_due:
            partners = partners.filtered(lambda p: not p.acc_followup_next_date or p.acc_followup_next_date <= self.date)
        if self.level_ids:
            partners = partners.filtered(lambda p: p.acc_followup_level_id in self.level_ids)
        return partners.filtered(lambda p: p.acc_followup_level_id)

    def action_run(self):
        self.ensure_one()
        partners = self._partners()
        to_print = self.env["res.partner"]
        emailed = 0
        activity_type = self.env.ref("mail.mail_activity_data_todo", raise_if_not_found=False)
        for p in partners:
            lvl = p.acc_followup_level_id
            if self.send_emails and lvl.send_email and p.email:
                att = p._acc_statement_pdf()
                p.message_post(body=p._acc_email_body(), subject=_("%s - Payment reminder") % self.env.company.name,
                               partner_ids=[p.id], attachment_ids=att.ids if att else [], message_type="comment",
                               subtype_xmlid="mail.mt_comment")
                emailed += 1
            if self.print_letters and lvl.print_letter:
                to_print |= p
            if self.create_activities and lvl.manual_action and activity_type:
                p.activity_schedule(activity_type_id=activity_type.id, summary=_("Follow-up: %s") % lvl.name,
                                    note=lvl.manual_action_note or "", user_id=(p.acc_followup_responsible_id or self.env.user).id)
        partners._acc_mark_followed()
        if to_print:
            return self.env.ref("accounting_followup_heapdev.action_report_acc_customer_statement").report_action(to_print)
        return {"type": "ir.actions.client", "tag": "display_notification",
                "params": {"title": _("Follow-ups done"), "type": "success",
                           "message": _("%(p)s customers processed, %(e)s reminders sent.") % {"p": len(partners), "e": emailed},
                           "next": {"type": "ir.actions.act_window_close"}}}

from odoo import _, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    bca_exchange_rate_enabled = fields.Boolean(
        related="company_id.bca_exchange_rate_enabled",
        readonly=False,
    )
    bca_exchange_rate_type = fields.Selection(
        related="company_id.bca_exchange_rate_type",
        readonly=False,
    )
    bca_exchange_rate_value = fields.Selection(
        related="company_id.bca_exchange_rate_value",
        readonly=False,
    )
    bca_exchange_rate_currency_ids = fields.Many2many(
        related="company_id.bca_exchange_rate_currency_ids",
        readonly=False,
    )
    bca_exchange_rate_last_update = fields.Datetime(
        related="company_id.bca_exchange_rate_last_update",
        readonly=True,
    )
    bca_exchange_rate_last_message = fields.Char(
        related="company_id.bca_exchange_rate_last_message",
        readonly=True,
    )

    def action_update_bca_exchange_rates(self):
        self.ensure_one()
        message = self.company_id.action_update_bca_exchange_rates()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("BCA Exchange Rate"),
                "message": message,
                "type": "success",
                "sticky": False,
            },
        }

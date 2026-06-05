import logging
import re
from datetime import date

from lxml import html

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    bca_exchange_rate_enabled = fields.Boolean(string="Enable BCA Exchange Rate")
    bca_exchange_rate_type = fields.Selection(
        [
            ("e_rate", "E-Rate"),
            ("tt_counter", "TT Counter"),
            ("bank_notes", "Bank Notes"),
        ],
        string="BCA Rate Type",
        default="e_rate",
        required=True,
    )
    bca_exchange_rate_value = fields.Selection(
        [
            ("mid", "Middle"),
            ("buy", "Buy"),
            ("sell", "Sell"),
        ],
        string="BCA Rate Value",
        default="mid",
        required=True,
    )
    bca_exchange_rate_currency_ids = fields.Many2many(
        "res.currency",
        "res_company_bca_exchange_rate_currency_rel",
        "company_id",
        "currency_id",
        string="Currencies Updated from BCA",
        domain=[("name", "!=", "IDR")],
    )
    bca_exchange_rate_last_update = fields.Datetime(
        string="Last BCA Update",
        readonly=True,
    )
    bca_exchange_rate_last_message = fields.Char(
        string="Last BCA Message",
        readonly=True,
    )

    def _bca_fetch_exchange_rates(self):
        """Return BCA rates keyed by ISO currency code.

        BCA publishes rates as IDR per one foreign currency unit on its kurs page.
        The HTML contains both desktop and mobile tables; duplicate currency rows are
        intentionally ignored after the first parsed occurrence.
        """
        try:
            import requests
        except ImportError as exc:
            raise UserError(_("Python library 'requests' is required to fetch BCA exchange rates.")) from exc

        url = "https://www.bca.co.id/id/informasi/kurs/"
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; Odoo BCA Exchange Rate/16.0)",
            "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
        except Exception as exc:
            raise UserError(_("Unable to fetch BCA exchange rates: %s") % exc) from exc

        document = html.fromstring(response.content)
        text_items = [
            item.strip()
            for item in document.xpath("//body//*[not(self::script) and not(self::style)]/text()")
            if item and item.strip()
        ]

        rates = {}
        currency_pattern = re.compile(r"^[A-Z]{3}$")
        number_pattern = re.compile(r"^\d{1,3}(?:[.,]\d{3})*(?:,\d+)?$|^\d+(?:,\d+)?$")
        labels = {"E-Rate", "TT Counter", "Bank Notes", "Beli", "Jual"}

        index = 0
        while index < len(text_items):
            code = text_items[index]
            if not currency_pattern.match(code) or code == "IDR" or code in rates:
                index += 1
                continue

            values = []
            cursor = index + 1
            while cursor < len(text_items) and len(values) < 6:
                token = text_items[cursor]
                if currency_pattern.match(token) and token not in labels:
                    break
                if number_pattern.match(token):
                    values.append(self._bca_parse_number(token))
                cursor += 1

            if len(values) == 6:
                rates[code] = {
                    "e_rate": {"buy": values[0], "sell": values[1]},
                    "tt_counter": {"buy": values[2], "sell": values[3]},
                    "bank_notes": {"buy": values[4], "sell": values[5]},
                }
            index += 1

        if not rates:
            raise UserError(_("No BCA exchange rates were found on the BCA kurs page."))
        return rates

    @api.model
    def _bca_parse_number(self, value):
        return float(value.replace(".", "").replace(",", "."))

    def _bca_get_company_rate(self, rates, currency_name):
        self.ensure_one()
        currency_rates = rates.get(currency_name)
        if not currency_rates:
            return False
        selected_rate = currency_rates[self.bca_exchange_rate_type]
        buy = selected_rate["buy"]
        sell = selected_rate["sell"]
        if self.bca_exchange_rate_value == "buy":
            return buy
        if self.bca_exchange_rate_value == "sell":
            return sell
        return (buy + sell) / 2.0

    def action_update_bca_exchange_rates(self):
        self.ensure_one()
        if self.currency_id.name != "IDR":
            raise UserError(_("BCA exchange rate update requires the company currency to be IDR."))

        currencies = self.bca_exchange_rate_currency_ids.filtered(lambda currency: currency.active)
        if not currencies:
            raise UserError(_("Please select at least one active currency to update from BCA."))

        bca_rates = self._bca_fetch_exchange_rates()
        today = fields.Date.context_today(self)
        Rate = self.env["res.currency.rate"].sudo()
        updated = []
        skipped = []

        for currency in currencies:
            inverse_company_rate = self._bca_get_company_rate(bca_rates, currency.name)
            if not inverse_company_rate:
                skipped.append(currency.name)
                continue

            existing_rate = Rate.search(
                [
                    ("name", "=", today),
                    ("currency_id", "=", currency.id),
                    ("company_id", "=", self.id),
                ],
                limit=1,
            )
            values = {
                "name": today,
                "currency_id": currency.id,
                "company_id": self.id,
                "inverse_company_rate": inverse_company_rate,
            }
            if existing_rate:
                existing_rate.write(values)
            else:
                Rate.create(values)
            updated.append(currency.name)

        if not updated:
            raise UserError(_("No selected currencies were available from BCA. Missing: %s") % ", ".join(skipped))

        message = _("Updated %s currency rate(s): %s") % (len(updated), ", ".join(updated))
        if skipped:
            message += _("; skipped: %s") % ", ".join(skipped)
        self.write(
            {
                "bca_exchange_rate_last_update": fields.Datetime.now(),
                "bca_exchange_rate_last_message": message,
            }
        )
        return message

    @api.model
    def _cron_update_bca_exchange_rates(self):
        companies = self.search([("bca_exchange_rate_enabled", "=", True)])
        for company in companies:
            try:
                company.action_update_bca_exchange_rates()
            except Exception as exc:
                _logger.exception("BCA exchange rate update failed for company %s", company.display_name)
                company.sudo().write(
                    {
                        "bca_exchange_rate_last_update": fields.Datetime.now(),
                        "bca_exchange_rate_last_message": _("Update failed: %s") % exc,
                    }
                )

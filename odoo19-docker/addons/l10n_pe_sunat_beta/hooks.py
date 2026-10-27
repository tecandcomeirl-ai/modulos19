import logging

from .models.account_tax import sunat_guess_from_tax

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Clasifica los impuestos de venta existentes (IGV, exonerado, inafecto...)."""
    taxes = env["account.tax"].with_context(active_test=False).search(
        [("type_tax_use", "=", "sale"), ("sunat_tax_code", "=", False)]
    )
    for tax in taxes:
        code, afect = sunat_guess_from_tax(tax.name, tax.amount)
        if code:
            tax.write({"sunat_tax_code": code, "sunat_afectacion": afect})
    _logger.info("SUNAT: %s impuestos clasificados", len(taxes))

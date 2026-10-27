from .models.uom import guess_uom_codes


def post_init_hook(env):
    """Completa los códigos SUNAT de las unidades de medida existentes."""
    for uom in env["uom.uom"].with_context(active_test=False).search([]):
        gre_code, ple_code = guess_uom_codes(uom.name)
        vals = {}
        if not uom.sunat_uom_code:
            vals["sunat_uom_code"] = gre_code
        if not uom.sunat_ple_uom_code:
            vals["sunat_ple_uom_code"] = ple_code
        if vals:
            uom.write(vals)

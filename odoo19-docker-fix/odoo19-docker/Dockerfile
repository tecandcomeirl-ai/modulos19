FROM odoo:19.0

USER root

# Dependencias Python del módulo l10n_pe_sunat_beta (firma XMLDSig + SOAP)
ENV PIP_BREAK_SYSTEM_PACKAGES=1
COPY addons/l10n_pe_sunat_beta/requirements.txt /tmp/requirements.txt
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

USER odoo

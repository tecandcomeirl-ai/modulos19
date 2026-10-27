comma := ,
DB ?= odoo19
MODULE ?= l10n_pe_sunat_beta
ALL_MODULES = l10n_pe,l10n_pe_sunat_beta,l10n_pe_sunat_gre,l10n_pe_sunat_consulta,l10n_pe_sunat_edi,l10n_pe_sunat_detraccion,l10n_pe_edi_stock,l10n_pe_reports,l10n_pe_reports_stock

up:        ; docker compose up -d --build
proxy:     ; docker compose --profile proxy up -d --build
down:      ; docker compose down
logs:      ; docker compose logs -f odoo
restart:   ; docker compose restart odoo
shell:     ; docker compose exec odoo odoo shell -d $(DB)
install:   ; docker compose exec odoo odoo -d $(DB) -i $(MODULE) --stop-after-init
install-all: ; docker compose exec odoo odoo -d $(DB) -i $(ALL_MODULES) --stop-after-init
update-all: ; docker compose exec odoo odoo -d $(DB) -u $(subst l10n_pe$(comma),,$(ALL_MODULES)) --stop-after-init
update:    ; docker compose exec odoo odoo -d $(DB) -u $(MODULE) --stop-after-init
test:      ; docker compose exec odoo odoo -d $(DB) -u $(ALL_MODULES) --test-tags $(subst $(comma),$(comma)/,/$(subst l10n_pe$(comma),,$(ALL_MODULES))) --stop-after-init
backup:    ; docker compose exec -T db pg_dump -U odoo $(DB) > backup_$(DB).sql
reset-db:  ; docker compose down -v && docker compose up -d --build
fix-pass:  ; . ./.env && docker compose exec db psql -U $$POSTGRES_USER -d postgres -c "ALTER USER $$POSTGRES_USER WITH PASSWORD '$$POSTGRES_PASSWORD';"
seed:      ; docker compose exec -T odoo odoo shell -d $(DB) < scripts/seed_beta.py
cert:      ; python3 scripts/generate_test_cert.py

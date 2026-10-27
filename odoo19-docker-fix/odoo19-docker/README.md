# Odoo 19 Community + Contabilidad Perú + SUNAT (CPE, GRE, detracciones, PLE, inventario)

## Módulos (`addons/`)
| Módulo | Qué hace |
|---|---|
| `l10n_pe_sunat_beta` | **Base**: Factura, Boleta, NC, ND (UBL 2.1, firma, `sendBill`, CDR) y Nota de venta interna |
| `l10n_pe_sunat_gre` | Guía de Remisión Electrónica remitente (API REST, ticket, CDR) |
| `l10n_pe_sunat_consulta` | Consulta de validez de comprobantes (API REST) y recuperación de CDR (producción) |
| `l10n_pe_sunat_edi` | **Capa EDI**: envío automático/cron, reintentos, resumen diario RC, bajas RA, PDF con QR, correo |
| `l10n_pe_sunat_detraccion` | Detracciones SPOT: catálogo, cálculo y bloque en el XML |
| `l10n_pe_edi_stock` | Conductores, vehículos, almacén anexo, GRE automática desde Inventario, códigos de unidad/existencia |
| `l10n_pe_reports` | Libros PLE: Ventas 14.1, Compras 8.1, Diario 5.1, Plan contable 5.3 (+ Excel de respaldo) |
| `l10n_pe_reports_stock` | Inventario permanente PLE 12.1 (físico) y 13.1 (valorizado) |

> **Nombres.** `l10n_pe_reports`, `l10n_pe_edi_stock` y `l10n_pe_reports_stock` coinciden con módulos de **Odoo
> Enterprise**. Estos son versiones Community independientes: no los uses junto con los de Enterprise ni
> agregues el repositorio enterprise al `addons_path`.

## Servicios Docker
| Servicio | Contenedor | Puerto | Función |
|---|---|---|---|
| db | odoo19_db | interno | PostgreSQL 16 |
| odoo | odoo19_web | 8069 / 8072 | Odoo 19 |
| nginx | odoo19_nginx | 80 | Proxy inverso (opcional, `--profile proxy`) |

Carpetas montadas: `addons/`, `scripts/` (solo lectura), `certs/` (solo lectura).

## 1. Instalación
1. Cambia las claves en `.env` (la de PostgreSQL se define **solo ahí**) y `admin_passwd` en `config/odoo.conf`.
2. `docker compose up -d --build`
3. Crea la base en http://localhost:8069/web/database/manager con **País = Perú** (instala `l10n_pe`).
4. Instala todo:
```
docker compose exec odoo odoo -d odoo19 -i l10n_pe,l10n_pe_sunat_beta,l10n_pe_sunat_gre,l10n_pe_sunat_consulta,l10n_pe_sunat_edi,l10n_pe_sunat_detraccion,l10n_pe_edi_stock,l10n_pe_reports,l10n_pe_reports_stock --stop-after-init
docker compose restart odoo
```
(con `make`: `make install-all DB=odoo19`). Datos de prueba: ver `docs/GUIA_PRUEBAS_BETA.md` §2.3.

## 2. Configuración (Ajustes > Compañías > pestaña SUNAT)
| Bloque | Datos |
|---|---|
| Facturación (SOAP) | Ambiente beta, `MODDATOS` / `moddatos`, certificado `.pfx` + clave, ubigeo |
| EDI automatizado | Envío manual / al publicar / cron; boletas individual o resumen; correo; reintentos |
| Detracciones | Cuenta del Banco de la Nación, redondeo al sol |
| GRE (REST) | Client ID/Secret de «Credenciales de API SUNAT», serie `T001`, ambiente |
| Consulta de validez | Client ID/Secret de «Consulta de Validez de CPE» (credenciales distintas a las de GRE) |
| Libros electrónicos | ¿Incorporada al SIRE? |

Además: diarios de venta con **«Usar documentos»**; impuestos con *Tributo SUNAT* y *Afectación* (se completan solos).

## 3. Uso rápido
- **Factura / boleta / NC / ND**: publicar > *Enviar a SUNAT*. NC y ND se crean desde el comprobante original.
- **Nota de venta**: tipo *Nota de venta (interna)*; numera `NV01-…`; no se envía.
- **Detracción**: producto con código de detracción → la factura calcula tasa y monto; va en el XML.
- **Resumen / baja**: SUNAT > *Resúmenes y bajas*; botón *Dar de baja en SUNAT* en comprobantes aceptados.
- **GRE**: en la operación de inventario > pestaña *GRE SUNAT* > *Generar GRE*; o automática por tipo de operación.
- **Consulta**: SUNAT > *Consultar comprobante*, o *Validar en SUNAT* en facturas de cliente/proveedor.
- **Libros**: SUNAT > *Libros electrónicos (PLE)* > nuevo > libro, año, mes > *Generar libro* (TXT oficial + Excel).

## 4. Pruebas
`docs/GUIA_PRUEBAS_BETA.md`: 25 casos de prueba, 7 negativos, plantilla de resultados y checklist de paso a producción.
`make test DB=odoo19` ejecuta las pruebas automáticas de los módulos.

## 5. Comandos
```
docker compose logs -f odoo
make update-all DB=odoo19         # actualizar módulos tras cambios
docker compose down               # conserva datos
docker compose down -v            # BORRA datos
```

## 6. Solución de problemas
**`password authentication failed for user "odoo"`**: PostgreSQL fija la clave al crear el volumen. Usa
`docker compose down -v` (borra datos) o `ALTER USER odoo WITH PASSWORD '...'` en el contenedor `db`. No pongas
`db_password` en `odoo.conf`.

## 7. Alcance y límites (léase antes de producción)
- **Nada de esto se ha ejecutado contra SUNAT ni en un Odoo real.** Se verificó sintaxis, estructura de los
  XML/TXT y la lógica con datos simulados (campos por libro PLE, kárdex, nombres de archivo oficiales).
- **GRE**: SUNAT no documenta beta; el ambiente de pruebas es una URL configurable (sandbox de terceros).
- **SIRE**: ventas y compras migraron al SIRE; los TXT 14.1/8.1 sirven a quien no esté incorporado y como respaldo.
- **PLE**: la estructura 14.1, 8.1, 12.1 y 13.1 sigue el anexo oficial de la RS 108-2020/SUNAT. Las estructuras
  5.1 y 5.3, las Tablas 6, 12 y 14 (unidad de medida, tipo de operación, método de valuación) y las tasas de
  detracción se tomaron de fuentes secundarias o de memoria: **verifíquelas** con el PLE vigente y el Anexo de SUNAT.
- **Libro Mayor 6.1 y asientos de apertura/cierre (A/C)** no están implementados.
- **Detracciones**: no genera los asientos contables de la detracción ni el archivo de pago masivo del Banco de la Nación.
- **Inventario 13.1**: toma el valor de `stock.move.value` (Odoo 19 eliminó `stock.valuation.layer`); el método de
  valuación y el tipo de operación se infieren y pueden requerir ajuste.
- No cubre: operaciones gratuitas, ICBPER, descuentos globales, retención, percepción, anticipos, GRE transportista.
- No lo mezcle con los módulos EDI de Odoo Enterprise (`l10n_pe_edi`): duplicaría el envío.

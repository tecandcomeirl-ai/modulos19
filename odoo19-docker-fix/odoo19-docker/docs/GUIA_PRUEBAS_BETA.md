# Guía de pruebas en beta SUNAT — Odoo 19 (módulos `l10n_pe_*`)

Esta guía te lleva de cero a validar **factura, boleta, nota de crédito, nota de débito, resumen diario (RC),
comunicación de baja (RA), detracción, guía de remisión (GRE), consulta de comprobantes, libros PLE e
inventario**. Cada caso indica datos, pasos, resultado esperado y qué revisar.

> **Estado de lo que vas a probar.** El código se revisó por sintaxis y con pruebas unitarias de los
> generadores XML y de los libros PLE, pero **nunca se ejecutó contra SUNAT**. Esta guía existe para
> descubrir lo que falte. Anota cada resultado en la plantilla de la sección 7.

---

## 1. Qué es (y qué no es) el ambiente beta

| Función | ¿Hay beta oficial de SUNAT? | Cómo probarla |
|---|---|---|
| Factura, boleta, NC, ND (`sendBill`) | **Sí** (`e-beta.sunat.gob.pe`) | Directo en beta |
| Resumen diario RC / Baja RA (`sendSummary` + `getStatus`) | **Sí** | Directo en beta |
| Guía de remisión (API REST) | **No documentada**: el manual de SUNAT solo publica producción | Sandbox de un PSE/OSE (configurable en la compañía) o producción con operaciones reales de bajo riesgo |
| Consulta de validez de CPE (REST) | **No**: consulta el padrón real | Requiere credenciales API reales; solo consulta, no emite nada |
| Recuperar CDR por número (`getStatusCdr`) | **No** (solo producción) | Producción |
| Libros PLE | No aplica (se validan con el aplicativo PLE de escritorio) | Programa PLE de SUNAT |

Credenciales beta: usuario `RUC` + `MODDATOS` (ej. `20000000001MODDATOS`) y clave `moddatos`.
Si tu beta rechaza el RUC de ejemplo, usa el RUC real de tu empresa con `MODDATOS`.

---

## 2. Preparación (una sola vez)

### 2.1 Levantar el entorno
```powershell
docker compose up -d --build
```
Crea la base en `http://localhost:8069/web/database/manager` con **País = Perú**, nombre `odoo19`.

### 2.2 Instalar los módulos
```powershell
docker compose exec odoo odoo -d odoo19 -i l10n_pe,l10n_pe_sunat_beta,l10n_pe_sunat_gre,l10n_pe_sunat_consulta,l10n_pe_sunat_edi,l10n_pe_sunat_detraccion,l10n_pe_edi_stock,l10n_pe_reports,l10n_pe_reports_stock --stop-after-init
docker compose restart odoo
```
Si algún módulo falla al instalar, **copia el error completo**: es el primer hallazgo de la prueba.

### 2.3 Cargar datos de prueba y certificado
El `.pfx` autofirmado (clave `beta1234`) ya viene en `certs/`. Para regenerarlo:
`python3 scripts/generate_test_cert.py 20000000001 beta1234`.

PowerShell (no soporta `<`):
```powershell
Get-Content scripts\seed_beta.py | docker compose exec -T odoo odoo shell -d odoo19
```
bash:
```bash
docker compose exec -T odoo odoo shell -d odoo19 < scripts/seed_beta.py
```
El script configura la compañía (RUC `20000000001`, ambiente beta, certificado) y crea:

| Dato | Valor |
|---|---|
| Cliente con RUC | `20131312955` (RUC público de SUNAT) |
| Cliente con DNI | `12345678` JUAN PEREZ GOMEZ |
| `PROD-A` | S/ 100 + IGV (bien almacenable) |
| `SERV-CONS` | S/ 1,000 + IGV, con detracción 037 (12 %) |
| `SERV-EXO` | S/ 500 exonerado (requiere un impuesto exonerado con *Tributo SUNAT = 9997*) |
| Vehículo / conductor | `ABC123` / CARLOS RAMIREZ DIAZ (DNI 45678912, licencia Q45678912) |

### 2.4 Configuración manual que el script no hace
1. **Impuestos** (Contabilidad > Configuración > Impuestos): comprueba que existen *IGV 18 %* (Tributo 1000 / Afectación 10) y un impuesto *Exonerado* (9997 / 20) e *Inafecto* (9998 / 30). Los módulos los clasifican solos; revisa la pestaña de cada uno.
2. **Diarios de venta**: activa **«Usar documentos»** (l10n_latam). El requisito de los módulos es que el nombre final del comprobante tenga la forma `SERIE-NÚMERO` (`F001-00000001`, `B001-00000001`, NC `FC01-…`/`BC01-…`, ND `FD01-…`). Si Odoo no propone el número, escríbelo en *Número de documento*.
   - Facturas y sus NC/ND: serie que empiece con **F**. Boletas y sus NC/ND: serie que empiece con **B**.
3. **Dirección del emisor**: ubigeo `150101` en la pestaña SUNAT; dirección en el contacto de la compañía.
4. **Envío**: deja *Envío a SUNAT = Manual* para controlar cada caso (se cambia en los casos CP-20/21).

### 2.5 Prueba de humo (5 minutos)
Crea la factura del caso CP-01 y pulsa **Enviar a SUNAT**. Si falla aquí, no avances: revisa la sección 8.

---

## 3. Cómo leer el resultado

En la factura: botón inteligente **SUNAT** → registro con *Estado*, *Código de respuesta* y *Mensaje*.

| Estado | Significado |
|---|---|
| **Aceptado** | Código `0`. Se guardó el CDR y se adjuntaron XML y CDR a la factura. |
| **Rechazado** | SUNAT devolvió CDR con código distinto de 0: hay que corregir y reenviar. |
| **Error** | No hubo CDR: falla de conexión, credenciales, firma o estructura (SOAP Fault). |

Rangos de códigos SUNAT (catálogo oficial): `0100–1999` excepciones (sin CDR), `2000–3999` rechazos,
`4000+` observaciones (el comprobante **se acepta** pero con advertencias). Verifica cada código en el
catálogo de errores publicado por SUNAT.

---

## 4. Casos de prueba — comprobantes

### A. Facturas

**CP-01 · Factura gravada**
- *Datos:* cliente RUC; 1 × `PROD-A`; total **S/ 118.00**.
- *Pasos:* crear factura → publicar → **Enviar a SUNAT**.
- *Esperado:* estado Aceptado, código `0`; adjuntos `20000000001-01-F001-00000001.xml` y `R-….zip`.
- *Revisar:* botón **Imprimir** → «Comprobante electrónico SUNAT»: QR y hash visibles; leyenda «SON: CIENTO DIECIOCHO CON 00/100 SOLES».

**CP-02 · Factura exonerada** — 1 × `SERV-EXO`; total **S/ 500.00**; esperado: aceptada, sin IGV.
*Revisar:* en el XML, `TaxExemptionReasonCode = 20` y tributo `9997`.

**CP-03 · Factura en dólares** — 1 × `PROD-A` con moneda **USD** (total USD 118.00).
*Esperado:* aceptada con `DocumentCurrencyCode = USD`; la leyenda dice «DÓLARES AMERICANOS».

**CP-04 · Factura a crédito** — vencimiento a 30 días; total S/ 1,180.00 con `SERV-CONS` **sin** detracción
(quita el código de detracción en la factura).
*Esperado:* aceptada; el XML trae `FormaPago = Credito` y `Cuota001` con fecha de vencimiento.

**CP-05 · Factura con detracción** — 1 × `SERV-CONS`; total **S/ 1,180.00**.
- *Pasos:* verificar que aparece *Código de detracción 037*, tasa 12 %, monto **S/ 142.00** (141.60 redondeado) → enviar.
- *Esperado:* aceptada; en el XML `InvoiceTypeCode listID="1001"`, nota `2006`, `PaymentMeans = Detraccion`
  con la cuenta del Banco de la Nación y `PaymentTerms = Detraccion`.
- *Negativo:* quita la cuenta de detracciones de la compañía → el envío debe bloquearse con mensaje claro.

### B. Boletas

**CP-06 · Boleta sin documento (menor a S/ 700)** — cliente «CLIENTES VARIOS»/sin documento; **0.5 × `PROD-A`** (50.00 + IGV 9.00 = **S/ 59.00**).
*Esperado:* aceptada (modo *Individual*).

**CP-07 · Boleta con DNI (mayor a S/ 700)** — cliente DNI; 1 × `SERV-CONS`; total **S/ 1,180.00**.
*Esperado:* aceptada; `schemeID="1"` en el cliente. *(Una boleta no lleva detracción.)*

### C. Notas de crédito y débito

**CP-08 · NC por anulación total (motivo 01)** — sobre la factura de CP-01.
- *Pasos:* en la factura aceptada, **Añadir nota de crédito** (total) → serie `FC01` → motivo **01** y sustento «Anulación de la operación» → publicar → enviar.
- *Esperado:* aceptada; XML `CreditNote` con `DiscrepancyResponse` (ReferenceID `F001-00000001`, código 01) y `BillingReference` tipo 01.
- *Negativo:* enviar una NC creada sin comprobante origen → bloqueo con mensaje.

**CP-09 · NC parcial por devolución (motivo 07)** — factura de 2 × `PROD-A` (S/ 236.00), NC de 1 unidad (S/ 118.00).
*Esperado:* aceptada; en el PLE 14.1 aparece en **negativo**.

**CP-10 · Nota de débito por intereses (motivo 01)** — sobre CP-01, S/ 10.00 + IGV = **S/ 11.80**.
*Esperado:* aceptada; XML `DebitNote` con `RequestedMonetaryTotal`.

### D. Resumen diario y bajas

**CP-11 · Resumen diario de boletas (RC)**
- *Pasos:* compañía → *Envío de boletas = Resumen diario*; publicar 3 boletas del mismo día; **Enviar a SUNAT** en una de ellas (o esperar el cron).
- *Esperado:* se crea `RC-AAAAMMDD-1` en **SUNAT > Resúmenes y bajas**, estado *Enviado (ticket)*; en pocos minutos pasa a *Aceptado*; cada boleta queda con registro SUNAT *Aceptado* «mediante RC-…».
- *Revisar:* si queda en *Enviado*, usa **Consultar ticket**; el mensaje «aún procesando» es normal al inicio.

**CP-12 · Baja de factura (RA)** — sobre una factura aceptada (CP-02): **Dar de baja en SUNAT** → motivo «ERROR EN LA EMISION».
*Esperado:* `RA-AAAAMMDD-1` aceptada; la factura queda marcada *Dado de baja en SUNAT*.

**CP-13 · Anulación de boleta (RC con condición 3)** — sobre una boleta aceptada: **Dar de baja en SUNAT**.
*Esperado:* RC con condición *Anular* aceptado.

### E. Nota de venta

**CP-14 · Nota de venta interna** — crear factura con *Comprobante SUNAT = Nota de venta* → publicar.
*Esperado:* número `NV01-00000001`; **no** aparece «Enviar a SUNAT»; **Imprimir nota de venta** genera PDF.
*Negativo:* forzar el envío por acción masiva → no debe enviarse.

---

## 5. Casos de prueba — guías, consulta, automatización, libros

### F. Guía de remisión (GRE)
> No hay beta oficial. Configura en la compañía el *ambiente de pruebas* con la URL de un sandbox compatible
> (PSE/OSE) o usa producción **solo si aceptas emitir una guía real**. Sin las credenciales API
> (Client ID / Secret) el envío debe fallar con un mensaje claro de configuración (no con un error técnico).

**CP-15 · GRE transporte privado (venta)** — Inventario → entrega con 5 × `PROD-A` a cliente RUC → pestaña **GRE SUNAT**: motivo 01, modalidad privada, conductor y vehículo de prueba, 1 bulto → **Generar GRE**.
- Completa ubigeos de partida y llegada (6 dígitos) → **Enviar a SUNAT**.
- *Esperado:* ticket numérico; luego *Aceptada* con CDR (el cron consulta cada 15 min).
- *Revisar:* el XML trae `TransportHandlingUnit/TransportEquipment/ID = ABC123` y `AdditionalDocumentReference` si hay factura vinculada.

**CP-16 · GRE transporte público** — modalidad 01 con transportista (RUC 11 dígitos). *Esperado:* el XML lleva `CarrierParty`, sin conductor ni placa.

**CP-17 · GRE automática** — en el tipo de operación *Órdenes de entrega* activa **Generar GRE al validar**; valida una entrega.
*Esperado:* se crea la GRE sola; si el envío automático está activo, también se envía. Si falla, queda nota en el chatter de la operación (la validación del stock **no** debe fallar).

### G. Consulta de comprobantes
> Requiere *Client ID/Secret* reales de «Consulta de Validez de CPE».

**CP-18 · Validar comprobante** — menú **SUNAT > Consultar comprobante** con una factura emitida en **producción**: RUC emisor, tipo 01, serie, número, fecha y monto.
*Esperado:* estado `ACEPTADO` (1), estado del RUC `ACTIVO`, condición `HABIDO`; queda en *Historial de consultas*.
*Negativo:* cambia el monto → debe indicar que no existe (`0`).

**CP-19 · Validar factura de proveedor** — factura de proveedor con referencia `E001-123` → **Validar en SUNAT**.
*Esperado:* se llena *Validez en SUNAT* con insignia; si la referencia no tiene `SERIE-NÚMERO`, mensaje claro.

### H. EDI automático, PDF y correo

**CP-20 · Envío al publicar + reintentos** — *Envío a SUNAT = Al publicar*.
1. Publica una factura → debe enviarse sola.
2. Pon una clave de certificado errónea y publica otra → queda en **Error**, el asiento **sí** se publica y el chatter anota el motivo.
3. Corrige la clave → en ≤ 15 minutos el cron la reenvía. *Esperado:* tras `Reintentos máximos` fallos deja de insistir.

**CP-21 · Correo con adjuntos** — activa *Enviar por correo al ser aceptado* (con correo saliente configurado) y envía CP-01.
*Esperado:* llega correo con **PDF + XML + CDR**. Si no hay correo configurado, la factura igual se acepta (el fallo de correo no bloquea).

### I. Libros PLE e inventario (SUNAT > Libros electrónicos)

**CP-22 · Registro de Ventas 14.1** — mes de las pruebas → *14.1* → **Generar libro**.
- *Esperado:* archivo `LE20000000001AAAAMM00140100001111.txt`; **35 campos** por fila; la NC aparece en negativo; las bajas con estado `2`.
- *Revisar:* abre el TXT en el **PLE de SUNAT** (versión vigente) y valida; el Excel debe cuadrar con el *Reporte de IGV* de Odoo.

**CP-23 · Registro de Compras 8.1** — con 2 facturas de proveedor (una con IGV, una sin). *Esperado:* **42 campos**; estado `1` con derecho a crédito, `0` sin él.

**CP-24 · Diario 5.1 + Plan 5.3** — *Esperado:* 21 y 8 campos; débitos = créditos del mes; cuentas del 5.3 = cuentas usadas en el 5.1.
> Si la compañía está marcada *Incorporada al SIRE*, el campo 20 del 5.1 va vacío (es lo previsto).

**CP-25 · Inventario 12.1 / 13.1** — con una compra de 20 uds. y una venta de 15 en el mes.
*Esperado:* primera fila de cada producto = saldo inicial (operación 16); saldo final = 5 uds.; el total valorizado del 13.1 cuadra con *Inventario > Reportes > Valoración*.

---

## 6. Casos negativos (deben fallar «bien»)

| ID | Provocación | Resultado esperado |
|---|---|---|
| N-01 | Nombre de factura sin formato `SERIE-NÚMERO` | Mensaje que explica el formato; no se envía |
| N-02 | Factura (01) a cliente con DNI | «requiere cliente con RUC de 11 dígitos» |
| N-03 | Enviar dos veces la misma factura aceptada | «ya fue aceptado por SUNAT» |
| N-04 | Credenciales SOL erróneas | Estado *Error* con código de excepción (0xxx) y mensaje de SUNAT |
| N-05 | Certificado ausente o clave incorrecta | Error claro de certificado; no se envía nada |
| N-06 | Emisión con fecha de más de 7 días de antigüedad | Rechazo/observación de SUNAT por fecha; queda registrado |
| N-07 | Sin conexión a internet (apaga la red del contenedor) | Estado *Error*; el cron lo reintenta al volver la red |

---

## 7. Plantilla de registro de resultados

| Caso | Fecha | Comprobante | Estado | Código SUNAT | ¿Pasó? | Observaciones / captura |
|---|---|---|---|---|---|---|
| CP-01 | | | | | | |
| CP-02 | | | | | | |
| … | | | | | | |

---

## 8. Problemas frecuentes

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| `password authentication failed` al arrancar | Clave de PostgreSQL distinta a la del volumen | `docker compose down -v` o `ALTER USER` (ver README) |
| «Configure RUC, usuario y clave SOL» | Falta configuración de la compañía | Pestaña SUNAT de la compañía |
| Error `0111` / `0102` en la respuesta | Perfil o usuario/clave SOL inválidos | Usuario `RUC+MODDATOS`, clave `moddatos` |
| Rechazo por firma (documento alterado) | Certificado/firma mal aplicada o XML modificado | Ver el XML adjunto; regenera con certificado nuevo |
| Rechazo por RUC del emisor | El RUC de prueba no coincide con el certificado/usuario | Usa el mismo RUC en compañía, usuario SOL y certificado |
| «No se pudo obtener serie y correlativo» | El diario no numera como `F001-00000001` | Activa «Usar documentos» o escribe el número |
| RC en *Enviado* mucho tiempo | SUNAT aún procesa | **Consultar ticket**; el cron lo hace cada 10 min |
| Impuesto sin tributo SUNAT | Impuesto creado a mano con otro nombre | Completa *Tributo SUNAT* y *Afectación* en el impuesto |

---

## 9. Criterios para pasar a producción

- [ ] CP-01 a CP-14 aprobados en beta (incluidos RC y RA).
- [ ] Todos los códigos `4xxx` (observaciones) revisados y justificados.
- [ ] **Certificado digital real** (emitido por una entidad acreditada) cargado y probado; usuario secundario SOL con perfil de facturación electrónica.
- [ ] Cuenta de detracciones del Banco de la Nación y tasas del catálogo **verificadas contra el Anexo vigente**.
- [ ] GRE probada contra el ambiente real o el del PSE/OSE, con credenciales API propias.
- [ ] Series autorizadas en SUNAT (SOL > Comprobantes > Series) iguales a las de Odoo.
- [ ] Libros PLE validados con el **programa PLE vigente**; confirmado si la empresa lleva ventas/compras en **SIRE**.
- [ ] Respaldo de base y de `filestore`; cron de envío y de tickets activos; correo saliente probado.
- [ ] Ambiente de la compañía cambiado a *Producción* **solo después** de lo anterior.

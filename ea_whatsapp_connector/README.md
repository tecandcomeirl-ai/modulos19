# EA WhatsApp Connector

Odoo 19 module by **ERP Artists**. It sends and receives WhatsApp messages from
Odoo. You pair a number by scanning a QR code, so no Meta Business API approval
is needed.

```
 Odoo (ea_whatsapp_connector)  <── REST + API key ──>  EA WhatsApp Gateway (Node.js, Baileys)  <──>  WhatsApp
          ▲                                                    │
          └──────────────── webhook (inbound, status, acks) ───┘
```

## 1. Start the gateway

The gateway is in `sidecar/` and needs Node.js 20 or newer.

```bash
cd sidecar
cp .env.example .env        # set API_KEY to a long random string
npm install
npm start                   # listens on http://0.0.0.0:3000
```

Keep it running in production with `pm2 start src/index.js --name ea-whatsapp`,
systemd, or Docker:

```bash
docker build -t ea-whatsapp-gateway sidecar
docker run -d --name ea-whatsapp -p 3000:3000 -e API_KEY=... -v ea_wa_data:/data ea-whatsapp-gateway
```

Session credentials are stored in `DATA_DIR`. Back that folder up and keep it
private: anyone with it can use the linked WhatsApp number. The gateway reconnects
paired sessions automatically when it restarts.

## 2. Pair a number in Odoo

1. Install **EA WhatsApp Connector**.
2. Go to **WhatsApp > Configuration > Accounts > New**.
3. Fill in:
   - **Gateway URL**: for example `http://localhost:3000`.
   - **Gateway API Key**: the same value as `API_KEY` in the gateway's `.env`.
   - **Odoo URL for Gateway**: only needed when the gateway reaches Odoo through
     a different address, for example `http://odoo:8069` in Docker. Otherwise
     `web.base.url` is used.
4. Click **Connect**. A QR code appears in the form. On your phone, go to
   **WhatsApp > Linked devices > Link a device** and scan it.
5. The account changes to **Connected**.

## 3. Use it

- **WhatsApp > Chats**: a WhatsApp-style inbox. Contacts appear on the left with
  their profile picture, last message and an unread count. Click one to open the
  conversation, then reply or attach files from the box at the bottom.
  Outgoing messages show ✓ sent, ✓✓ delivered and blue ✓✓ read. A red ! means
  the message failed; click it to retry. Search by name or phone number to start
  a new chat. Updates appear live.
- **WhatsApp > Dashboard**: sent, delivered, read, received and failed counts;
  messages per day; delivery rates; account status; recent messages and top
  contacts. Click a tile to see the matching messages.
- **Sales / Invoicing**: the add-ons `ea_whatsapp_connector_sale` and
  `ea_whatsapp_connector_account` install automatically. They add **Send WhatsApp**
  to quotations, sales orders and posted customer invoices or credit notes. The
  message is pre-filled with the amount and the online view or pay link, and the
  PDF is attached. A quotation sent this way is marked **Quotation Sent**.
- **Contacts**: click **Send WhatsApp** next to the phone number, or select
  several contacts and use **Action > Send WhatsApp**. The **WhatsApp** smart
  button opens the contact's chat.
- **Any document with a `partner_id`**: add a button or server action that opens
  the `ea.whatsapp.composer` wizard with `active_model` / `active_id` in the
  context. The message is sent to the document's partner and logged on its chatter.
- **Incoming messages** are logged in **WhatsApp > Messages** and posted on the
  contact's chatter. If an unknown number writes in, a contact is created for it
  (you can switch this off per account). A reply is also posted on the document
  the last message was sent from, if that was within 7 days.
- **Delivery status**: messages move through Sent, Delivered and Read.

## Access rights

| Group | Can do |
|---|---|
| WhatsApp / User | Send messages, see the message log |
| WhatsApp / Administrator | Create, pair and log out accounts; see API keys and webhook tokens |

## Gateway API

Every call except `/health` needs the header `X-Api-Key`.

| Method | Path | Body |
|---|---|---|
| GET | `/health` | |
| GET | `/sessions/:id` | returns `{status, qr, phone, name}` |
| GET | `/sessions/:id/avatar/:number` | returns `{url}` of the WhatsApp profile picture |
| POST | `/sessions/:id/start` | `{webhook_url, webhook_token}` |
| POST | `/sessions/:id/logout` | |
| POST | `/sessions/:id/messages` | `{to, text, media?: {data (base64), mimetype, filename}}` |

Webhook events are POSTed to `webhook_url` with the header `X-Webhook-Token`.
The body is `{session, event, data}`, where `event` is `status`, `message` or `ack`.

## Notes

- This uses the WhatsApp Web protocol through an unofficial library. Bulk or
  unsolicited messaging can get a number banned. Only message contacts who expect it.
- Only one-to-one chats are handled. Group, status and channel messages are ignored.

---
© ERP Artists. Licensed under LGPL-3.

import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";

const POLL_INTERVAL = 3000;

export class EaWhatsappQrField extends Component {
    static template = "ea_whatsapp_connector.QrField";
    static props = { ...standardFieldProps };

    setup() {
        this.state = useState({ qr: false, status: this.props.record.data.state, error: false });
        onMounted(() => {
            this.poll();
            this.timer = setInterval(() => this.poll(), POLL_INTERVAL);
        });
        onWillUnmount(() => clearInterval(this.timer));
    }

    get hint() {
        if (this.state.error) {
            return _t("Cannot reach the gateway. Retrying...");
        }
        return this.state.qr
            ? _t("Open WhatsApp on your phone > Linked devices > Link a device, then scan this code.")
            : _t("Waiting for the QR code from the gateway...");
    }

    async poll() {
        const record = this.props.record;
        if (!record.resId || this.busy) {
            return;
        }
        this.busy = true;
        try {
            const result = await rpc("/ea_whatsapp/account/qr_state", { account_id: record.resId });
            this.state.error = false;
            this.state.qr = result.qr;
            if (result.state !== this.state.status) {
                this.state.status = result.state;
                if (!record.dirty) {
                    await record.load();
                }
            }
        } catch {
            this.state.error = true;
        } finally {
            this.busy = false;
        }
    }
}

registry.category("fields").add("ea_whatsapp_qr", {
    component: EaWhatsappQrField,
    supportedTypes: ["binary"],
});

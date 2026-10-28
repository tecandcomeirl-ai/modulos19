/* global luxon */
import { Component, onMounted, onWillStart, onWillUnmount, useEffect, useRef, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { debounce } from "@web/core/utils/timing";

const FALLBACK_REFRESH = 30000;
const AVATAR_COLORS = ["#2a78d6", "#1baf7a", "#eb6834", "#4a3aa7", "#e87ba4", "#008300", "#e34948", "#eda100"];

export class EaWhatsappChat extends Component {
    static template = "ea_whatsapp_connector.Chat";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.bus = useService("bus_service");
        this.threadRef = useRef("thread");
        this.inputRef = useRef("input");
        this.fileRef = useRef("file");

        this.state = useState({
            search: "",
            conversations: [],
            contacts: [],
            active: null, // number of the open conversation
            thread: null,
            draft: "",
            files: [],
            sending: false,
            loadingOlder: false,
        });

        this.debouncedSearch = debounce(() => this.loadConversations(), 250);
        this.debouncedRefresh = debounce((numbers) => this.refresh(numbers), 300);
        this.onBusUpdate = ({ numbers }) => this.debouncedRefresh(numbers || []);

        onWillStart(async () => {
            await this.loadConversations();
            const initial = this.props.action?.context?.active_number;
            if (initial) {
                await this.openConversation(initial);
            }
        });
        onMounted(() => {
            this.bus.subscribe("ea_whatsapp/chat_update", this.onBusUpdate);
            this.timer = setInterval(() => this.refresh(), FALLBACK_REFRESH);
        });
        onWillUnmount(() => {
            this.bus.unsubscribe("ea_whatsapp/chat_update", this.onBusUpdate);
            clearInterval(this.timer);
        });
        // keep the thread scrolled to the newest message
        useEffect(
            () => {
                if (this.stickToBottom && this.threadRef.el) {
                    this.threadRef.el.scrollTop = this.threadRef.el.scrollHeight;
                }
            },
            () => [this.state.thread?.messages.length, this.state.active]
        );
    }

    // ------------------------------------------------------------------
    // Data
    // ------------------------------------------------------------------
    async loadConversations() {
        const result = await this.orm.call("ea.whatsapp.message", "chat_get_conversations", [], {
            search: this.state.search,
        });
        this.state.conversations = result.conversations;
        this.state.contacts = result.contacts;
    }

    async openConversation(number) {
        this.state.active = number;
        this.state.draft = "";
        this.state.files = [];
        this.stickToBottom = true;
        this.state.thread = await this.orm.call("ea.whatsapp.message", "chat_get_messages", [number]);
        const conv = this.state.conversations.find((c) => c.number === number);
        if (conv) {
            conv.unread = 0;
        }
        this.inputRef.el?.focus();
    }

    async reloadThread() {
        if (!this.state.active) {
            return;
        }
        const el = this.threadRef.el;
        this.stickToBottom = !el || el.scrollHeight - el.scrollTop - el.clientHeight < 80;
        const fresh = await this.orm.call("ea.whatsapp.message", "chat_get_messages", [this.state.active]);
        if (fresh.contact.number === this.state.active) {
            // keep already loaded older messages
            const older = (this.state.thread?.messages || []).filter(
                (m) => fresh.messages.length && m.id < fresh.messages[0].id
            );
            fresh.messages = [...older, ...fresh.messages];
            fresh.has_more = this.state.thread?.has_more && older.length ? this.state.thread.has_more : fresh.has_more;
            this.state.thread = fresh;
        }
    }

    async refresh(numbers = null) {
        await this.loadConversations();
        if (this.state.active && (!numbers || numbers.includes(this.state.active))) {
            await this.reloadThread();
        }
    }

    async loadOlder() {
        const thread = this.state.thread;
        if (!thread?.has_more || this.state.loadingOlder || !thread.messages.length) {
            return;
        }
        this.state.loadingOlder = true;
        const el = this.threadRef.el;
        const previousHeight = el.scrollHeight;
        try {
            const older = await this.orm.call("ea.whatsapp.message", "chat_get_messages", [this.state.active], {
                before_id: thread.messages[0].id,
            });
            this.stickToBottom = false;
            thread.messages.unshift(...older.messages);
            thread.has_more = older.has_more;
            requestAnimationFrame(() => {
                el.scrollTop = el.scrollHeight - previousHeight;
            });
        } finally {
            this.state.loadingOlder = false;
        }
    }

    onThreadScroll(ev) {
        if (ev.target.scrollTop < 60) {
            this.loadOlder();
        }
    }

    // ------------------------------------------------------------------
    // Sending
    // ------------------------------------------------------------------
    onSearchInput(ev) {
        this.state.search = ev.target.value;
        this.debouncedSearch();
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    onInput(ev) {
        this.state.draft = ev.target.value;
        ev.target.style.height = "auto";
        ev.target.style.height = Math.min(ev.target.scrollHeight, 140) + "px";
    }

    openFilePicker() {
        this.fileRef.el.click();
    }

    async onFilesSelected(ev) {
        const files = [...ev.target.files];
        ev.target.value = "";
        for (const file of files) {
            if (file.size > 16 * 1024 * 1024) {
                this.notification.add(_t("%s is larger than 16 MB.", file.name), { type: "warning" });
                continue;
            }
            const data = await new Promise((resolve, reject) => {
                const reader = new FileReader();
                reader.onload = () => resolve(reader.result.split(",")[1]);
                reader.onerror = reject;
                reader.readAsDataURL(file);
            });
            this.state.files.push({ name: file.name, mimetype: file.type || "application/octet-stream", data });
        }
        this.inputRef.el?.focus();
    }

    removeFile(index) {
        this.state.files.splice(index, 1);
    }

    async send() {
        const body = this.state.draft.trim();
        if ((!body && !this.state.files.length) || this.state.sending || !this.state.active) {
            return;
        }
        this.state.sending = true;
        const files = this.state.files;
        this.state.draft = "";
        this.state.files = [];
        if (this.inputRef.el) {
            this.inputRef.el.style.height = "auto";
        }
        try {
            const message = await this.orm.call("ea.whatsapp.message", "chat_send", [this.state.active], {
                body, files,
            });
            this.stickToBottom = true;
            if (!this.state.thread.messages.some((m) => m.id === message.id)) {
                this.state.thread.messages.push(message);
            }
            if (message.state === "failed") {
                this.notification.add(message.error || _t("The message could not be sent."), { type: "danger" });
            }
            this.loadConversations();
        } catch (error) {
            this.state.draft = body;
            this.state.files = files;
            throw error;
        } finally {
            this.state.sending = false;
            this.inputRef.el?.focus();
        }
    }

    async retry(message) {
        if (message.state !== "failed") {
            return;
        }
        const [updated] = await this.orm.call("ea.whatsapp.message", "chat_retry", [[message.id]]);
        Object.assign(message, updated);
        if (updated.state === "failed") {
            this.notification.add(updated.error || _t("The message could not be sent."), { type: "danger" });
        }
    }

    // ------------------------------------------------------------------
    // Navigation
    // ------------------------------------------------------------------
    openContact() {
        const partnerId = this.state.thread?.contact.partner_id;
        if (partnerId) {
            this.action.doAction({
                type: "ir.actions.act_window", res_model: "res.partner", res_id: partnerId,
                views: [[false, "form"]],
            });
        }
    }

    newChat() {
        this.action.doAction("ea_whatsapp_connector.action_ea_whatsapp_composer_new", {
            onClose: () => this.refresh(),
        });
    }

    closeThread() {
        this.state.active = null;
        this.state.thread = null;
    }

    // ------------------------------------------------------------------
    // Display helpers
    // ------------------------------------------------------------------
    get threadItems() {
        const items = [];
        let lastDay = null;
        for (const message of this.state.thread?.messages || []) {
            const dt = this.toLocal(message.date);
            const day = dt.toISODate();
            if (day !== lastDay) {
                items.push({ key: `day-${day}`, type: "day", label: this.dayLabel(dt) });
                lastDay = day;
            }
            items.push({ key: `msg-${message.id}`, type: "msg", message });
        }
        return items;
    }

    toLocal(value) {
        return luxon.DateTime.fromSQL(value, { zone: "utc" }).toLocal();
    }

    dayLabel(dt) {
        const today = luxon.DateTime.local().startOf("day");
        const diff = today.diff(dt.startOf("day"), "days").days;
        if (diff === 0) {
            return _t("Today");
        }
        if (diff === 1) {
            return _t("Yesterday");
        }
        if (diff < 7) {
            return dt.toFormat("cccc");
        }
        return dt.toFormat("d LLLL yyyy");
    }

    listTime(value) {
        const dt = this.toLocal(value);
        const diff = luxon.DateTime.local().startOf("day").diff(dt.startOf("day"), "days").days;
        if (diff === 0) {
            return dt.toFormat("HH:mm");
        }
        if (diff === 1) {
            return _t("Yesterday");
        }
        return diff < 7 ? dt.toFormat("ccc") : dt.toFormat("dd/LL/yy");
    }

    time(value) {
        return this.toLocal(value).toFormat("HH:mm");
    }

    preview(message) {
        if (message.body) {
            return message.body.split("\n")[0];
        }
        const att = message.attachments[0];
        if (!att) {
            return "";
        }
        return att.is_image ? _t("Photo") : att.name;
    }

    initials(name) {
        const parts = (name || "?").replace(/^\+/, "").trim().split(/\s+/);
        return ((parts[0]?.[0] || "") + (parts[1]?.[0] || "")).toUpperCase() || "#";
    }

    avatarColor(key) {
        let hash = 0;
        for (const ch of String(key)) {
            hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
        }
        return AVATAR_COLORS[hash % AVATAR_COLORS.length];
    }

    tickTitle(state) {
        return {
            queued: _t("Sending"), sent: _t("Sent"), delivered: _t("Delivered"),
            read: _t("Read"), failed: _t("Not sent - click to retry"),
        }[state] || "";
    }
}

registry.category("actions").add("ea_whatsapp_chat", EaWhatsappChat);

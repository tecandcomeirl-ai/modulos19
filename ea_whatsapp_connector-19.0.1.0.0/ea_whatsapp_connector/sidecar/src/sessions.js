'use strict';

const fs = require('fs');
const path = require('path');
const QRCode = require('qrcode');
const baileys = require('@whiskeysockets/baileys');

const makeWASocket = baileys.default || baileys.makeWASocket;
const {
    Browsers,
    DisconnectReason,
    downloadMediaMessage,
    fetchLatestBaileysVersion,
    getContentType,
    jidDecode,
    makeCacheableSignalKeyStore,
    normalizeMessageContent,
    useMultiFileAuthState,
} = baileys;

const IGNORED_TYPES = new Set([
    'protocolMessage', 'reactionMessage', 'senderKeyDistributionMessage',
    'messageContextInfo', 'pollUpdateMessage', 'keepInChatMessage',
]);
const MEDIA_TYPES = new Set(['imageMessage', 'videoMessage', 'audioMessage', 'documentMessage', 'stickerMessage']);
const EXTENSIONS = {
    'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp', 'image/gif': 'gif',
    'video/mp4': 'mp4', 'audio/ogg': 'ogg', 'audio/mpeg': 'mp3', 'audio/mp4': 'm4a',
    'application/pdf': 'pdf',
};
// WAMessageStatus: 2 = server ack, 3 = delivered, 4 = read, 5 = played
const ACK_STATUS = { 2: 'sent', 3: 'delivered', 4: 'read', 5: 'read' };

const SAFE_ID = /^[A-Za-z0-9_-]{1,64}$/;

class SessionManager {
    constructor({ dataDir, logger, maxMediaBytes }) {
        this.dataDir = dataDir;
        this.logger = logger;
        this.maxMediaBytes = maxMediaBytes;
        this.sessions = new Map();
        this.avatarCache = new Map(); // jid -> { url, at }
        fs.mkdirSync(dataDir, { recursive: true });
    }

    static isValidId(id) {
        return SAFE_ID.test(id || '');
    }

    sessionDir(id) {
        return path.join(this.dataDir, id);
    }

    readConfig(id) {
        try {
            return JSON.parse(fs.readFileSync(path.join(this.sessionDir(id), 'config.json'), 'utf8'));
        } catch {
            return {};
        }
    }

    writeConfig(id, config) {
        fs.mkdirSync(this.sessionDir(id), { recursive: true });
        fs.writeFileSync(path.join(this.sessionDir(id), 'config.json'), JSON.stringify(config, null, 2), { mode: 0o600 });
    }

    status(id) {
        const session = this.sessions.get(id);
        if (!session) {
            return { status: 'not_found', qr: null };
        }
        return { status: session.status, qr: session.qr, phone: session.phone, name: session.name };
    }

    /** Restore every session that was paired before the gateway restarted. */
    async restoreAll() {
        for (const id of fs.readdirSync(this.dataDir)) {
            if (SessionManager.isValidId(id) && fs.existsSync(path.join(this.sessionDir(id), 'auth', 'creds.json'))) {
                this.logger.info({ session: id }, 'restoring session');
                await this.start(id, this.readConfig(id)).catch((err) =>
                    this.logger.error({ session: id, err }, 'restore failed'));
            }
        }
    }

    async start(id, config = {}) {
        const merged = { ...this.readConfig(id), ...config };
        this.writeConfig(id, merged);
        const existing = this.sessions.get(id);
        if (existing) {
            existing.config = merged;
            if (existing.status !== 'disconnected' && existing.status !== 'logged_out') {
                return this.status(id);
            }
            existing.stopped = true;
            existing.sock?.end(undefined);
        }
        const session = {
            id, config: merged, status: 'starting', qr: null, phone: null, name: null,
            retries: 0, stopped: false, sock: null,
        };
        this.sessions.set(id, session);
        await this.connect(session);
        return this.status(id);
    }

    async connect(session) {
        const log = this.logger.child({ session: session.id });
        const { state, saveCreds } = await useMultiFileAuthState(path.join(this.sessionDir(session.id), 'auth'));
        let version;
        try {
            ({ version } = await fetchLatestBaileysVersion());
        } catch {
            version = undefined; // fall back to the version bundled with Baileys
        }
        const sock = makeWASocket({
            version,
            logger: log.child({ module: 'baileys' }, { level: 'warn' }),
            auth: { creds: state.creds, keys: makeCacheableSignalKeyStore(state.keys, log) },
            browser: Browsers.ubuntu('Chrome'),
            markOnlineOnConnect: false,
            syncFullHistory: false,
            generateHighQualityLinkPreview: false,
        });
        session.sock = sock;

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', async (update) => {
            if (session.sock !== sock) {
                return; // stale socket
            }
            const { connection, lastDisconnect, qr } = update;
            if (qr) {
                session.qr = await QRCode.toDataURL(qr, { margin: 1, width: 320 });
                this.setStatus(session, 'qr');
            }
            if (connection === 'open') {
                session.retries = 0;
                session.qr = null;
                session.phone = jidDecode(sock.user?.id)?.user || null;
                session.name = sock.user?.name || sock.user?.verifiedName || null;
                log.info({ phone: session.phone }, 'connected');
                this.setStatus(session, 'connected');
            }
            if (connection === 'close') {
                const code = lastDisconnect?.error?.output?.statusCode;
                session.qr = null;
                if (session.stopped) {
                    return;
                }
                if (code === DisconnectReason.loggedOut) {
                    log.warn('logged out from phone');
                    this.wipe(session.id);
                    this.setStatus(session, 'logged_out');
                    this.sessions.delete(session.id);
                    return;
                }
                if (!state.creds.registered && code === DisconnectReason.timedOut) {
                    log.info('QR code expired without scan');
                    this.setStatus(session, 'disconnected');
                    return;
                }
                session.retries += 1;
                const delay = Math.min(60000, 2000 * session.retries);
                log.warn({ code, delay }, 'connection closed, reconnecting');
                this.setStatus(session, 'connecting');
                setTimeout(() => {
                    if (!session.stopped && this.sessions.get(session.id) === session) {
                        this.connect(session).catch((err) => log.error({ err }, 'reconnect failed'));
                    }
                }, delay);
            }
        });

        sock.ev.on('messages.upsert', async ({ messages, type }) => {
            if (type !== 'notify') {
                return;
            }
            for (const msg of messages) {
                try {
                    const data = await this.parseInbound(session, msg);
                    if (data) {
                        await this.notify(session, 'message', data, 5);
                    }
                } catch (err) {
                    log.error({ err, id: msg.key?.id }, 'failed to handle inbound message');
                }
            }
        });

        sock.ev.on('messages.update', (updates) => {
            for (const { key, update } of updates) {
                const status = ACK_STATUS[update?.status];
                if (key?.fromMe && status) {
                    this.notify(session, 'ack', { id: key.id, status }, 2);
                }
            }
        });
    }

    setStatus(session, status) {
        session.status = status;
        this.notify(session, 'status', {
            status, qr: session.qr, phone: session.phone, name: session.name,
        }, 1);
    }

    wipe(id) {
        fs.rmSync(path.join(this.sessionDir(id), 'auth'), { recursive: true, force: true });
    }

    async logout(id) {
        const session = this.sessions.get(id);
        if (session) {
            session.stopped = true;
            try {
                await session.sock?.logout();
            } catch (err) {
                this.logger.warn({ session: id, err: err.message }, 'logout call failed, wiping anyway');
            }
            session.sock?.end(undefined);
            this.sessions.delete(id);
        }
        this.wipe(id);
        return { status: 'logged_out' };
    }

    async shutdown() {
        for (const session of this.sessions.values()) {
            session.stopped = true;
            session.sock?.end(undefined);
        }
    }

    // ------------------------------------------------------------------
    // Inbound
    // ------------------------------------------------------------------
    senderNumber(msg) {
        const jid = msg.key.remoteJid || '';
        if (jid.endsWith('@s.whatsapp.net')) {
            return jidDecode(jid)?.user;
        }
        // Privacy "LID" chats: the phone-number JID travels in an alternate field
        const alt = msg.key.senderPn || msg.key.remoteJidAlt || msg.key.participantPn;
        if (alt && alt.endsWith('@s.whatsapp.net')) {
            return jidDecode(alt)?.user;
        }
        return null;
    }

    async parseInbound(session, msg) {
        const jid = msg.key?.remoteJid || '';
        if (!msg.message || msg.key.fromMe || !jid || jid.endsWith('@g.us') || jid.endsWith('@broadcast')
            || jid.endsWith('@newsletter')) {
            return null; // groups, status, channels are out of scope
        }
        const number = this.senderNumber(msg);
        if (!number) {
            this.logger.warn({ session: session.id, jid }, 'cannot resolve sender number, skipped');
            return null;
        }
        const content = normalizeMessageContent(msg.message);
        const type = content && getContentType(content);
        if (!type || IGNORED_TYPES.has(type)) {
            return null;
        }
        const body = content[type] || {};
        let text = content.conversation || content.extendedTextMessage?.text || body.caption || '';
        if (type === 'locationMessage' || type === 'liveLocationMessage') {
            text = `Location: https://maps.google.com/?q=${body.degreesLatitude},${body.degreesLongitude}`
                + (body.name ? `\n${body.name}` : '') + (body.address ? `\n${body.address}` : '');
        } else if (type === 'contactMessage') {
            text = `Contact card: ${body.displayName || ''}\n${body.vcard || ''}`.trim();
        } else if (type === 'pollCreationMessage' || type === 'pollCreationMessageV3') {
            text = `Poll: ${body.name}\n` + (body.options || []).map((o) => `- ${o.optionName}`).join('\n');
        }

        let media = null;
        if (MEDIA_TYPES.has(type)) {
            const size = Number(body.fileLength || 0);
            if (size && size > this.maxMediaBytes) {
                text = `${text}\n[${type.replace('Message', '')} too large to download: ${Math.round(size / 1048576)} MB]`.trim();
            } else {
                const buffer = await downloadMediaMessage(msg, 'buffer', {}, {
                    logger: this.logger, reuploadRequest: session.sock.updateMediaMessage,
                });
                const mimetype = (body.mimetype || 'application/octet-stream').split(';')[0];
                const ext = EXTENSIONS[mimetype] || mimetype.split('/')[1] || 'bin';
                media = {
                    data: buffer.toString('base64'),
                    mimetype,
                    filename: body.fileName || `${type.replace('Message', '')}_${msg.key.id}.${ext}`,
                };
            }
        }
        if (!text && !media) {
            return null;
        }
        return {
            id: msg.key.id,
            from: number,
            avatar_url: await this.profilePicture(session, `${number}@s.whatsapp.net`),
            push_name: msg.pushName || null,
            text,
            timestamp: Number(msg.messageTimestamp) || Math.floor(Date.now() / 1000),
            media,
        };
    }

    async notify(session, event, data, attempts = 1) {
        const { webhook_url: url, webhook_token: token } = session.config;
        if (!url) {
            return;
        }
        for (let attempt = 1; attempt <= attempts; attempt += 1) {
            try {
                const response = await fetch(url, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'X-Webhook-Token': token || '' },
                    body: JSON.stringify({ session: session.id, event, data }),
                    signal: AbortSignal.timeout(30000),
                });
                if (response.ok) {
                    return;
                }
                this.logger.warn({ session: session.id, event, status: response.status }, 'webhook rejected');
                if (response.status < 500) {
                    return; // retrying a 4xx will not help
                }
            } catch (err) {
                this.logger.warn({ session: session.id, event, err: err.message, attempt }, 'webhook failed');
            }
            if (attempt < attempts) {
                await new Promise((resolve) => setTimeout(resolve, 2000 * attempt));
            }
        }
    }

    async profilePicture(session, jid) {
        const cached = this.avatarCache.get(jid);
        if (cached && Date.now() - cached.at < 6 * 3600 * 1000) {
            return cached.url;
        }
        let url = null;
        try {
            url = await session.sock.profilePictureUrl(jid, 'image');
        } catch {
            url = null; // no picture or hidden by the contact's privacy settings
        }
        this.avatarCache.set(jid, { url, at: Date.now() });
        return url;
    }

    async avatar(id, number) {
        const session = this.sessions.get(id);
        if (!session || session.status !== 'connected') {
            return { url: null };
        }
        const digits = String(number || '').replace(/\D/g, '');
        return { url: digits ? await this.profilePicture(session, `${digits}@s.whatsapp.net`) : null };
    }

    // ------------------------------------------------------------------
    // Outbound
    // ------------------------------------------------------------------
    async send(id, { to, text, media }) {
        const session = this.sessions.get(id);
        if (!session || session.status !== 'connected') {
            const error = new Error('WhatsApp session is not connected');
            error.status = 409;
            throw error;
        }
        const number = String(to || '').replace(/\D/g, '');
        if (number.length < 6) {
            const error = new Error('Invalid phone number');
            error.status = 400;
            throw error;
        }
        const [lookup] = await session.sock.onWhatsApp(`${number}@s.whatsapp.net`);
        if (!lookup?.exists) {
            const error = new Error(`+${number} is not on WhatsApp`);
            error.status = 404;
            throw error;
        }
        const jid = lookup.jid;
        let content;
        if (media && media.data) {
            const buffer = Buffer.from(media.data, 'base64');
            if (buffer.length > this.maxMediaBytes) {
                const error = new Error('Attachment is too large');
                error.status = 413;
                throw error;
            }
            const mimetype = media.mimetype || 'application/octet-stream';
            const caption = text || undefined;
            if (mimetype.startsWith('image/') && mimetype !== 'image/svg+xml') {
                content = { image: buffer, mimetype, caption };
            } else if (mimetype.startsWith('video/')) {
                content = { video: buffer, mimetype, caption };
            } else if (mimetype.startsWith('audio/')) {
                content = { audio: buffer, mimetype };
            } else {
                content = { document: buffer, mimetype, fileName: media.filename || 'file', caption };
            }
            if (content.audio && text) {
                await session.sock.sendMessage(jid, { text }); // audio cannot carry a caption
            }
        } else {
            if (!text) {
                const error = new Error('Nothing to send');
                error.status = 400;
                throw error;
            }
            content = { text };
        }
        const result = await session.sock.sendMessage(jid, content);
        return { id: result?.key?.id, jid };
    }
}

module.exports = { SessionManager };

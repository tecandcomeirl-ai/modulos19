'use strict';

require('dotenv').config();

const crypto = require('crypto');
const path = require('path');
const express = require('express');
const pino = require('pino');
const { SessionManager } = require('./sessions');

const PORT = Number(process.env.PORT || 3000);
const HOST = process.env.HOST || '0.0.0.0';
const API_KEY = process.env.API_KEY || '';
const DATA_DIR = path.resolve(process.env.DATA_DIR || path.join(__dirname, '..', 'sessions'));
const MAX_MEDIA_MB = Number(process.env.MAX_MEDIA_MB || 16);

const logger = pino({ level: process.env.LOG_LEVEL || 'info' });

if (!API_KEY) {
    logger.warn('API_KEY is empty: every request will be accepted. Set API_KEY in .env for production.');
}

const manager = new SessionManager({ dataDir: DATA_DIR, logger, maxMediaBytes: MAX_MEDIA_MB * 1024 * 1024 });
const app = express();
app.use(express.json({ limit: `${Math.ceil(MAX_MEDIA_MB * 1.4) + 1}mb` }));

function safeEqual(a, b) {
    const left = Buffer.from(String(a));
    const right = Buffer.from(String(b));
    return left.length === right.length && crypto.timingSafeEqual(left, right);
}

app.get('/health', (req, res) => res.json({ ok: true, sessions: manager.sessions.size }));

const router = express.Router();
router.use((req, res, next) => {
    if (API_KEY && !safeEqual(req.get('X-Api-Key') || '', API_KEY)) {
        return res.status(401).json({ error: 'invalid api key' });
    }
    return next();
});
router.param('id', (req, res, next, id) => {
    if (!SessionManager.isValidId(id)) {
        return res.status(400).json({ error: 'invalid session id' });
    }
    return next();
});

const handle = (fn) => async (req, res) => {
    try {
        res.json(await fn(req));
    } catch (err) {
        const status = err.status || 500;
        if (status >= 500) {
            logger.error({ err, path: req.path }, 'request failed');
        }
        res.status(status).json({ error: err.message || 'internal error' });
    }
};

router.get('/:id', handle((req) => manager.status(req.params.id)));
router.post('/:id/start', handle((req) => manager.start(req.params.id, {
    webhook_url: req.body.webhook_url,
    webhook_token: req.body.webhook_token,
})));
router.post('/:id/logout', handle((req) => manager.logout(req.params.id)));
router.get('/:id/avatar/:number', handle((req) => manager.avatar(req.params.id, req.params.number)));
router.post('/:id/messages', handle((req) => manager.send(req.params.id, req.body || {})));

app.use('/sessions', router);

const server = app.listen(PORT, HOST, async () => {
    logger.info(`EA WhatsApp gateway listening on http://${HOST}:${PORT}`);
    await manager.restoreAll();
});

async function stop() {
    logger.info('shutting down');
    await manager.shutdown();
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 3000).unref();
}
process.on('SIGINT', stop);
process.on('SIGTERM', stop);

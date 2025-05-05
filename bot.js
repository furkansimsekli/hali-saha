const { Client, LocalAuth } = require('whatsapp-web.js');
const qrcode = require('qrcode-terminal');
const axios = require('axios');

require('dotenv').config();


const TARGET_CHAT = process.env.TARGET_CHAT;
const ITEM = process.env.ITEM;

const client = new Client({
    authStrategy: new LocalAuth(),
    puppeteer: {
        args: ['--no-sandbox', '--disable-setuid-sandbox']
    }
});

client.on('qr', (qr) => {
    qrcode.generate(qr, { small: true });
});

client.on('ready', () => {
    console.log('INFO: Client is ready.');
});

client.on('message', async (msg) => {
    // Only group messages
    if (!msg.from.includes('@g.us')) return;

    const chat = await msg.getChat();
    if (chat.name !== TARGET_CHAT) return;

    const prefix = 'https://listmoz.com/#';
    if (!msg.body.includes(prefix)) return;

    const startIdx = msg.body.indexOf(prefix);
    const endIdx = msg.body.indexOf(' ', startIdx);
    const fullUrl = msg.body.substring(startIdx, endIdx === -1 ? msg.body.length : endIdx).trim();
    const modUrl = fullUrl.split('#')[1];
    if (!modUrl) return;

    console.log('INFO: A new listmoz link has been dropped!');
    console.log(`INFO: Mod URL: ${modUrl}`);

    try {
        const fetchRes = await waitForValidFetch(modUrl);
        const { read_url, items = [] } = fetchRes;

        const alreadyExists = items.some(e => e.description === ITEM);
        if (alreadyExists) {
            console.log(`WARNING: Enrollment skipped, because ${ITEM} already exists`);
            return;
        }

        const payload = {
            description: ITEM,
            force_creation_of_new_list: false,
            mod_url: modUrl,
            read_url
        };

        await axios.post('https://listmoz.com/actions?action=ADD', payload, {
            headers: { 'Content-Type': 'application/json' }
        });

        console.log(`INFO: Enrollment successful for ${ITEM} to ${fullUrl}`);
    } catch (err) {
        console.error('ERROR: Enrollment failed:', err.message);
    }
});

client.initialize();

async function waitForValidFetch(modUrl, maxRetries = 100) {
    const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

    for (let i = 0; i < maxRetries; i++) {
        try {
            const res = await axios.get(`https://listmoz.com/actions?action=FETCH&mod_url=${modUrl}`);
            if (res.data.read_url) return res.data;
            console.log(`WARNING: read_url not found, retrying (${i + 1})...`);
        } catch (err) {
            console.error(`ERROR: ${err.message}`);
        }
        await delay(30000);
    }

    throw new Error(`read_url not found after max retries: ${maxRetries}`);
}

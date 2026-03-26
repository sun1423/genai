const express = require('express');
const axios = require('axios');
const path = require('path');
require('dotenv').config();

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;

// Serve the UI
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.post('/api/analyze', async (req, res) => {
    const { text } = req.body;

    if (!text) return res.status(400).json({ error: "No text provided" });

    try {
        const response = await axios.post('https://openrouter.ai/api/v1/chat/completions', {
            model: 'google/gemini-2.0-flash-001',
            messages: [{ role: 'user', content: text }]
        }, {
            headers: {
                'Authorization': `Bearer ${process.env.OPENROUTER_KEY}`,
                'Content-Type': 'application/json',
                'HTTP-Referer': 'http://localhost:3000', // Required by some OpenRouter models
                'X-Title': 'VM AI Proxy'
            }
        });

        // Extracting only the human-readable text
        const cleanText = response.data.choices[0].message.content;
        res.json({ result: cleanText });

    } catch (error) {
        const errorDetails = error.response?.data?.error?.message || error.message;
        console.error("OpenRouter Error:", errorDetails);
        res.status(500).json({ error: "OpenRouter Error: " + errorDetails });
    }
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`Server running on http://localhost:${PORT}`);
});const express = require('express');
const axios = require('axios');
require('dotenv').config();

const app = express();
app.use(express.json());
app.use(express.static('public')); // To serve your index.html

app.post('/api/chat', async (req, res) => {
    try {
        const { message } = req.body;

        const response = await axios.post('https://openrouter.ai/api/v1/chat/completions', {
            model: 'google/gemini-2.0-flash-001',
            messages: [{ role: 'user', content: message }]
        }, {
            headers: {
                'Authorization': `Bearer ${process.env.OPENROUTER_KEY}`,
                'Content-Type': 'application/json'
            }
        });

        // 🟢 THE CLEANER: Extracting only what the user needs
        const cleanData = {
            text: response.data.choices[0].message.content,
            model: response.data.model,
            tokens: response.data.usage.total_tokens
        };

        res.json(cleanData);
    } catch (error) {
        res.status(500).json({ error: error.response?.data || error.message });
    }
});

app.listen(3000, () => console.log('Server running on http://localhost:3000'));const express = require('express');
const axios = require('axios');
const path = require('path');
require('dotenv').config();

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;

// DEBUG: This will show in 'pm2 logs' if the key is actually loaded
if (!process.env.OPENROUTER_KEY) {
    console.error("❌ ERROR: OPENROUTER_KEY is not defined in environment variables!");
} else {
    console.log("✅ OPENROUTER_KEY is loaded.");
}

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.post('/api/analyze', async (req, res) => {
    const { text } = req.body;
    if (!text) return res.status(400).json({ error: "No text provided" });

    try {
        const response = await axios.post('https://openrouter.ai/api/v1/chat/completions', {
            model: 'google/gemini-2.0-flash-001',
            messages: [{ role: 'user', content: text }]
        }, {
            headers: {
                // Ensure there is no space between 'Bearer' and the key if the key is missing
                'Authorization': `Bearer ${process.env.OPENROUTER_KEY}`,
                'Content-Type': 'application/json',
                'HTTP-Referer': 'http://localhost:3000',
                'X-Title': 'VM AI Proxy'
            }
        });
        res.json(response.data);
    } catch (error) {
        const errorMsg = error.response?.data?.error?.message || error.message;
        console.error("OpenRouter Details:", errorMsg);
        res.status(500).json({ error: "OpenRouter Error: " + errorMsg });
    }
});

app.listen(PORT, '0.0.0.0', () => console.log(`Server live on port ${PORT}`));

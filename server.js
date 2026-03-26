const express = require('express');
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

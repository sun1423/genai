const express = require('express');
const axios = require('axios');
const path = require('path');
require('dotenv').config();

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 3000;

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
                // OpenRouter specific headers (Required for some keys)
                'HTTP-Referer': 'http://localhost:3000', 
                'X-Title': 'VM AI Proxy'
            }
        });
        res.json(response.data);
    } catch (error) {
        // Log the actual error response from OpenRouter to your VM console
        console.error("OpenRouter Error Details:", error.response ? error.response.data : error.message);
        res.status(500).json({ error: "OpenRouter Error: " + (error.response?.data?.error?.message || error.message) });
    }
});

app.listen(PORT, '0.0.0.0', () => console.log(`Server live on port ${PORT}`));

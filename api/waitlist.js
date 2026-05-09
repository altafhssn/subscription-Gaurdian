// Vercel serverless function using CommonJS
// Captures waitlist signups. Check logs in Vercel dashboard.

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Only POST accepted' });
  }

  const { email, name } = req.body || {};

  if (!email || !email.includes('@')) {
    return res.status(400).json({ error: 'Valid email required' });
  }

  console.log('📝 SIGNUP:', JSON.stringify({
    email: email.toLowerCase().trim(),
    name: name || '',
    time: new Date().toISOString()
  }));

  return res.status(200).json({ status: 'ok', message: "You're on the list!" });
};

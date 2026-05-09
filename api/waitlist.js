// Vercel serverless function — captures waitlist signups
// Deploy to Vercel (free tier). Signups stored in Vercel KV or just logged.
// For simplicity, stores in a JSON file (ephemeral on serverless)
// Better: use Vercel KV or a real DB later.

export default async function handler(req, res) {
  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const { email, name } = req.body || {};

  if (!email || !email.includes('@')) {
    return res.status(400).json({ error: 'Valid email is required' });
  }

  // Log the signup (Vercel logs are accessible from dashboard)
  console.log('NEW SIGNUP:', JSON.stringify({
    email: email.toLowerCase().trim(),
    name: name || '',
    timestamp: new Date().toISOString()
  }));

  return res.status(200).json({ 
    status: 'ok', 
    message: "You're on the list!"
  });
}

// Netlify function — Subscription Guardian waitlist
// Stores signups to a JSON file in Netlify's /tmp (per deploy instance)
// For production: swap in Supabase, Airtable, or Google Sheets

const fs = require('fs');
const path = require('path');

exports.handler = async function(event, context) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS'
  };

  // CORS preflight
  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return {
      statusCode: 405,
      headers,
      body: JSON.stringify({ error: 'Only POST accepted' })
    };
  }

  try {
    const { email, hp_check } = JSON.parse(event.body || '{}');

    // Honeypot — bot caught, silently succeed
    if (hp_check) {
      return {
        statusCode: 200,
        headers,
        body: JSON.stringify({ status: 'ok' })
      };
    }

    const cleanEmail = (email || '').toLowerCase().trim();

    // Validate email
    if (!cleanEmail || !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(cleanEmail)) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ error: 'Valid email required' })
      };
    }

    // Store to a JSON file (survives as long as the Netlify instance is warm)
    // For proper persistence, connect Airtable/Supabase below
    const DATA_FILE = path.join('/tmp', 'sg_waitlist.json');
    let signups = [];
    
    try {
      signups = JSON.parse(fs.readFileSync(DATA_FILE, 'utf-8'));
    } catch (_) {
      // First run
    }

    // Check duplicate
    if (signups.some(s => s.email === cleanEmail)) {
      return {
        statusCode: 409,
        headers,
        body: JSON.stringify({ error: 'Already on the list' })
      };
    }

    // Add entry
    signups.push({
      email: cleanEmail,
      timestamp: new Date().toISOString(),
      ip_hint: (event.headers['x-forwarded-for'] || '').split(',')[0] || ''
    });

    fs.writeFileSync(DATA_FILE, JSON.stringify(signups, null, 2));

    // Also log to build logs so we can see signups
    console.log('📝 WAITLIST SIGNUP:', cleanEmail, '| Total:', signups.length);

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ status: 'ok', message: "You're on the list!" })
    };
  } catch (err) {
    console.error('❌ WAITLIST ERROR:', err.message);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: 'Server error' })
    };
  }
};

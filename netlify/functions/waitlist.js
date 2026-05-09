// Netlify function — CommonJS format
// Netlify auto-detects functions in netlify/functions/
// Accessed via /.netlify/functions/waitlist
// We'll redirect /api/waitlist → /.netlify/functions/waitlist via netlify.toml

exports.handler = async function(event, context) {
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS'
  };

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
    const { email, name } = JSON.parse(event.body || '{}');

    if (!email || !email.includes('@')) {
      return {
        statusCode: 400,
        headers,
        body: JSON.stringify({ error: 'Valid email required' })
      };
    }

    console.log('📝 SIGNUP:', JSON.stringify({
      email: email.toLowerCase().trim(),
      name: name || '',
      time: new Date().toISOString()
    }));

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ status: 'ok', message: "You're on the list!" })
    };
  } catch (err) {
    return {
      statusCode: 400,
      headers,
      body: JSON.stringify({ error: 'Invalid request' })
    };
  }
};

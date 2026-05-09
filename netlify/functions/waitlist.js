// Netlify serverless function — captures waitlist signups
// Deploy to Netlify (free tier). Signups captured in function logs.

exports.handler = async function(event, context) {
  // CORS headers
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS'
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  try {
    const { email, name } = JSON.parse(event.body || '{}');

    if (!email || !email.includes('@')) {
      return { 
        statusCode: 400, headers, 
        body: JSON.stringify({ error: 'Valid email is required' }) 
      };
    }

    console.log('SIGNUP:', JSON.stringify({
      email: email.toLowerCase().trim(),
      name: name || '',
      timestamp: new Date().toISOString()
    }));

    // Also save to Netlify Build plugins store (persistent)
    // For now: logged, you can check logs in Netlify dashboard

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({ status: 'ok', message: "You're on the list!" })
    };
  } catch (err) {
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({ error: 'Server error' })
    };
  }
};

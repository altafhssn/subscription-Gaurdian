// Vercel Edge Function — works on all plans
// Edge functions are detected differently than serverless

export const config = {
  runtime: 'edge'
};

export default async function handler(req) {
  // Only accept POST
  if (req.method === 'OPTIONS') {
    return new Response(null, {
      status: 200,
      headers: {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type'
      }
    });
  }

  if (req.method !== 'POST') {
    return new Response(JSON.stringify({ error: 'Only POST accepted' }), {
      status: 405,
      headers: { 'content-type': 'application/json' }
    });
  }

  try {
    const { email, name } = await req.json();

    if (!email || !email.includes('@')) {
      return new Response(JSON.stringify({ error: 'Valid email required' }), {
        status: 400,
        headers: { 'content-type': 'application/json' }
      });
    }

    console.log('SIGNUP:', JSON.stringify({
      email: email.toLowerCase().trim(),
      name: name || '',
      time: new Date().toISOString()
    }));

    return new Response(JSON.stringify({ status: 'ok', message: "You're on the list!" }), {
      status: 200,
      headers: {
        'content-type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      }
    });
  } catch (err) {
    return new Response(JSON.stringify({ error: 'Invalid request' }), {
      status: 400,
      headers: { 'content-type': 'application/json' }
    });
  }
}

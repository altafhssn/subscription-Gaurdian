// server.js — Subscription Guardian Backend
// Complete OAuth flow + scan + user management + privacy compliance
//
// Deploy to Railway/Render/Fly.io. Set env vars from .env.example.
// Database: PostgreSQL (free tier on Railway, Supabase, or Neon)

require('dotenv').config();
const express = require('express');
const { google } = require('googleapis');
const { Pool } = require('pg');
const crypto = require('crypto');
const cors = require('cors');
const cookieParser = require('cookie-parser');
const helmet = require('helmet');
const rateLimit = require('express-rate-limit');
const fs = require('fs');
const path = require('path');
const { encryptToken, decryptToken, initDb, deleteUserData } = require('./db');

// Validate required env at startup
const REQUIRED_ENV = ['APP_URL', 'ENCRYPTION_KEY', 'DATABASE_URL', 'GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET'];
for (const key of REQUIRED_ENV) {
  if (!process.env[key]) {
    console.error(`FATAL: Missing required env variable: ${key}`);
    process.exit(1);
  }
}

const app = express();

// Security headers
app.use(helmet());

// CORS — validated APP_URL prevents undefined fallback
app.use(cors({ origin: process.env.APP_URL, credentials: true }));

// Body parsing with size limit
app.use(express.json({ limit: '10kb' }));
app.use(cookieParser());

// Static files
app.use(express.static('public'));

// Global rate limiters
const authLimiter = rateLimit({
  windowMs: 60 * 1000, // 1 minute
  max: 5,
  message: { error: 'Too many requests. Try again in a minute.' }
});
const apiLimiter = rateLimit({
  windowMs: 60 * 1000,
  max: 60,
  message: { error: 'Rate limit exceeded.' }
});

// Serve landing page
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'index.html'));
});

// Serve dashboard (after OAuth redirect)
app.get('/dashboard', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'dashboard.html'));
});

// Database connection
const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  // Use rejectUnauthorized: true in production for proper TLS
  // For Railway/Neon/Supabase, provide the CA cert if needed
  ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: true } : false
});

// Google OAuth config
const oauth2Client = new google.auth.OAuth2(
  process.env.GOOGLE_CLIENT_ID,
  process.env.GOOGLE_CLIENT_SECRET,
  process.env.GOOGLE_REDIRECT_URI
);

const SCOPES = ['https://www.googleapis.com/auth/gmail.readonly'];

// ===============================================================
// ROUTES
// ===============================================================

// 1. PRIVACY POLICY
app.get('/privacy', (req, res) => {
  res.send(`<!DOCTYPE html>
<html><head><title>Privacy Policy — Subscription Guardian</title>
<style>body{font-family:sans-serif;max-width:700px;margin:40px auto;padding:0 20px;line-height:1.6;color:#333}h1{color:#16a34a}</style></head>
<body>
<h1>Privacy Policy</h1>
<p><em>Last updated: May 2026</em></p>

<h2>What we collect</h2>
<p>When you connect your Gmail account, we request <strong>read-only</strong> access to your Gmail inbox. We only scan emails that contain subscription receipts, invoices, and payment confirmations.</p>

<h2>How we use your data</h2>
<ul>
  <li>Identify subscriptions you're paying for</li>
  <li>Extract service name, amount, billing cycle, and renewal dates</li>
  <li>Show you your total subscription spend in one dashboard</li>
</ul>

<h2>What we don't do</h2>
<ul>
  <li>We never send emails from your account</li>
  <li>We never delete or modify your emails</li>
  <li>We never access your bank, credit card, or financial accounts</li>
  <li>We never share your data with third parties</li>
</ul>

<h2>Data storage & retention</h2>
<p>We store only the subscription data extracted from your emails (service name, amount, dates). Your actual email content is scanned in memory and not permanently stored. We retain your subscription data for <strong>90 days</strong> after your last activity. You can delete all your data at any time.</p>

<h2>Token security</h2>
<p>Your Gmail access tokens are encrypted using AES-256-GCM before storage. We use industry-standard encryption and never store tokens in plaintext.</p>

<h2>Your rights</h2>
<ul>
  <li>Delete your account and all data — <a href="/account/delete">click here</a></li>
  <li>Revoke Gmail access at any time via <a href="https://myaccount.google.com/permissions">Google Account Permissions</a></li>
  <li>Export your data — contact us</li>
</ul>

<h2>Contact</h2>
<p>hello@subscriptionguardian.com</p>

<h2>Business info</h2>
<p>Subscription Guardian is operated as a sole proprietorship. Registered in India.</p>
</body></html>`);
});

// 2. TERMS OF SERVICE
app.get('/terms', (req, res) => {
  res.send(`<!DOCTYPE html>
<html><head><title>Terms of Service — Subscription Guardian</title>
<style>body{font-family:sans-serif;max-width:700px;margin:40px auto;padding:0 20px;line-height:1.6;color:#333}h1{color:#16a34a}</style></head>
<body>
<h1>Terms of Service</h1>
<p><em>Last updated: May 2026</em></p>

<h2>Service</h2>
<p>Subscription Guardian scans your Gmail inbox for subscription receipts and presents them in a dashboard. We provide read-only access and do not modify your email or financial accounts.</p>

<h2>Payment</h2>
<p>Guardian plan is $3/month. Cancel anytime. No refunds for partial months.</p>

<h2>Limitations</h2>
<ul>
  <li>We may miss subscriptions that don't send email receipts</li>
  <li>We are not a financial advisor — we show data, not recommendations</li>
  <li>Service availability depends on Google's API availability</li>
</ul>

<h2>Data deletion</h2>
<p>You can delete your account and all associated data at any time. After 90 days of inactivity, data is automatically purged.</p>

<h2>Liability</h2>
<p>Subscription Guardian is provided "as is." We are not liable for missed subscriptions, incorrect data, or financial decisions based on our scans.</p>
</body></html>`);
});

// 3. INITIATE GMAIL OAUTH
app.get('/auth/gmail', authLimiter, (req, res) => {
  const state = crypto.randomBytes(16).toString('hex');
  res.cookie('oauth_state', state, { 
    httpOnly: true, 
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    maxAge: 10 * 60 * 1000 // 10 minutes
  });
  
  const authUrl = oauth2Client.generateAuthUrl({
    access_type: 'offline',
    scope: SCOPES,
    state: state,
    prompt: 'consent' // Force refresh token on every auth
  });
  
  res.redirect(authUrl);
});

// 4. OAUTH CALLBACK
app.get('/auth/callback', authLimiter, async (req, res) => {
  const { code, state, error } = req.query;
  
  if (error) {
    return res.redirect('/?error=' + error);
  }
  
  // Verify state to prevent CSRF
  const storedState = req.cookies.oauth_state;
  if (!state || state !== storedState) {
    return res.redirect('/?error=invalid_state');
  }
  
  try {
    // Exchange auth code for tokens
    const { tokens } = await oauth2Client.getToken(code);
    
    // Get user's email from Google
    oauth2Client.setCredentials(tokens);
    const gmail = google.gmail({ version: 'v1', auth: oauth2Client });
    const profile = await gmail.users.getProfile({ userId: 'me' });
    const email = profile.data.emailAddress;
    
    // Encrypt tokens before storing
    const encAccess = encryptToken(tokens.access_token);
    const encRefresh = tokens.refresh_token 
      ? encryptToken(tokens.refresh_token) 
      : null;
    
    // Generate session token and store hash
    const sessionToken = crypto.randomBytes(32).toString('hex');
    const sessionHash = crypto.createHash('sha256').update(sessionToken).digest('hex');
    
    // Store or update user in database
    await pool.query(`
      INSERT INTO users (email, google_id, encrypted_access_token, encrypted_refresh_token, token_iv, token_auth_tag, session_token, last_scan_at)
      VALUES ($1, $2, $3, $4, $5, $6, $7, NOW())
      ON CONFLICT (email) DO UPDATE SET
        encrypted_access_token = EXCLUDED.encrypted_access_token,
        encrypted_refresh_token = COALESCE(EXCLUDED.encrypted_refresh_token, users.encrypted_refresh_token),
        token_iv = EXCLUDED.token_iv,
        token_auth_tag = EXCLUDED.token_auth_tag,
        session_token = EXCLUDED.session_token,
        last_scan_at = NOW()
    `, [
      email,
      profile.data.emailAddress,
      encAccess.encrypted,
      encRefresh ? encRefresh.encrypted : null,
      encAccess.iv + ':' + encAccess.authTag,
      null,
      sessionHash
    ]);
    
    res.cookie('session', sessionToken, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 30 * 24 * 60 * 60 * 1000 // 30 days
    });
    
    // Trigger first scan asynchronously
    res.redirect('/dashboard?scan=started');
    
    // Kick off background scan (don't await)
    scanUserEmails(email).catch(err => {
      console.error('Background scan failed for', email, err.message);
    });
    
  } catch (err) {
    console.error('OAuth callback error:', err.message);
    res.redirect('/?error=auth_failed');
  }
});

// 4.5 WAITLIST — capture early access emails
app.post('/api/waitlist', apiLimiter, async (req, res) => {
  const { email } = req.body;
  
  if (!email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    return res.status(400).json({ error: 'Valid email required' });
  }
  
  try {
    await pool.query(`
      INSERT INTO waitlist (email)
      VALUES ($1)
      ON CONFLICT (email) DO NOTHING
    `, [email.toLowerCase().trim()]);
    
    res.json({ success: true, message: 'You\'re on the list!' });
  } catch (err) {
    console.error('Waitlist error:', err.message);
    res.status(500).json({ error: 'Server error' });
  }
});

// 5. GET USER DASHBOARD DATA
app.get('/api/subscriptions', apiLimiter, async (req, res) => {
  try {
    const user = await getAuthenticatedUser(req);
    if (!user) return res.status(401).json({ error: 'Not authenticated' });
    
    const result = await pool.query(
      'SELECT * FROM subscriptions WHERE user_id = $1 ORDER BY amount DESC',
      [user.id]
    );
    
    // Calculate totals
    const total = result.rows.reduce((sum, s) => sum + parseFloat(s.amount || 0), 0);
    const byCategory = {};
    result.rows.forEach(s => {
      const cat = s.category || 'Other';
      byCategory[cat] = (byCategory[cat] || 0) + parseFloat(s.amount || 0);
    });
    
    res.json({
      subscriptions: result.rows,
      total_monthly: total,
      by_category: byCategory,
      count: result.rows.length
    });
    
  } catch (err) {
    console.error('API error:', err.message);
    res.status(500).json({ error: 'Server error' });
  }
});

// 6. DELETE ACCOUNT — COMPLETE DATA ERASURE
app.post('/account/delete', apiLimiter, async (req, res) => {
  try {
    const user = await getAuthenticatedUser(req);
    if (!user) return res.status(401).json({ error: 'Not authenticated' });
    
    await deleteUserData(pool, user.id);
    
    // Clear session from DB
    await pool.query('UPDATE users SET session_token = NULL WHERE id = $1', [user.id]);
    
    res.clearCookie('session');
    res.json({ success: true, message: 'All your data has been deleted permanently.' });
    
  } catch (err) {
    console.error('Delete error:', err.message);
    res.status(500).json({ error: 'Failed to delete data' });
  }
});

// 7. DELETE ACCOUNT PAGE (GET)
app.get('/account/delete', (req, res) => {
  res.send(`<!DOCTYPE html>
<html><head><title>Delete Account — Subscription Guardian</title>
<style>body{font-family:sans-serif;max-width:500px;margin:40px auto;padding:0 20px;line-height:1.6}h1{color:#dc2626}button{background:#dc2626;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:1rem;cursor:pointer}</style></head>
<body>
<h1>Delete Your Account</h1>
<p>This will permanently delete all your data — subscription records, scan history, and stored tokens. Your Gmail access can be revoked separately via Google Account Permissions.</p>
<form action="/account/delete" method="post">
<button type="submit" onclick="return confirm('Are you sure? This cannot be undone.')">Permanently Delete My Data</button>
</form>
</body></html>`);
});

// ===============================================================
// EMAIL SCANNING ENGINE
// ===============================================================

async function scanUserEmails(email) {
  const userResult = await pool.query('SELECT * FROM users WHERE email = $1', [email]);
  if (userResult.rows.length === 0) return;
  
  const user = userResult.rows[0];
  
  // Decrypt tokens
  const [iv, authTag] = user.token_iv.split(':');
  const accessToken = decryptToken(user.encrypted_access_token, iv, authTag);
  
  // Set up auth
  oauth2Client.setCredentials({
    access_token: accessToken,
    refresh_token: user.encrypted_refresh_token 
      ? decryptToken(user.encrypted_refresh_token, iv, authTag) 
      : null
  });
  
  const gmail = google.gmail({ version: 'v1', auth: oauth2Client });
  
  // Search for subscription-related emails
  const query = [
    'subject:(receipt OR invoice OR subscription OR "you\'ve been charged" OR "automatic payment" OR renewal OR "monthly payment")',
    'OR',
    'from:(noreply OR no-reply OR notification OR billing OR payments)',
    'newer_than:6m'
  ].join(' ');
  
  let emailsScanned = 0;
  let subsFound = 0;
  let newSubs = 0;
  
  try {
    const response = await gmail.users.messages.list({
      userId: 'me',
      q: query,
      maxResults: 50
    });
    
    const messages = response.data.messages || [];
    emailsScanned = messages.length;
    
    for (const msg of messages) {
      const detail = await gmail.users.messages.get({
        userId: 'me',
        id: msg.id,
        format: 'metadata',
        metadataHeaders: ['From', 'Subject', 'Date']
      });
      
      const headers = detail.data.payload.headers;
      const from = headers.find(h => h.name === 'From')?.value || '';
      const subject = headers.find(h => h.name === 'Subject')?.value || '';
      
      // Extract subscription info
      const sub = extractSubscription(from, subject);
      if (sub) {
        subsFound++;
        
        // Check if we already have this one
        const existing = await pool.query(
          'SELECT id FROM subscriptions WHERE user_id = $1 AND service_name = $2',
          [user.id, sub.service_name]
        );
        
        if (existing.rows.length === 0) {
          newSubs++;
          await pool.query(`
            INSERT INTO subscriptions (user_id, service_name, amount, currency, billing_cycle, category, status)
            VALUES ($1, $2, $3, $4, $5, $6, 'active')
          `, [user.id, sub.service_name, sub.amount, sub.currency, sub.billing_cycle, sub.category]);
        }
      }
    }
    
    // Log scan
    await pool.query(`
      INSERT INTO scan_log (user_id, emails_scanned, subscriptions_found, new_subscriptions)
      VALUES ($1, $2, $3, $4)
    `, [user.id, emailsScanned, subsFound, newSubs]);
    
    console.log(`Scan complete for ${email}: ${emailsScanned} emails, ${subsFound} subs, ${newSubs} new`);
    
  } catch (err) {
    // If token expired, try to refresh
    if (err.message.includes('Token expired') || err.message.includes('invalid_grant')) {
      try {
        const { credentials } = await oauth2Client.refreshAccessToken();
        const encAccess = encryptToken(credentials.access_token);
        const [oldIv, oldAuthTag] = user.token_iv.split(':');
        
        await pool.query(`
          UPDATE users SET 
            encrypted_access_token = $1,
            token_iv = $2
          WHERE email = $3
        `, [encAccess.encrypted, encAccess.iv + ':' + encAccess.authTag, email]);
        
        console.log('Refreshed token for', email);
      } catch (refreshErr) {
        console.error('Token refresh failed for', email, refreshErr.message);
      }
    } else {
      console.error('Scan error for', email, err.message);
    }
  }
}

// Known subscription services database
const KNOWN_SERVICES = [
  // Streaming
  { domains: ['netflix.com', 'mailer.netflix.com'], name: 'Netflix', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  { domains: ['spotify.com', 'no-reply@spotify.com'], name: 'Spotify', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  { domains: ['apple.com', 'no_reply@email.apple.com'], name: 'Apple', category: 'Streaming & Cloud', regex: /\$(\d+\.?\d*)/ },
  { domains: ['primevideo.com', 'amazon.com', 'auto-confirm@amazon.com'], name: 'Amazon Prime', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  { domains: ['disneyplus.com', 'disney.com'], name: 'Disney+', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  { domains: ['hulu.com'], name: 'Hulu', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  { domains: ['hbomax.com', 'max.com', 'warnermedia.com'], name: 'Max', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  { domains: ['peacocktv.com'], name: 'Peacock', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  { domains: ['youtube.com', 'youtubered.com'], name: 'YouTube Premium', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  { domains: ['paramountplus.com'], name: 'Paramount+', category: 'Streaming', regex: /\$(\d+\.?\d*)/ },
  
  // SaaS
  { domains: ['adobe.com', 'noreply@adobe.com'], name: 'Adobe', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['figma.com'], name: 'Figma', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['notion.so', 'notion.com'], name: 'Notion', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['github.com', 'github.com'], name: 'GitHub', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['slack.com'], name: 'Slack', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['zoom.us'], name: 'Zoom', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['microsoft.com', 'office.com'], name: 'Microsoft 365', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['dropbox.com'], name: 'Dropbox', category: 'Cloud Storage', regex: /\$(\d+\.?\d*)/ },
  { domains: ['google.com', 'noreply@google.com'], name: 'Google One', category: 'Cloud Storage', regex: /\$(\d+\.?\d*)/ },
  { domains: ['icloud.com'], name: 'iCloud', category: 'Cloud Storage', regex: /\$(\d+\.?\d*)/ },
  { domains: ['canva.com'], name: 'Canva', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['medium.com'], name: 'Medium', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  { domains: ['substack.com'], name: 'Substack', category: 'SaaS', regex: /\$(\d+\.?\d*)/ },
  
  // Fitness
  { domains: ['peloton.com'], name: 'Peloton', category: 'Fitness', regex: /\$(\d+\.?\d*)/ },
  { domains: ['myfitnesspal.com'], name: 'MyFitnessPal', category: 'Fitness', regex: /\$(\d+\.?\d*)/ },
  { domains: ['strava.com'], name: 'Strava', category: 'Fitness', regex: /\$(\d+\.?\d*)/ },
  { domains: ['calm.com', 'headspace.com'], name: 'Calm/Headspace', category: 'Wellness', regex: /\$(\d+\.?\d*)/ },
  
  // UK-specific
  { domains: ['nowtv.com', 'sky.com'], name: 'Now TV / Sky', category: 'Streaming', regex: /\£(\d+\.?\d*)/ },
  { domains: ['audible.co.uk', 'audible.com'], name: 'Audible', category: 'Streaming', regex: /\£(\d+\.?\d*)/ },
  { domains: ['britbox.com'], name: 'BritBox', category: 'Streaming', regex: /\£(\d+\.?\d*)/ },
];

function extractSubscription(from, subject) {
  const lowerFrom = (from || '').toLowerCase();
  const lowerSubject = (subject || '').toLowerCase();
  
  // Check against known services
  for (const service of KNOWN_SERVICES) {
    if (service.domains.some(d => lowerFrom.includes(d))) {
      // Try to extract amount from subject
      const amountMatch = lowerSubject.match(service.regex) || lowerFrom.match(service.regex);
      const amount = amountMatch ? parseFloat(amountMatch[1]) : null;
      
      // Determine billing cycle from subject
      let cycle = 'monthly';
      if (lowerSubject.includes('yearly') || lowerSubject.includes('annual')) cycle = 'yearly';
      if (lowerSubject.includes('weekly')) cycle = 'weekly';
      
      return {
        service_name: service.name,
        amount: amount || 0,
        currency: 'USD',
        billing_cycle: cycle,
        category: service.category
      };
    }
  }
  
  // Unknown service — return generic
  return null;
}

// ===============================================================
// AUTH MIDDLEWARE
// ===============================================================

async function getAuthenticatedUser(req) {
  const sessionToken = req.cookies.session;
  if (!sessionToken) return null;
  
  // Look up user by session token hash
  const sessionHash = crypto.createHash('sha256').update(sessionToken).digest('hex');
  const result = await pool.query(
    'SELECT * FROM users WHERE session_token = $1',
    [sessionHash]
  );
  return result.rows[0] || null;
}

// ===============================================================
// START
// ===============================================================

const PORT = process.env.PORT || 3000;
async function start() {
  try {
    // Auto-create database tables on first run
    await initDb(pool);
    
    app.listen(PORT, () => {
      console.log(`Subscription Guardian running on port ${PORT}`);
      console.log(`OAuth callback: ${process.env.GOOGLE_REDIRECT_URI || 'http://localhost:' + PORT + '/auth/callback'}`);
      console.log(`Privacy policy: http://localhost:${PORT}/privacy`);
      console.log(`Terms: http://localhost:${PORT}/terms`);
    });
  } catch (err) {
    console.error('Failed to initialize:', err.message);
    process.exit(1);
  }
}

start();

// db.js — Database setup + encrypted token storage + auto-migration
const crypto = require('crypto');

// AES-256-GCM encryption for tokens
const ALGORITHM = 'aes-256-gcm';

function getEncryptionKey() {
  const key = process.env.ENCRYPTION_KEY;
  if (!key || key.length < 64) {
    throw new Error('ENCRYPTION_KEY must be at least 64 hex characters (32 bytes)');
  }
  return Buffer.from(key, 'hex');
}

function encryptToken(token) {
  const key = getEncryptionKey();
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv(ALGORITHM, key, iv);
  let encrypted = cipher.update(token, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  const authTag = cipher.getAuthTag().toString('hex');
  return { encrypted, iv: iv.toString('hex'), authTag };
}

function decryptToken(encrypted, iv, authTag) {
  const key = getEncryptionKey();
  const decipher = crypto.createDecipheriv(ALGORITHM, key, Buffer.from(iv, 'hex'));
  decipher.setAuthTag(Buffer.from(authTag, 'hex'));
  let decrypted = decipher.update(encrypted, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
}

// Auto-create tables on startup (Railway-friendly)
async function initDb(pool) {
  const queries = [
    `CREATE TABLE IF NOT EXISTS users (
      id SERIAL PRIMARY KEY,
      email VARCHAR(255) UNIQUE NOT NULL,
      google_id VARCHAR(255) UNIQUE,
      encrypted_access_token TEXT,
      encrypted_refresh_token TEXT,
      token_iv TEXT,
      session_token TEXT,
      plan VARCHAR(20) DEFAULT 'free',
      stripe_customer_id VARCHAR(255),
      created_at TIMESTAMP DEFAULT NOW(),
      last_scan_at TIMESTAMP,
      data_retention_date TIMESTAMP DEFAULT (NOW() + INTERVAL '90 days')
    )`,
    `CREATE TABLE IF NOT EXISTS subscriptions (
      id SERIAL PRIMARY KEY,
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      service_name VARCHAR(255) NOT NULL,
      service_logo VARCHAR(500),
      amount DECIMAL(10,2),
      currency VARCHAR(10) DEFAULT 'USD',
      billing_cycle VARCHAR(50),
      next_billing_date DATE,
      category VARCHAR(100),
      status VARCHAR(20) DEFAULT 'active',
      cancel_url TEXT,
      last_receipt_date DATE,
      created_at TIMESTAMP DEFAULT NOW()
    )`,
    `CREATE TABLE IF NOT EXISTS waitlist (
      id SERIAL PRIMARY KEY,
      email VARCHAR(255) UNIQUE NOT NULL,
      referrer VARCHAR(255),
      signed_up_at TIMESTAMP DEFAULT NOW(),
      converted_to_user BOOLEAN DEFAULT FALSE
    )`,
    `CREATE TABLE IF NOT EXISTS scan_log (
      id SERIAL PRIMARY KEY,
      user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
      scanned_at TIMESTAMP DEFAULT NOW(),
      emails_scanned INTEGER DEFAULT 0,
      subscriptions_found INTEGER DEFAULT 0,
      new_subscriptions INTEGER DEFAULT 0
    )`
  ];

  for (const sql of queries) {
    await pool.query(sql);
  }
  console.log('Database tables initialized');
}

async function cleanupExpiredUsers(pool) {
  const result = await pool.query(`
    DELETE FROM users 
    WHERE data_retention_date < NOW() 
    RETURNING id, email
  `);
  return result.rows;
}

async function deleteUserData(pool, userId) {
  const result = await pool.query(
    'DELETE FROM users WHERE id = $1 RETURNING email',
    [userId]
  );
  return result.rows[0];
}

module.exports = {
  encryptToken,
  decryptToken,
  initDb,
  cleanupExpiredUsers,
  deleteUserData
};

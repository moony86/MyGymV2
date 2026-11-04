"""Password hashes and expiring opaque sessions, separate from training records."""
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3
import time

ENABLED = os.getenv('MYGYM_AUTH_ENABLED', '1') != '0'
DB = Path(os.getenv('MYGYM_AUTH_DB', str(Path(os.getenv('DB_PATH', './gym_tracker.db')).resolve().with_name('mygym_auth.sqlite3'))))
BOOTSTRAP = Path(os.getenv('MYGYM_BOOTSTRAP_FILE', str(DB.parent / 'secrets/mygym-bootstrap.txt')))
TTL = 7 * 86400
REMEMBER_TTL = 90 * 86400
REMEMBER_LIMIT = 180 * 86400

def connect():
    db = sqlite3.connect(DB, timeout=10)
    db.row_factory = sqlite3.Row
    return db

def initialize():
    DB.parent.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS accounts (
            profile_id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL, is_admin INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS sessions (
            token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL,
            csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS remembered_sessions (
            token_hash TEXT PRIMARY KEY, absolute_expires REAL NOT NULL);
        ''')
    DB.chmod(0o600)
    if not has_accounts():
        BOOTSTRAP.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(BOOTSTRAP, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w') as out:
                out.write(secrets.token_urlsafe(32) + '\n')
        except FileExistsError:
            BOOTSTRAP.chmod(0o600)

def has_accounts():
    with connect() as db:
        return bool(db.execute('SELECT 1 FROM accounts LIMIT 1').fetchone())

def normalize(username):
    return username.strip().casefold()

def password_hash(password):
    if not 12 <= len(password) <= 128:
        raise ValueError('Password must contain 12 to 128 characters')
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return salt.hex() + '$' + value.hex()

def verify(password, encoded):
    try:
        salt, expected = encoded.split('$')
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False

def account_for_username(username):
    with connect() as db:
        row = db.execute('SELECT * FROM accounts WHERE username=?', (normalize(username),)).fetchone()
        return dict(row) if row else None

def save_account(profile_id, username, password, bootstrap=None):
    username = normalize(username)
    if not username or len(username) > 80:
        raise ValueError('Username must contain 1 to 80 characters')
    encoded = password_hash(password)
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        if bootstrap is not None:
            if db.execute('SELECT 1 FROM accounts LIMIT 1').fetchone():
                raise ValueError('Initial setup has already completed')
            try:
                expected = BOOTSTRAP.read_text().strip()
            except OSError:
                raise ValueError('Initial setup key is unavailable')
            if not hmac.compare_digest(bootstrap, expected):
                raise ValueError('Invalid initial setup key')
        existing = db.execute('SELECT is_admin FROM accounts WHERE profile_id=?', (profile_id,)).fetchone()
        admin = 1 if bootstrap is not None else (existing['is_admin'] if existing else 0)
        db.execute('INSERT INTO accounts(profile_id,username,password_hash,is_admin) VALUES(?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET username=excluded.username,password_hash=excluded.password_hash', (profile_id,username,encoded,admin))
        db.execute('DELETE FROM sessions WHERE profile_id=?', (profile_id,))
        db.execute('DELETE FROM remembered_sessions WHERE token_hash NOT IN (SELECT token_hash FROM sessions)')
    if bootstrap is not None:
        BOOTSTRAP.unlink(missing_ok=True)

def new_session(profile_id, remember=False):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
    now = time.time()
    digest = hashlib.sha256(token.encode()).hexdigest()
    with connect() as db:
        db.execute('DELETE FROM sessions WHERE expires<=?', (now,))
        db.execute('DELETE FROM remembered_sessions WHERE token_hash NOT IN (SELECT token_hash FROM sessions)')
        db.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest,profile_id,csrf,now+(REMEMBER_TTL if remember else TTL)))
        if remember:
            db.execute('INSERT INTO remembered_sessions VALUES(?,?)', (digest,now+REMEMBER_LIMIT))
    return token, csrf


def session(token):
    if not token or len(token) > 200:
        return None
    with connect() as db:
        now = time.time()
        row = db.execute("""SELECT a.profile_id,a.username,a.is_admin,s.csrf,s.expires,r.absolute_expires
            FROM sessions s JOIN accounts a ON s.profile_id=a.profile_id
            LEFT JOIN remembered_sessions r ON r.token_hash=s.token_hash
            WHERE s.token_hash=? AND s.expires>? AND (r.absolute_expires IS NULL OR r.absolute_expires>?)""",
            (hashlib.sha256(token.encode()).hexdigest(),now,now)).fetchone()
        return dict(row) if row else None


def renew_remembered(token, account):
    """Renew at most daily; never revive an expired or revoked session."""
    now = time.time()
    absolute = account.get('absolute_expires')
    if absolute is None or absolute <= now or account['expires'] >= now+REMEMBER_TTL-86400:
        return None
    expiry = min(now+REMEMBER_TTL,absolute)
    if expiry <= account['expires']:
        return None
    with connect() as db:
        updated = db.execute("""UPDATE sessions SET expires=? WHERE token_hash=? AND expires>?
            AND expires<? AND EXISTS (SELECT 1 FROM remembered_sessions r
            WHERE r.token_hash=sessions.token_hash AND r.absolute_expires>=?)""",
            (expiry,hashlib.sha256(token.encode()).hexdigest(),now,expiry,expiry))
        return expiry if updated.rowcount else None


def revoke(token):
    with connect() as db:
        digest = hashlib.sha256((token or '').encode()).hexdigest()
        db.execute('DELETE FROM sessions WHERE token_hash=?', (digest,))
        db.execute('DELETE FROM remembered_sessions WHERE token_hash=?', (digest,))


if ENABLED:
    initialize()

"""
One-time (but safe-to-rerun) schema setup for the NexusAI Postgres database.

Run this manually whenever you need to (re)create the tables — e.g. the
first time you point the app at a fresh Postgres instance. It's written
with `IF NOT EXISTS` throughout, so rerunning it against a database that
already has the tables is a no-op rather than an error or data loss.

Usage:
    python init_db.py

Requires DATABASE_URL to be set in the environment (or in backend/.env,
loaded the same way main.py loads other env vars).
"""

import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()  # picks up backend/.env if present, same as the rest of the app

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Set it in your environment or in backend/.env "
        "before running this script."
    )

SCHEMA = """
CREATE TABLE IF NOT EXISTS client (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    location TEXT,
    contact_name TEXT,
    contact_phone TEXT,
    token TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    camera_count INTEGER
);

CREATE TABLE IF NOT EXISTS nvrs (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    ip_address TEXT,
    username TEXT,
    password TEXT,
    channel_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cameras (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    nvr_id INTEGER REFERENCES nvrs(id) ON DELETE CASCADE,
    channel_id INTEGER,
    ip_address TEXT,
    username TEXT,
    password TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('active', 'pending', 'error')),
    last_alert TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS qrcode (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    token TEXT,
    url TEXT,
    image_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE cameras ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS last_alert_at TIMESTAMP;

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    client_id INTEGER NOT NULL REFERENCES client(id) ON DELETE CASCADE,
    camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    alert_type TEXT NOT NULL CHECK (alert_type IN ('Theft', 'Threat', 'Weapon')),
    confidence NUMERIC(5,2),
    media_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_alerts_client_created ON alerts (client_id, created_at DESC);
"""

def main():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA)
        print("Schema applied successfully (tables created if they didn't already exist).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
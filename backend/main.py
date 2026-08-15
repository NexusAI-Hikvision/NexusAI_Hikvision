import base64
import logging
import os
import secrets
import subprocess
import sys
from contextlib import closing
from urllib.parse import quote
import psycopg2
import psycopg2.extras
from dotenv import dotenv_values
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from generate_qr_code import build_qr
from isapi_auth import verify_camera_auth

import random
import random
from datetime import datetime, timedelta
import requests
from fastapi.responses import PlainTextResponse

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

BASE_URL = os.getenv("BASE_URL", "https://getnexusai.co.za")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("nexusai")

app = FastAPI(title="NexusAI API")

# NOTE: allow_origins=["*"] is fine for local dev. Before deploying anywhere
# public, replace this with the exact origin(s) your frontend is served from
# (e.g. ["https://nexusai.co.za"]) - a wildcard origin combined with mutable
# server state (DB writes, spawning processes) is a soft target.
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")
QR_DIR = os.path.join(BASE_DIR, "qrcodes")
RELAY_SCRIPT = os.path.join(BASE_DIR, "nexus_isapi_relay.py")
os.makedirs(QR_DIR, exist_ok=True)

# Base config shared by every relay (e.g. the installer's own Discord
# webhook, if you want one default for every client). Anything client
# specific is layered on top per-connection below and passed straight to
# the subprocess environment - it is never written back into the shared
# .env file, so multiple clients' relays can run side-by-side without
# clobbering each other's NVR credentials.
_BASE_ENV = dotenv_values(ENV_PATH) if os.path.exists(ENV_PATH) else {}

# token -> subprocess.Popen, so a client reconnecting (new IP, fixed
# password, etc.) restarts its relay instead of leaving an orphaned
# process running forever alongside a new one.
_RUNNING_RELAYS: dict[str, subprocess.Popen] = {}

def _get_client_or_404(cur, token: str):
    cur.execute("SELECT * FROM client WHERE token = %s", (token,))
    row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown or expired token.")
    return row


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set.")
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


# ---------------------------------------------------------------------------
# Client intake / QR code generation
# ---------------------------------------------------------------------------

class ClientForm(BaseModel):
    name: str
    location: str
    contact_person: str
    contact_phone: str
    camera_count: int = Field(ge=1, le=128)


@app.post("/generate-qr")
def generate_qr(data: ClientForm):
    token = secrets.token_hex(16)

    try:
        with closing(get_db()) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO client (name, location, contact_name, contact_phone, token, camera_count)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (data.name, data.location, data.contact_person, data.contact_phone, token, data.camera_count),
            )
            client_id = cur.fetchone()["id"]

            # Only the token needs to travel in the URL - it's the one thing
            # the connect-camera page actually needs, and the server looks
            # up everything else from the DB. This also keeps the client's
            # name/phone number out of a URL that might land in browser
            # history, server access logs, or a QR-scanning app's history.
            url = f"{BASE_URL}/connect_camera.html?token={quote(token)}"

            image_path = os.path.join(QR_DIR, f"{token}.png")
            build_qr(url, image_path)

            cur.execute(
                """
                INSERT INTO qrcode (client_id, token, url, image_path)
                VALUES (%s, %s, %s, %s)
                """,
                (client_id, token, url, image_path),
            )
            conn.commit()
    except psycopg2.Error:
        log.exception("Database error while generating QR code")
        raise HTTPException(status_code=500, detail="Could not save client record. Please try again.")

    with open(image_path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode()

    return {"url": url, "token": token, "qr_image_base64": img_base64}


# ---------------------------------------------------------------------------
# Lookup used by connect_camera.html to prefill client details from the
# token embedded in the QR code, instead of asking the technician to
# re-type things (or worse, trusting values sent from the browser).
# ---------------------------------------------------------------------------

@app.get("/client/{token}")
def get_client(token: str):
    with closing(get_db()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT name, location, camera_count FROM client WHERE token = %s", (token,)
        )
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Unknown or expired token.")

    return {"name": row["name"], "location": row["location"], "camera_count": row["camera_count"]}


# ---------------------------------------------------------------------------
# NVR Onboarding & ISAPI Authentication
# ---------------------------------------------------------------------------

class NVRConnectRequest(BaseModel):
    token: str
    ip: str
    port: int = Field(default=80, ge=1, le=65535)
    username: str
    password: str


class ConnectCameraResponse(BaseModel):
    status: str
    message: str


@app.post("/connect-nvr", response_model=ConnectCameraResponse)
def connect_nvr(payload: NVRConnectRequest):
    with closing(get_db()) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, camera_count FROM client WHERE token = %s", (payload.token,)
        )
        client_row = cur.fetchone()

        if client_row is None:
            raise HTTPException(status_code=404, detail="Unknown or expired token. Please rescan your QR code.")

        # 1. Verify connection to the NVR via ISAPI digest auth
        result = verify_camera_auth(
            ip=payload.ip,
            port=payload.port,
            username=payload.username,
            password=payload.password,
        )

        if not result["success"]:
            return {
                "status": "error",
                "message": "Please check your NVR IP, username, or password.",
            }

        # 2. Upsert the NVR record, then ensure one `cameras` row exists per
        #    channel (not one row for the whole NVR) — this is what lets a
        #    single QR/NVR connection populate the dashboard with all of a
        #    site's cameras instead of just one.
        cur.execute(
            "SELECT id FROM nvrs WHERE client_id = %s", (client_row["id"],)
        )
        existing_nvr = cur.fetchone()
        if existing_nvr:
            cur.execute("""
                UPDATE nvrs SET ip_address = %s, username = %s, password = %s, channel_count = %s
                WHERE id = %s
            """, (payload.ip, payload.username, payload.password, client_row["camera_count"], existing_nvr["id"]))
            nvr_id = existing_nvr["id"]
        else:
            cur.execute("""
                INSERT INTO nvrs (client_id, ip_address, username, password, channel_count)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (client_row["id"], payload.ip, payload.username, payload.password, client_row["camera_count"]))
            nvr_id = cur.fetchone()["id"]

        cur.execute(
            "SELECT channel_id FROM cameras WHERE nvr_id = %s", (nvr_id,)
        )
        existing_channels = cur.fetchall()
        existing_channel_ids = {row["channel_id"] for row in existing_channels}

        for channel_num in range(1, client_row["camera_count"] + 1):
            if channel_num not in existing_channel_ids:
                cur.execute("""
                    INSERT INTO cameras (client_id, nvr_id, channel_id, status)
                    VALUES (%s, %s, %s, 'pending')
                """, (client_row["id"], nvr_id, channel_num))

        conn.commit()

    # 3. Launch a background ISAPI relay dedicated to this client. Config is
    #    passed straight into the subprocess's environment rather than
    #    written to the shared .env file, so this works correctly with more
    #    than one client connected at the same time. If this client already
    #    had a relay running (e.g. they reconnected with new credentials),
    #    stop the old one first.
    _stop_relay(payload.token)

    relay_env = {
        **os.environ,
        **_BASE_ENV,
        "NVR_IP": payload.ip,
        "NVR_PORT": str(payload.port),
        "NVR_USER": payload.username,
        "NVR_PASS": payload.password,
        "NUM_CAMERAS": str(client_row["camera_count"] or 1),
        "CLIENT_TOKEN": payload.token,
        "CLIENT_NAME": client_row["name"],
    }

    try:
        proc = subprocess.Popen([sys.executable, RELAY_SCRIPT], env=relay_env)
        _RUNNING_RELAYS[payload.token] = proc
    except OSError:
        log.exception("Failed to start relay process for client %s", client_row["name"])
        raise HTTPException(status_code=500, detail="NVR authenticated, but the alert relay failed to start.")

    return {
        "status": "success",
        "message": f"NVR connected successfully with {client_row['camera_count']} channel(s). ISAPI relay started!",
    }


def _stop_relay(token: str):
    proc = _RUNNING_RELAYS.pop(token, None)
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@app.get("/health")
def health():
    return {"status": "ok"}

app.mount(
    "/",
    StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend"), html=True),
    name="frontend",
)

@app.get("/api/dashboard/{token}")
def get_dashboard(token: str):
    with closing(get_db()) as conn:
        cur = conn.cursor()
        client = _get_client_or_404(cur, token)

        cur.execute(
            "SELECT id, channel_id, name, status, last_alert_at FROM cameras WHERE client_id = %s ORDER BY channel_id",
            (client["id"],),
        )
        cameras = cur.fetchall()

        cur.execute(
            """
            SELECT COUNT(*) AS count FROM alerts
            WHERE client_id = %s AND created_at::date = CURRENT_DATE
            """,
            (client["id"],),
        )
        alerts_today = cur.fetchone()["count"]

    site_status = "Active" if any(c["status"] == "active" for c in cameras) else "Offline"

    camera_list = [
        {
            "id": c["id"],
            "name": c["name"] or f"Camera {c['channel_id']}",
            "status": c["status"],
            "last_alert_at": c["last_alert_at"].isoformat() if c["last_alert_at"] else None,
        }
        for c in cameras
    ]

    return {
        "site_name": client["name"],
        "status": site_status,
        "camera_count": len(cameras),
        "alerts_today": alerts_today,
        "cameras": camera_list,
    }

# ---------------------------------------------------------------------------
# Alert feed (optionally filtered to one camera, e.g. "last 5 for this cam")
# ---------------------------------------------------------------------------

@app.get("/api/alerts/{token}")
def get_alerts(token: str, limit: int = 50, camera_id: int | None = None):
    limit = min(limit, 50)
    with closing(get_db()) as conn:
        cur = conn.cursor()
        client = _get_client_or_404(cur, token)

        query = """
            SELECT a.id, a.alert_type, a.confidence, a.created_at,
                   c.id AS camera_id, COALESCE(c.name, 'Camera ' || c.channel_id) AS camera_name
            FROM alerts a
            JOIN cameras c ON c.id = a.camera_id
            WHERE a.client_id = %s
        """
        params = [client["id"]]

        if camera_id is not None:
            query += " AND a.camera_id = %s"
            params.append(camera_id)

        query += " ORDER BY a.created_at DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        {
            "id": r["id"],
            "camera_id": r["camera_id"],
            "camera_name": r["camera_name"],
            "type": r["alert_type"],
            "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
            "created_at": r["created_at"].isoformat(),
        }
        for r in rows
    ]

# ---------------------------------------------------------------------------
# Test Alert — proves the DB + Discord pipeline without any live NVR
# ---------------------------------------------------------------------------

@app.post("/api/test-alert/{token}")
def fire_test_alert(token: str):
    with closing(get_db()) as conn:
        cur = conn.cursor()
        client = _get_client_or_404(cur, token)

        cur.execute(
            "SELECT id, channel_id, name FROM cameras WHERE client_id = %s ORDER BY channel_id LIMIT 1",
            (client["id"],),
        )
        camera = cur.fetchone()
        if camera is None:
            raise HTTPException(status_code=400, detail="No cameras linked to this client yet.")

        alert_type = random.choice(["Theft", "Threat", "Weapon"])
        confidence = round(random.uniform(70, 99), 2)

        cur.execute(
            """
            INSERT INTO alerts (client_id, camera_id, alert_type, confidence)
            VALUES (%s, %s, %s, %s)
            RETURNING id, created_at
            """,
            (client["id"], camera["id"], alert_type, confidence),
        )
        alert_row = cur.fetchone()

        cur.execute(
            "UPDATE cameras SET last_alert_at = %s WHERE id = %s",
            (alert_row["created_at"], camera["id"]),
        )
        conn.commit()

    camera_name = camera["name"] or f"Camera {camera['channel_id']}"

    if DISCORD_WEBHOOK_URL:
        try:
            requests.post(
                DISCORD_WEBHOOK_URL,
                json={
                    "content": f"🧪 **[TEST]** {alert_type} detected on {camera_name} "
                               f"({client['name']}) — {confidence}% confidence"
                },
                timeout=5,
            )
        except requests.RequestException:
            log.exception("Discord webhook failed for test alert")
    else:
        log.warning("DISCORD_WEBHOOK_URL not set — test alert saved to DB but not sent to Discord")

    return {
        "status": "ok",
        "alert": {
            "id": alert_row["id"],
            "camera_name": camera_name,
            "type": alert_type,
            "confidence": confidence,
            "created_at": alert_row["created_at"].isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# Weekly report — plain text, per Aphile's spec
# ---------------------------------------------------------------------------

@app.get("/api/report/{token}")
def download_report(token: str):
    with closing(get_db()) as conn:
        cur = conn.cursor()
        client = _get_client_or_404(cur, token)

        cur.execute(
            """
            SELECT a.created_at, a.alert_type, a.confidence,
                   COALESCE(c.name, 'Camera ' || c.channel_id) AS camera_name
            FROM alerts a
            JOIN cameras c ON c.id = a.camera_id
            WHERE a.client_id = %s AND a.created_at >= %s
            ORDER BY a.created_at DESC
            """,
            (client["id"], datetime.utcnow() - timedelta(days=7)),
        )
        rows = cur.fetchall()

    lines = [f"NexusAI — Weekly Alert Report", f"Site: {client['name']}", f"Generated: {datetime.utcnow().isoformat()}Z", ""]
    if not rows:
        lines.append("No alerts in the last 7 days.")
    else:
        for r in rows:
            lines.append(f"{r['created_at']} | {r['camera_name']} | {r['alert_type']} | {r['confidence']}%")

    return PlainTextResponse("\n".join(lines), headers={
        "Content-Disposition": f"attachment; filename=nexusai_report_{token[:8]}.txt"
    })
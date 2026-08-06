import base64
import logging
import os
import secrets
import sqlite3
import subprocess
import sys
from contextlib import closing
from urllib.parse import quote

from dotenv import dotenv_values
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from generate_qr_code import build_qr
from isapi_auth import verify_camera_auth

BASE_URL = os.getenv("BASE_URL", "https://getnexusai.co.za")

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
DB_PATH = os.path.join(BASE_DIR, "NexusAI_Form_Database.db")
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


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
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
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (data.name, data.location, data.contact_person, data.contact_phone, token, data.camera_count),
            )
            client_id = cur.lastrowid

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
                VALUES (?, ?, ?, ?)
                """,
                (client_id, token, url, image_path),
            )
            conn.commit()
    except sqlite3.Error:
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
        row = conn.execute(
            "SELECT name, location, camera_count FROM client WHERE token = ?", (token,)
        ).fetchone()

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
        client_row = conn.execute(
            "SELECT id, name, camera_count FROM client WHERE token = ?", (payload.token,)
        ).fetchone()

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
        existing_nvr = conn.execute(
            "SELECT id FROM nvrs WHERE client_id = ?", (client_row["id"],)
        ).fetchone()
        if existing_nvr:
            conn.execute("""
                UPDATE nvrs SET ip_address = ?, username = ?, password = ?, channel_count = ?
                WHERE id = ?
            """, (payload.ip, payload.username, payload.password, client_row["camera_count"], existing_nvr["id"]))
            nvr_id = existing_nvr["id"]
        else:
            cur = conn.execute("""
                INSERT INTO nvrs (client_id, ip_address, username, password, channel_count)
                VALUES (?, ?, ?, ?, ?)
            """, (client_row["id"], payload.ip, payload.username, payload.password, client_row["camera_count"]))
            nvr_id = cur.lastrowid

        existing_channels = conn.execute(
            "SELECT channel_id FROM cameras WHERE nvr_id = ?", (nvr_id,)
        ).fetchall()
        existing_channel_ids = {row["channel_id"] for row in existing_channels}

        for channel_num in range(1, client_row["camera_count"] + 1):
            if channel_num not in existing_channel_ids:
                conn.execute("""
                    INSERT INTO cameras (client_id, nvr_id, channel_id, status)
                    VALUES (?, ?, ?, 'pending')
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
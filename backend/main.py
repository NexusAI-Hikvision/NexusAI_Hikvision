import sqlite3
import secrets
import base64
import os
from io import BytesIO

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from generate_qr_code import build_qr
from isapi_auth import verify_camera_auth

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "NexusAI_Form_Database.db")
QR_DIR = os.path.join(BASE_DIR, "qrcodes")
os.makedirs(QR_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Client intake / QR code generation
# ---------------------------------------------------------------------------

class ClientForm(BaseModel):
    name: str
    location: str
    contact_person: str
    contact_phone: str
    camera_count: int = Field(ge=1, le=10)


@app.post("/generate-qr")
def generate_qr(data: ClientForm):
    token = secrets.token_hex(16)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO client (name, location, contact_name, contact_phone, token)
        VALUES (?, ?, ?, ?, ?)
    """, (data.name, data.location, data.contact_person, data.contact_phone, token))
    client_id = cur.lastrowid

    url = (
        f"https://nexusai.co.za?"
        f"client={data.name}&location={data.location}"
        f"&contact={data.contact_person}&phone={data.contact_phone}"
        f"&cams={data.camera_count}&token={token}"
    )

    # NOTE: was previously "qrcodes/{token}.png" — relative to whatever
    # directory uvicorn was launched from, not to this file. Fixed to
    # always resolve to backend/qrcodes regardless of cwd.
    image_path = os.path.join(QR_DIR, f"{token}.png")
    img = build_qr(url, image_path)

    cur.execute("""
        INSERT INTO qrcode (client_id, token, url, image_path)
        VALUES (?, ?, ?, ?)
    """, (client_id, token, url, image_path))

    conn.commit()
    conn.close()

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    return {
        "url": url,
        "token": token,
        "qr_image_base64": img_base64
    }


# ---------------------------------------------------------------------------
# Camera connection / ISAPI authentication
# ---------------------------------------------------------------------------

class ConnectCameraRequest(BaseModel):
    ip: str
    port: int = Field(default=80, ge=1, le=65535)
    username: str
    password: str


class ConnectCameraResponse(BaseModel):
    status: str
    message: str


@app.post("/connect-camera", response_model=ConnectCameraResponse)
def connect_camera(payload: ConnectCameraRequest):
    result = verify_camera_auth(
        ip=payload.ip,
        port=payload.port,
        username=payload.username,
        password=payload.password,
    )

    if result["success"]:
        return {"status": "success", "message": "Camera connected successfully."}

    return {
        "status": "error",
        "message": "Please check your camera IP, username or password.",
    }


@app.get("/health")
def health():
    return {"status": "ok"}
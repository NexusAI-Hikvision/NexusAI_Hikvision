import os
import signal
import sys
import time
import xml.etree.ElementTree as ET

import requests
from dotenv import load_dotenv
from requests.auth import HTTPDigestAuth

# load_dotenv() does NOT override variables already present in the process
# environment by default, so when main.py launches this script with
# NVR_IP/NVR_PORT/etc. already set on the subprocess env (one relay per
# connected client), those take priority. Running this file directly still
# works by falling back to a local .env for manual testing.
load_dotenv()

NVR_IP = os.getenv("NVR_IP")
NVR_PORT = int(os.getenv("NVR_PORT", 80))
NVR_USER = os.getenv("NVR_USER")
NVR_PASS = os.getenv("NVR_PASS")
NUM_CAMERAS = int(os.getenv("NUM_CAMERAS", 1))
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

CLIENT_TOKEN = os.getenv("CLIENT_TOKEN", "")
CLIENT_NAME = os.getenv("CLIENT_NAME", "Unknown client")

ISAPI_URL = f"http://{NVR_IP}:{NVR_PORT}/ISAPI/Event/notification/alertStream"

# Reconnect handling: an unplugged camera or a Wi-Fi blip shouldn't kill
# the whole relay process. Back off between retries so a persistently
# unreachable NVR doesn't spin the CPU or spam logs.
INITIAL_BACKOFF = 2
MAX_BACKOFF = 60

_shutdown = False


def _handle_signal(signum, frame):
    global _shutdown
    _shutdown = True


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


def extract_channel_id(xml_data: str) -> str:
    try:
        root = ET.fromstring(xml_data)
        ns = {"ns": "http://www.hikvision.com/ver20/XMLSchema"}
        channel = root.find(".//channelID")
        if channel is None:
            channel = root.find(".//ns:channelID", ns)
        if channel is None:
            channel = root.find(".//dynChannelID")
        if channel is None:
            channel = root.find(".//ns:dynChannelID", ns)
        return channel.text if channel is not None else "Unknown"
    except ET.ParseError as e:
        print(f"[!] XML Parsing Error: {e}", flush=True)
        return "Unknown"


def send_discord_alert(channel_id: str, event_description: str = "Motion / VCA Event Detected"):
    if not DISCORD_WEBHOOK_URL:
        print("[!] Error: DISCORD_WEBHOOK_URL is not configured.", flush=True)
        return

    payload = {
        "embeds": [
            {
                "title": "\U0001f6a8 NVR Alert Stream Notification",
                "color": 15158332,
                "fields": [
                    {"name": "Client", "value": CLIENT_NAME, "inline": True},
                    {"name": "NVR IP", "value": f"`{NVR_IP}`", "inline": True},
                    {"name": "Camera Channel", "value": f"**Channel {channel_id}** (of {NUM_CAMERAS})", "inline": True},
                    {"name": "Event Details", "value": event_description, "inline": False},
                ],
                "footer": {"text": "Nexus AI Event Engine"},
            }
        ]
    }

    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        if res.status_code in (200, 204):
            print(f"[+] Alert successfully sent for Channel {channel_id}!", flush=True)
        else:
            print(f"[!] Discord webhook returned HTTP {res.status_code}", flush=True)
    except requests.exceptions.RequestException as e:
        print(f"[!] Failed to push to Discord: {e}", flush=True)


def _stream_once() -> bool:
    """Open the alert stream and read events until it drops or we're asked
    to shut down. Returns True if the connection was ever successfully
    established (used to decide whether to reset the reconnect backoff)."""
    print(f"[*] Connecting to NVR Alert Stream at {NVR_IP}:{NVR_PORT}...", flush=True)
    connected = False
    try:
        with requests.get(
            ISAPI_URL,
            auth=HTTPDigestAuth(NVR_USER, NVR_PASS),
            stream=True,
            timeout=60,
        ) as response:
            if response.status_code != 200:
                print(f"[!] NVR Connection Failed. HTTP Status: {response.status_code}", flush=True)
                return False

            print("[+] Successfully connected to NVR ISAPI Alert Stream.", flush=True)
            connected = True

            buffer = ""
            for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                if _shutdown:
                    break
                if not chunk:
                    continue
                buffer += chunk
                while "</EventNotificationAlert>" in buffer:
                    start_idx = buffer.find("<EventNotificationAlert")
                    end_idx = buffer.find("</EventNotificationAlert>") + len("</EventNotificationAlert>")
                    if start_idx == -1:
                        break

                    xml_payload = buffer[start_idx:end_idx]
                    buffer = buffer[end_idx:]

                    channel_id = extract_channel_id(xml_payload)
                    send_discord_alert(channel_id)

    except requests.exceptions.RequestException as e:
        print(f"[!] Stream connection error: {e}", flush=True)

    return connected


def listen_to_nvr_stream():
    if not all([NVR_IP, NVR_USER, NVR_PASS]):
        print("[!] Missing NVR_IP / NVR_USER / NVR_PASS - nothing to connect to. Exiting.", flush=True)
        sys.exit(1)

    backoff = INITIAL_BACKOFF
    while not _shutdown:
        connected = _stream_once()
        if _shutdown:
            break

        backoff = INITIAL_BACKOFF if connected else min(backoff * 2, MAX_BACKOFF)
        print(f"[*] Reconnecting in {backoff}s...", flush=True)
        time.sleep(backoff)

    print("[*] Relay shutting down.", flush=True)


if __name__ == "__main__":
    listen_to_nvr_stream()
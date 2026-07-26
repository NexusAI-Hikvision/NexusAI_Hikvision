import os
import requests
from requests.auth import HTTPDigestAuth
from dotenv import load_dotenv

# 1. Load environment variables from .env file
load_dotenv()

# 2. Fetch credentials and endpoints from environment
CAM_IP = os.getenv("CAM_IP")
CAM_PORT = int(os.getenv("CAM_PORT", 80))
CAM_USER = os.getenv("CAM_USER")
CAM_PASS = os.getenv("CAM_PASS")

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

# Construct the Hikvision ISAPI Alert Stream URL
ISAPI_URL = f"http://{CAM_IP}:{CAM_PORT}/ISAPI/Event/notification/alertStream"


def send_discord_alert(title, description, color=16711680):
    """
    Dispatches a structured alert card to the Discord Webhook channel.
    """
    if not DISCORD_WEBHOOK_URL:
        print("[!] Error: DISCORD_WEBHOOK_URL is not set in .env file.")
        return

    payload = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "footer": {"text": "Nexus AI Security System"},
            }
        ]
    }

    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        print("[+] Discord notification sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"[!] Failed to send Discord alert: {e}")


def listen_to_alert_stream():
    """
    Establishes a persistent HTTP Digest Auth connection to the camera's
    ISAPI event stream and processes incoming event payloads.
    """
    if not all([CAM_IP, CAM_USER, CAM_PASS]):
        print("[!] Missing required camera credentials in .env file.")
        return

    print(f"[*] Connecting to Hikvision Alert Stream at {ISAPI_URL}...")

    auth = HTTPDigestAuth(CAM_USER, CAM_PASS)

    try:
        # stream=True opens a long-polling/persistent connection
        with requests.get(ISAPI_URL, auth=auth, stream=True, timeout=30) as response:
            if response.status_code == 200:
                print("[+] Successfully connected to Hikvision Event Stream.")
                
                # Listen continuously to boundary chunks pushed by the camera
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode("utf-8", errors="ignore")

                        # Basic detection check (adjust keywords based on VCA XML output)
                        if "<eventType>" in decoded_line or "event" in decoded_line.lower():
                            print(f"[!] Event Triggered: {decoded_line}")
                            
                            send_discord_alert(
                                title="🚨 Threat Alert Triggered",
                                description=f"**Camera IP:** {CAM_IP}\n**Raw Payload:** {decoded_line}",
                                color=16711680  # Red
                            )
            elif response.status_code == 401:
                print("[!] Authentication Failed: Check CAM_USER and CAM_PASS in .env.")
            else:
                print(f"[!] Stream connection failed with status code: {response.status_code}")

    except requests.exceptions.ConnectionError:
        print(f"[!] Connection Error: Could not reach camera at {CAM_IP}:{CAM_PORT}.")
    except requests.exceptions.Timeout:
        print("[!] Connection Timeout: Camera did not respond in time.")
    except Exception as e:
        print(f"[!] Unexpected error: {e}")


if __name__ == "__main__":
    listen_to_alert_stream()

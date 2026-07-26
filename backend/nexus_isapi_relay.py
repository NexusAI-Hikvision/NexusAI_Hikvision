import json
import requests
from requests.auth import HTTPDigestAuth
import time

# ==========================================
# 1. CONFIGURATION
# ==========================================
# Update these details with your camera's IP 
CAM_IP = "192.168.1.64"  
CAM_PORT = "80"
CAM_USER = "admin"
CAM_PASS = "Password123"  # Camera admin password

# Replace this string with Discord Webhook URL
DISCORD_WEBHOOK_URL = ""

# Hikvision ISAPI Alert Stream Endpoint
ISAPI_URL = f"http://{CAM_IP}:{CAM_PORT}/ISAPI/Event/notification/alertStream"

# ==========================================
# 2. DISCORD RELAY FUNCTION
# ==========================================
def send_discord_alert(event_type, details):
    """Formats and sends threat event payloads to your Discord channel."""
    payload = {
        "username": "NexusAI Threat Sentinel",
        "embeds": [
            {
                "title": "🚨 HIGH PRIORITY THREAT DETECTED",
                "description": f"**Source:** Hikvision Embedded VCA (ISAPI)\n**Event Type:** {event_type}",
                "color": 15158332, # Red border
                "fields": [
                    {"name": "Details / Target Info", "value": str(details), "inline": False},
                    {"name": "Timestamp", "value": time.strftime("%Y-%m-%d %H:%M:%S"), "inline": True}
                ],
                "footer": {"text": "NexusAI Management & Billing Engine"}
            }
        ]
    }
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=5)
        if response.status_code in [200, 204]:
            print("[DISCORD] Alert successfully delivered to #threat-alerts")
        else:
            print(f"[DISCORD WARNING] Webhook returned status: {response.status_code}")
    except Exception as e:
        print(f"[DISCORD ERROR] Could not reach webhook: {e}")

# ==========================================
# 3. ISAPI STREAM LISTENER
# ==========================================
def listen_to_isapi_stream():
    """Connects to the persistent HTTP stream and listens for real-time camera alerts."""
    print(f"[START] Connecting to Hikvision ISAPI Alert Stream: {ISAPI_URL}...")
    
    # Hikvision requires Digest Authentication
    auth = HTTPDigestAuth(CAM_USER, CAM_PASS)
    headers = {"Accept": "application/json, application/xml"}

    try:
        # stream=True holds the HTTP connection open indefinitely
        with requests.get(ISAPI_URL, auth=auth, headers=headers, stream=True, timeout=60) as response:
            if response.status_code == 401:
                print("[AUTH ERROR] Invalid camera credentials (username or password).")
                return
            elif response.status_code != 200:
                print(f"[HTTP ERROR] Failed to connect. Status code: {response.status_code}")
                return

            print("[SUCCESS] Persistent connection established. Listening for events...")
            buffer = ""

            # Read chunks continuously as the camera sends them
            for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
                if chunk:
                    buffer += chunk
                    
                    # Locate and extract JSON payloads inside multipart boundaries
                    if "{" in buffer and "}" in buffer:
                        start = buffer.find("{")
                        end = buffer.rfind("}") + 1
                        json_str = buffer[start:end]
                        buffer = buffer[end:]

                        try:
                            data = json.loads(json_str)
                            
                            # Extract event details from Hikvision JSON schema
                            event_type = data.get("eventType", "VCA Threat Detected")
                            event_description = data.get("eventDescription", "Smart VCA trigger event")
                            
                            print(f"\n[CAMERA ALERT] {event_type} - {event_description}")
                            
                            # Relay directly to Discord
                            send_discord_alert(event_type, event_description)

                        except json.JSONDecodeError:
                            continue

    except requests.exceptions.RequestException as e:
        print(f"[STREAM ERROR] Network connection lost or timed out: {e}")

if __name__ == "__main__":
    listen_to_isapi_stream()
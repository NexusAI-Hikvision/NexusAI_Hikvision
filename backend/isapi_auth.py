"""
isapi_auth.py

Reuses the authentication mechanism from nexus_isapi_relay.py for the
"Connect Camera" onboarding flow, WITHOUT modifying that file.

Why this exists instead of importing listen_to_isapi_stream() directly:
  1. That function never returns on a successful connection — it holds the
     stream open and loops forever reading events. Calling it from a request
     handler would hang the HTTP request indefinitely on success.
  2. It reads CAM_IP / CAM_PORT / CAM_USER / CAM_PASS from hardcoded
     module-level globals, not function parameters, so it can't be pointed
     at a different camera per-request without mutating shared state.
  3. On success it also forwards events to Discord — a side effect that has
     nothing to do with "can we authenticate to this camera".

What this module does instead:
  Same endpoint (ISAPI alertStream), same auth scheme (HTTPDigestAuth),
  same status-code interpretation (401 = bad credentials, 200 = success)
  as nexus_isapi_relay.listen_to_isapi_stream(). The only difference is
  that we open the connection just long enough to read the response
  status line, then close it — we never enter the chunk-reading loop.

NOTE (matches the "Possible Future Refactor" section of the task doc):
Once the relay is split into test_camera_connection() /
listen_to_isapi_stream(), this file can be deleted and the endpoint can
call the real shared function directly.
"""

import requests
from requests.auth import HTTPDigestAuth


def _build_isapi_url(ip: str, port: int) -> str:
    return f"http://{ip}:{port}/ISAPI/Event/notification/alertStream"


def verify_camera_auth(ip: str, port: int, username: str, password: str, timeout: int = 8) -> dict:
    """
    Attempts a digest-authenticated connection to the camera's ISAPI
    alert stream endpoint, mirroring nexus_isapi_relay.py's auth check.

    Returns a dict:
      {"success": True}
      {"success": False, "reason": "unauthorized" | "http_<code>" | "network_error", "detail": ...}
    """
    url = _build_isapi_url(ip, port)
    auth = HTTPDigestAuth(username, password)
    headers = {"Accept": "application/json, application/xml"}

    try:
        # stream=True + context manager means the connection is closed as
        # soon as we leave the `with` block — we never call iter_content(),
        # so we never enter the infinite read loop that
        # listen_to_isapi_stream() uses.
        with requests.get(url, auth=auth, headers=headers, stream=True, timeout=timeout) as response:
            if response.status_code == 401:
                return {"success": False, "reason": "unauthorized"}
            if response.status_code != 200:
                return {"success": False, "reason": f"http_{response.status_code}"}
            return {"success": True}
    except requests.exceptions.RequestException as e:
        return {"success": False, "reason": "network_error", "detail": str(e)}
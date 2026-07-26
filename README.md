# NexusAI — Hikvision ISAPI Threat Sentinel

![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)
![Integration](https://img.shields.io/badge/Integration-Hikvision%20ISAPI-red.svg)
![Alerting](https://img.shields.io/badge/Alerts-Discord%20Webhook-7289DA.svg)

NexusAI is a lightweight, zero-GPU event management and alert relay engine built for automated security monitoring and threat dispatch. By integrating directly with Hikvision embedded VCA (Video Content Analysis) hardware via the **ISAPI Alert Stream**, NexusAI offloads heavy AI detection processing to edge camera hardware and manages real-time alert dispatching, dashboard feeds, and multi-channel notifications.

---

## 🌟 Key Features

* **Zero Local Hardware Bottleneck:** Eliminates the need for high-end local GPUs or heavy PyTorch/YOLO inference loops by consuming edge camera analytics directly.
* **Real-time ISAPI Event Streaming:** Connects to persistent HTTP chunked multipart streams (`/ISAPI/Event/notification/alertStream`) to receive immediate VCA threat triggers.
* **Automated Discord Dispatch:** Instantly parses incoming XML/JSON event payloads and dispatches formatted, high-priority threat cards to Discord `#threat-alerts`.
* **Digest Authentication Handling:** Securely handles HTTP Digest handshake constraints required by Hikvision camera firmware.
* **Extensible Alert Payload Architecture:** Built to easily route events to central management dashboards and custom client billing modules.

---

## 🏗️ System Architecture

```text
┌─────────────────────────┐    ISAPI Alert Stream     ┌────────────────────────┐    HTTP POST    ┌────────────────────────┐
│  Hikvision VCA Camera   │ ────────────────────────> │  NexusAI Relay Engine  │ ──────────────> │    Discord Webhook     │
│ (Embedded Detection AI) │   Chunked JSON / XML      │ (nexus_isapi_relay.py) │                 │  & Admin Dashboard     │
└─────────────────────────┘                           └────────────────────────┘                 └────────────────────────┘

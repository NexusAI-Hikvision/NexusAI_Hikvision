const form = document.getElementById("connect-camera-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("connect-status");
const clientNameEl = document.getElementById("client-name");

const API_BASE = "";

const token = new URLSearchParams(window.location.search).get("token");

if (!token) {
    statusEl.classList.add("visible", "error");
    statusEl.textContent = "This link is missing its access token. Please rescan your QR code.";
    submitBtn.disabled = true;
}

// Prefill the client's name/site so the technician can confirm they're
// connecting the right site's cameras before entering NVR credentials.
async function loadClient() {
    if (!token) return;
    try {
        const res = await fetch(`${API_BASE}/client/${encodeURIComponent(token)}`);
        if (!res.ok) {
            throw new Error(`Server responded with ${res.status}`);
        }
        const client = await res.json();
        if (clientNameEl) {
            clientNameEl.textContent = `Connecting cameras for ${client.name} (${client.location})`;
        }
    } catch (err) {
        if (clientNameEl) {
            clientNameEl.textContent = "";
        }
        statusEl.classList.add("visible", "error");
        statusEl.textContent = "Couldn't verify this link. Please rescan your QR code.";
        submitBtn.disabled = true;
        console.error("client lookup failed:", err);
    }
}

loadClient();

form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!token) return;

    statusEl.className = "form-status";
    statusEl.textContent = "";

    submitBtn.disabled = true;
    submitBtn.textContent = "Connecting...";

    const payload = {
        token: token,
        ip: document.getElementById("camera_ip").value.trim(),
        port: parseInt(document.getElementById("camera_port").value, 10),
        username: document.getElementById("username").value,
        password: document.getElementById("password").value
    };

    try {
        const response = await fetch(`${API_BASE}/connect-nvr`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        statusEl.classList.add("visible");

        if (result.status === "success") {
            statusEl.classList.remove("error");
            statusEl.textContent = result.message || "Connected! Redirecting to dashboard...";
            submitBtn.textContent = "Redirecting...";
            setTimeout(() => {
                window.location.href = `dashboard.html?token=${encodeURIComponent(token)}`;
            }, 1200);
            return; // skip the finally re-enable below
        }

        statusEl.classList.add("error");
        statusEl.textContent = result.message || "Something went wrong. Please try again.";
        submitBtn.disabled = false;
        submitBtn.textContent = "Connect Camera";
    } catch (err) {
        statusEl.classList.add("visible", "error");
        statusEl.textContent = "Could not reach the server. Is the backend running?";
        console.error("connect-nvr failed:", err);
        submitBtn.disabled = false;
        submitBtn.textContent = "Connect Camera";
    }
});
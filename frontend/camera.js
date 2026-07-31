const form = document.getElementById("connect-camera-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("connect-status");
<<<<<<< HEAD
const clientNameEl = document.getElementById("client-name");

const API_BASE = "http://127.0.0.1:8000";

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

=======

const API_BASE = "http://127.0.0.1:8000";

form.addEventListener("submit", async (e) => {
    e.preventDefault();

>>>>>>> 24a93dd31e7b1e372f00832431f03ca288ac3ce2
    statusEl.className = "form-status";
    statusEl.textContent = "";

    submitBtn.disabled = true;
    submitBtn.textContent = "Connecting...";

    const payload = {
<<<<<<< HEAD
        token: token,
=======
>>>>>>> 24a93dd31e7b1e372f00832431f03ca288ac3ce2
        ip: document.getElementById("camera_ip").value.trim(),
        port: parseInt(document.getElementById("camera_port").value, 10),
        username: document.getElementById("username").value,
        password: document.getElementById("password").value
    };

    try {
<<<<<<< HEAD
        const response = await fetch(`${API_BASE}/connect-nvr`, {
=======
        const response = await fetch(`${API_BASE}/connect-camera`, {
>>>>>>> 24a93dd31e7b1e372f00832431f03ca288ac3ce2
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const result = await response.json();

        statusEl.classList.add("visible");
        if (result.status === "success") {
            statusEl.classList.remove("error");
        } else {
            statusEl.classList.add("error");
        }
<<<<<<< HEAD
        statusEl.textContent = result.message || "Something went wrong. Please try again.";
    } catch (err) {
        statusEl.classList.add("visible", "error");
        statusEl.textContent = "Could not reach the server. Is the backend running?";
        console.error("connect-nvr failed:", err);
=======
        statusEl.textContent = result.message;
    } catch (err) {
        statusEl.classList.add("visible", "error");
        statusEl.textContent = "Could not reach the server. Is the backend running?";
        console.error("connect-camera failed:", err);
>>>>>>> 24a93dd31e7b1e372f00832431f03ca288ac3ce2
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Connect Camera";
    }
});
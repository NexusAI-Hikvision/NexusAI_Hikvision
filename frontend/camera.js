const form = document.getElementById("connect-camera-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("connect-status");

const API_BASE = "http://127.0.0.1:8000";

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    statusEl.className = "form-status";
    statusEl.textContent = "";

    submitBtn.disabled = true;
    submitBtn.textContent = "Connecting...";

    const payload = {
        ip: document.getElementById("camera_ip").value.trim(),
        port: parseInt(document.getElementById("camera_port").value, 10),
        username: document.getElementById("username").value,
        password: document.getElementById("password").value
    };

    try {
        const response = await fetch(`${API_BASE}/connect-camera`, {
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
        statusEl.textContent = result.message;
    } catch (err) {
        statusEl.classList.add("visible", "error");
        statusEl.textContent = "Could not reach the server. Is the backend running?";
        console.error("connect-camera failed:", err);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Connect Camera";
    }
});
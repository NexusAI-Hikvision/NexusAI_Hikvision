const form = document.getElementById("connect-camera-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("connect-status");
const clientNameEl = document.getElementById("client-name");

const nvrRadio = document.getElementById("conn-nvr");
const individualRadio = document.getElementById("conn-individual");
const nvrFields = document.getElementById("nvr-fields");
const individualFields = document.getElementById("individual-fields");
const cameraList = document.getElementById("camera-list");
const addCameraBtn = document.getElementById("add-camera-btn");

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

// ---------------------------------------------------------------------------
// Connection type toggle — NVR is the default/primary path (Benjamin's
// clients). Individual cameras is the secondary path for advanced users
// with no recorder box.
// ---------------------------------------------------------------------------

let cameraRowCount = 0;

function setRequiredNvrFields(required) {
    ["camera_ip", "camera_port", "username", "password"].forEach((id) => {
        document.getElementById(id).required = required;
    });
}

function updateSubmitLabel() {
    submitBtn.textContent = nvrRadio.checked ? "Connect Camera" : "Connect Cameras";
}

function toggleConnType() {
    const isIndividual = individualRadio.checked;
    nvrFields.hidden = isIndividual;
    individualFields.hidden = !isIndividual;
    setRequiredNvrFields(!isIndividual);
    updateSubmitLabel();
    if (isIndividual && cameraList.children.length === 0) {
        addCameraRow();
    }
}

nvrRadio.addEventListener("change", toggleConnType);
individualRadio.addEventListener("change", toggleConnType);
updateSubmitLabel();

function addCameraRow() {
    cameraRowCount += 1;
    const id = cameraRowCount;
    const row = document.createElement("div");
    row.className = "camera-row";
    row.dataset.rowId = id;
    row.innerHTML = `
        <div class="camera-row-head">
            <span>Camera ${id}</span>
            <button type="button" class="camera-remove-btn" data-remove="${id}">Remove</button>
        </div>
        <div class="field">
            <label>IP address</label>
            <input type="text" name="cam_ip_${id}" placeholder="192.168.1.${100 + id}" required>
        </div>
        <div class="field">
            <label>Username</label>
            <input type="text" name="cam_user_${id}" placeholder="admin" required>
        </div>
        <div class="field">
            <label>Password</label>
            <input type="password" name="cam_pass_${id}" placeholder="••••••••" required>
        </div>
    `;
    cameraList.appendChild(row);
    updateRemoveButtons();
}

function updateRemoveButtons() {
    const rows = cameraList.querySelectorAll(".camera-row");
    rows.forEach((row) => {
        const btn = row.querySelector(".camera-remove-btn");
        btn.style.visibility = rows.length > 1 ? "visible" : "hidden";
    });
}

addCameraBtn.addEventListener("click", addCameraRow);

cameraList.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-remove]");
    if (!btn) return;
    const row = cameraList.querySelector(`[data-row-id="${btn.dataset.remove}"]`);
    if (row) row.remove();
    updateRemoveButtons();
});

// ---------------------------------------------------------------------------
// Submit
// ---------------------------------------------------------------------------

form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!token) return;

    statusEl.className = "form-status";
    statusEl.textContent = "";

    if (nvrRadio.checked) {
        await submitNvr();
    } else {
        await submitIndividualCameras();
    }
});

// NVR path — unchanged, hits the real /connect-nvr endpoint.
async function submitNvr() {
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
}

// Individual camera path — secondary/advanced flow. No backend endpoint or
// `cameras` schema for standalone cameras exists yet, so this is mocked
// client-side. Swap the body of this function for a real fetch to
// `/connect-cameras` (or similar) once that's built.
async function submitIndividualCameras() {
    submitBtn.disabled = true;
    submitBtn.textContent = "Connecting...";

    const rows = cameraList.querySelectorAll(".camera-row");
    const cameras = Array.from(rows).map((row) => {
        const id = row.dataset.rowId;
        return {
            ip: row.querySelector(`[name="cam_ip_${id}"]`).value.trim(),
            username: row.querySelector(`[name="cam_user_${id}"]`).value.trim(),
            password: row.querySelector(`[name="cam_pass_${id}"]`).value
        };
    });

    // --- MOCK — replace with a real fetch once the backend/schema exist ---
    await new Promise((resolve) => setTimeout(resolve, 900));
    const result = {
        status: "success",
        message: `Connected ${cameras.length} camera(s) successfully!`
    };
    // ------------------------------------------------------------------

    statusEl.classList.add("visible");

    if (result.status === "success") {
        statusEl.classList.remove("error");
        statusEl.textContent = result.message;
        submitBtn.textContent = "Redirecting...";
        setTimeout(() => {
            window.location.href = `dashboard.html?token=${encodeURIComponent(token)}`;
        }, 1200);
        return;
    }

    statusEl.classList.add("error");
    statusEl.textContent = result.message || "Something went wrong. Please try again.";
    submitBtn.disabled = false;
    submitBtn.textContent = "Connect Cameras";
}
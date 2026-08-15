const API_BASE = ""; // same-origin, matches your existing pattern

const params = new URLSearchParams(window.location.search);
const token = params.get("token");

let selectedCameraId = null;

if (!token) {
  document.body.innerHTML = '<p style="padding:40px;font-family:monospace;">No token in URL. Expected ?token=xxx</p>';
  throw new Error("Missing token");
}

function timeAgo(isoString) {
  if (!isoString) return "No alerts yet";
  const diffMs = Date.now() - new Date(isoString + "Z").getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "Just now";
  if (mins < 60) return `Last alert: ${mins} min${mins === 1 ? "" : "s"} ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `Last alert: ${hrs}h ago`;
  return `Last alert: ${Math.floor(hrs / 24)}d ago`;
}

async function loadDashboard() {
  const res = await fetch(`${API_BASE}/api/dashboard/${token}`);
  if (!res.ok) {
    document.body.innerHTML = '<p style="padding:40px;font-family:monospace;">Client not found. Check your token.</p>';
    return;
  }
  const data = await res.json();

  document.getElementById("site-name").textContent = data.site_name;
  document.getElementById("camera-count").textContent = `${data.camera_count} camera${data.camera_count === 1 ? "" : "s"}`;
  document.getElementById("alert-count").textContent = `${data.alerts_today} alerts today`;

  const badge = document.getElementById("status-badge");
  badge.textContent = data.status;
  badge.className = "badge " + (data.status === "Active" ? "active" : "offline");

  const grid = document.getElementById("camera-grid");
  grid.innerHTML = "";

  if (data.cameras.length === 0) {
    grid.innerHTML = '<div class="empty-state">No cameras linked yet. Once the NVR is connected, cameras will show up here.</div>';
  } else {
    data.cameras.forEach((cam) => {
      const card = document.createElement("div");
      card.className = "camera-card" + (cam.id === selectedCameraId ? " selected" : "");
      card.innerHTML = `
        <div><span class="dot ${cam.status}"></span><strong>${cam.name}</strong></div>
        <div class="last-alert">${timeAgo(cam.last_alert_at)}</div>
      `;
      card.onclick = () => {
        selectedCameraId = cam.id;
        loadAlerts(cam.id, cam.name);
        loadDashboard(); // re-render to highlight selection
      };
      grid.appendChild(card);
    });
  }

  if (selectedCameraId === null) {
    loadAlerts(null, null);
  }
}

async function loadAlerts(cameraId, cameraName) {
  const title = document.getElementById("alert-feed-title");
  const limit = cameraId ? 5 : 50;
  title.textContent = cameraId ? `Alerts — ${cameraName}` : "Alert Feed";

  let url = `${API_BASE}/api/alerts/${token}?limit=${limit}`;
  if (cameraId) url += `&camera_id=${cameraId}`;

  const res = await fetch(url);
  const alerts = await res.json();

  const feed = document.getElementById("alert-feed");
  feed.innerHTML = "";

  if (alerts.length === 0) {
    feed.innerHTML = '<div class="empty-state">No alerts yet.</div>';
    return;
  }

  alerts.forEach((a) => {
    const row = document.createElement("div");
    row.className = "alert-row";
    const time = new Date(a.created_at + "Z").toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    row.innerHTML = `
      <span>${time}</span>
      <span>${a.camera_name}</span>
      <span class="alert-type ${a.type}">${a.type}</span>
      <span>${a.confidence != null ? a.confidence + "%" : "—"}</span>
    `;
    feed.appendChild(row);
  });
}

document.getElementById("refresh-btn").onclick = () => {
  loadDashboard();
  loadAlerts(selectedCameraId, null);
};

document.getElementById("test-alert-btn").onclick = async () => {
  const btn = document.getElementById("test-alert-btn");
  btn.disabled = true;
  btn.textContent = "Firing…";
  try {
    await fetch(`${API_BASE}/api/test-alert/${token}`, { method: "POST" });
    await loadDashboard();
    await loadAlerts(selectedCameraId, null);
  } catch (e) {
    alert("Test alert failed — check console.");
    console.error(e);
  } finally {
    btn.disabled = false;
    btn.textContent = "Test Alert";
  }
};

document.getElementById("report-btn").onclick = () => {
  window.location.href = `${API_BASE}/api/report/${token}`;
};

loadDashboard();
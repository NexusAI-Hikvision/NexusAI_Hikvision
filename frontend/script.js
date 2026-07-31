const form = document.getElementById("onboarding-form");
const submitBtn = document.getElementById("submit-btn");
const statusEl = document.getElementById("form-status");
const resultEl = document.getElementById("qr-result");
const qrImg = document.getElementById("qr-output");
const qrUrl = document.getElementById("qr-url");



const API_BASE = "http://127.0.0.1:8000";

form.addEventListener("submit", async (e) => {
    e.preventDefault();

    statusEl.className = "form-status";
    statusEl.textContent = "";
    resultEl.classList.remove("visible");

    submitBtn.disabled = true;
    submitBtn.textContent = "Generating...";

    const payload = {
        name: document.getElementById("name").value,
        location: document.getElementById("location").value,
        contact_person: document.getElementById("contact_person").value,
        contact_phone: document.getElementById("contact_phone").value,
        camera_count: parseInt(document.getElementById("camera_count").value, 10)
    };

    try {
        const response = await fetch(`${API_BASE}/generate-qr`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

<<<<<<< HEAD
        const result = await response.json();

        if (!response.ok) {
            const detail = typeof result.detail === "string" ? result.detail : `Server responded with ${response.status}`;
            throw new Error(detail);
        }

=======
        if (!response.ok) {
            throw new Error(`Server responded with ${response.status}`);
        }

        const result = await response.json();

>>>>>>> 24a93dd31e7b1e372f00832431f03ca288ac3ce2
        qrImg.src = "data:image/png;base64," + result.qr_image_base64;
        qrUrl.textContent = result.url;
        resultEl.classList.add("visible");
    } catch (err) {
        statusEl.classList.add("visible", "error");
<<<<<<< HEAD
        statusEl.textContent = err.message || "Something went wrong generating your QR code. Please try again.";
=======
        statusEl.textContent = "Something went wrong generating your QR code. Please try again.";
>>>>>>> 24a93dd31e7b1e372f00832431f03ca288ac3ce2
        console.error("generate-qr failed:", err);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Generate My QR Code";
    }
});
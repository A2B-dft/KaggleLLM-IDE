// src/lib/api.js
// Two clients:
//   backendApi  — talks to YOUR FastAPI server (session management)
//   tunnelApi   — talks DIRECTLY to the user's Kaggle kernel once ready

const BACKEND = import.meta.env.VITE_BACKEND_URL || "http://localhost:8000";

export async function verifyCredentials({ kaggleUsername, kaggleApiKey }) {
  const res = await fetch(`${BACKEND}/auth/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kaggle_username: kaggleUsername,
      kaggle_api_key:  kaggleApiKey,
    }),
  });
  if (!res.ok) throw new Error("Verification request failed");
  return res.json(); // { valid, gpu_enabled, username, error? }
}

// ── Backend: session lifecycle ───────────────────────────────────────────

export async function startSession({ kaggleUsername, kaggleApiKey, ngrokToken, model }) {
  const res = await fetch(`${BACKEND}/session/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kaggle_username: kaggleUsername,
      kaggle_api_key:  kaggleApiKey,
      ngrok_token:     ngrokToken,
      model,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to start session");
  }
  return res.json(); // { session_id, status }
}

export async function getSessionStatus(sessionId) {
  const res = await fetch(`${BACKEND}/session/${sessionId}/status`);
  if (!res.ok) throw new Error("Status check failed");
  return res.json(); // { session_id, status, tunnel_url, error }
}

export async function stopSession(sessionId) {
  const res = await fetch(`${BACKEND}/session/${sessionId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Stop session failed");
  return res.json();
}

// ── Tunnel: talk directly to Kaggle kernel ───────────────────────────────

export async function generateCompletion(tunnelUrl, { model, prompt, system = "", temperature = 0.2 }) {
  const res = await fetch(`${tunnelUrl}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ model, prompt, system, temperature, stream: false }),
  });
  if (!res.ok) throw new Error("Inference request failed");
  const data = await res.json();
  return data.response ?? data.choices?.[0]?.text ?? "";
}

export async function listModels(tunnelUrl) {
  const res = await fetch(`${tunnelUrl}/models`);
  if (!res.ok) throw new Error("Could not fetch models");
  return res.json();
}
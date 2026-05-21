"""
auth.py
-------
Validates Kaggle credentials and checks GPU access before any kernel
is launched. Called by the frontend at the start of every session.

Two checks in order:
  1. verify_credentials()  — confirms the API key is valid
  2. check_gpu_access()    — confirms phone verification is done
                             (required by Kaggle to use GPU kernels)

Exposes:
  POST /auth/verify   → { valid, gpu_enabled, username, error? }
"""

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

KAGGLE_API_BASE  = "https://www.kaggle.com/api/v1"
PHONE_VERIFY_URL = "https://www.kaggle.com/settings/phone-verification"


# ── Request / Response models ────────────────────────────────────────────

class VerifyRequest(BaseModel):
    kaggle_username: str
    kaggle_api_key:  str


class VerifyResponse(BaseModel):
    valid:       bool
    gpu_enabled: bool
    username:    str | None = None
    error:       str | None = None


# ── Core checks ──────────────────────────────────────────────────────────

async def verify_credentials(username: str, api_key: str) -> tuple[bool, str | None]:
    """
    Hits GET /api/v1/kernels (cheapest authenticated endpoint).
    Returns (True, None) on success or (False, error_message) on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(
                f"{KAGGLE_API_BASE}/kernels",
                auth=(username, api_key),
                params={"pageSize": 1},
            )

        if r.status_code == 200:
            return True, None

        if r.status_code == 401:
            return False, (
                "Invalid credentials. Check your Kaggle username and API key at "
                "kaggle.com → Settings → API."
            )

        return False, f"Kaggle returned HTTP {r.status_code}. Try again shortly."

    except httpx.TimeoutException:
        return False, "Request to Kaggle timed out. Check your internet connection."
    except httpx.RequestError as e:
        return False, f"Network error reaching Kaggle: {e}"


async def check_gpu_access(username: str, api_key: str) -> tuple[bool, str | None]:
    """
    Pushes a minimal no-op kernel and inspects the response.

    Kaggle returns a specific error payload when the account hasn't
    completed phone verification — we parse that and surface a clear
    message with the verification URL.

    Returns (True, None) if GPU access is confirmed,
            (False, error_message) otherwise.
    """
    probe_payload = {
        "metadata": {
            "id":                 f"{username}/gpu-access-probe",
            "title":              "GPU Access Probe",
            "code_file":          "probe.py",
            "language":           "python",
            "kernel_type":        "script",
            "is_private":         True,
            "enable_gpu":         True,     # ← this is what triggers the check
            "enable_internet":    False,
            "dataset_sources":    [],
            "competition_sources":[],
            "kernel_sources":     [],
        },
        "blob": {"source": "print('probe')"},
    }

    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                f"{KAGGLE_API_BASE}/kernels/push",
                auth=(username, api_key),
                json=probe_payload,
            )

        # 200 / 201 → push accepted → GPU access is enabled
        if r.status_code in (200, 201):
            return True, None

        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        message: str = body.get("message", "") or body.get("error", "")

        # Kaggle's phone-verification gate shows up as 403 with a specific message
        if r.status_code == 403 or "phone" in message.lower() or "verify" in message.lower():
            return False, (
                "Your Kaggle account needs phone verification before GPU kernels "
                f"can be used. Complete it here: {PHONE_VERIFY_URL}"
            )

        # Any other error — surface it verbatim so the user can act on it
        return False, (
            message or f"GPU access check failed (HTTP {r.status_code}). "
            "Make sure your Kaggle account has accepted the rules for GPU usage."
        )

    except httpx.TimeoutException:
        return False, "GPU access check timed out. Try again."
    except httpx.RequestError as e:
        return False, f"Network error during GPU access check: {e}"


# ── Route ────────────────────────────────────────────────────────────────

@router.post("/verify", response_model=VerifyResponse)
async def verify(req: VerifyRequest):
    """
    Frontend calls this before starting a session.

    Flow:
      1. Validate credentials — if invalid, return immediately.
      2. Check GPU access    — if not enabled, return the verification URL.
      3. Return { valid: true, gpu_enabled: true } → frontend proceeds to launch.
    """
    username = req.kaggle_username.lower().strip()
    api_key  = req.kaggle_api_key.strip()

    # ── Step 1: credentials ──────────────────────────────────────────────
    creds_ok, creds_err = await verify_credentials(username, api_key)
    if not creds_ok:
        return VerifyResponse(valid=False, gpu_enabled=False, error=creds_err)

    # ── Step 2: GPU access ───────────────────────────────────────────────
    gpu_ok, gpu_err = await check_gpu_access(username, api_key)
    if not gpu_ok:
        return VerifyResponse(
            valid=True,          # credentials are fine
            gpu_enabled=False,
            username=username,
            error=gpu_err,
        )

    return VerifyResponse(valid=True, gpu_enabled=True, username=username)
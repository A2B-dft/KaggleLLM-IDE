"""
main.py
-------
FastAPI backend — the thin orchestration layer between the frontend
and each user's Kaggle kernel.

What this server does NOT do:
  - It never proxies LLM inference traffic. Once the tunnel URL is known,
    the frontend talks directly to the user's Kaggle kernel.
  - It never stores Kaggle credentials beyond the lifetime of the process.

Endpoints:
  POST   /session/start          — push kernel, begin polling
  GET    /session/{id}/status    — poll: 'launching' | 'ready' | 'error'
  DELETE /session/{id}           — stop kernel, clear session
  GET    /health                 — liveness check
"""

import asyncio
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from kaggle_runner import KaggleRunner
from auth import router as auth_router

# ── App setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Kaggle GPU IDE — Backend",
    version="0.1.0",
    description="Orchestrates per-user Ollama kernels on Kaggle free GPU.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten to your frontend URL before going public
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)

# ── In-memory session store ─────────────────────────────────────────────────
# For a single-user / small-team setup this is fine.
# Replace with Redis if you scale beyond a handful of concurrent users.

SessionStatus = Literal["launching", "ready", "error", "stopped"]

sessions: dict[str, dict] = {}
# shape: { session_id: { runner, status, tunnel_url, error, kaggle_username } }


# ── Request / Response models ───────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    kaggle_username: str = Field(..., example="jdoe")
    kaggle_api_key:  str = Field(..., example="abc123...")
    ngrok_token:     str = Field(..., example="2abc...")
    model:           str = Field("qwen2.5-coder:7b", example="qwen2.5-coder:7b")


class StartSessionResponse(BaseModel):
    session_id: str
    status:     SessionStatus


class StatusResponse(BaseModel):
    session_id:  str
    status:      SessionStatus
    tunnel_url:  str | None = None
    error:       str | None = None


# ── Background task: wait for tunnel URL ────────────────────────────────────

async def _background_poll(session_id: str, runner: KaggleRunner):
    """Runs in the background after /session/start returns."""
    try:
        url = await runner.poll_for_tunnel_url()
        sessions[session_id]["tunnel_url"] = url
        sessions[session_id]["status"]     = "ready"
    except TimeoutError as e:
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"]  = str(e)
    except RuntimeError as e:
        sessions[session_id]["status"] = "error"
        sessions[session_id]["error"]  = str(e)


# ── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "active_sessions": len(sessions)}


@app.post("/session/start", response_model=StartSessionResponse, status_code=202)
async def start_session(req: StartSessionRequest):
    """
    Push the Kaggle GPU kernel for this user and begin polling for the
    tunnel URL. Returns immediately with status='launching'.

    The frontend should then poll GET /session/{id}/status until
    status becomes 'ready' (or 'error').
    """
    # One active session per Kaggle username
    session_id = req.kaggle_username.lower()

    if session_id in sessions and sessions[session_id]["status"] == "ready":
        # Kernel already running — just return existing session
        return {"session_id": session_id, "status": "ready"}

    runner = KaggleRunner(
        username    = req.kaggle_username,
        api_key     = req.kaggle_api_key,
        ngrok_token = req.ngrok_token,
    )

    # Push kernel (fast — just an API call)
    try:
        await runner.push_kernel(model_name=req.model)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Kaggle push failed: {e}")

    sessions[session_id] = {
        "runner":           runner,
        "status":           "launching",
        "tunnel_url":       None,
        "error":            None,
        "kaggle_username":  req.kaggle_username,
    }

    # Poll for tunnel URL without blocking the response
    asyncio.create_task(_background_poll(session_id, runner))

    return {"session_id": session_id, "status": "launching"}


@app.get("/session/{session_id}/status", response_model=StatusResponse)
async def session_status(session_id: str):
    """
    Returns the current session state.
    When status == 'ready', tunnel_url will be set — the frontend
    should save it and talk directly to the Kaggle kernel from then on.
    """
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {
        "session_id": session_id,
        "status":     session["status"],
        "tunnel_url": session.get("tunnel_url"),
        "error":      session.get("error"),
    }


@app.delete("/session/{session_id}")
async def stop_session(session_id: str):
    """Stop the Kaggle kernel and clear the session."""
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        await session["runner"].stop_kernel()
    except Exception as e:
        # Log but don't fail — we still want to clear the local session
        print(f"[WARN] stop_kernel error: {e}")

    sessions.pop(session_id, None)
    return {"status": "stopped", "session_id": session_id}
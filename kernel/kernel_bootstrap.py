"""
kernel_bootstrap.py
-------------------
This script runs INSIDE the Kaggle kernel on the user's GPU.
It is pushed programmatically via the Kaggle API by kaggle_runner.py.

Flow:
  1. Install dependencies (fastapi, uvicorn, pyngrok, httpx)
  2. Install Ollama via official install script
  3. Start the Ollama background server
  4. Pull the requested coding model
  5. Start a lightweight FastAPI inference server on port 8000
  6. Open a public ngrok tunnel and print the URL with a special marker
     so the backend can parse it via output polling.
  7. Keep-alive loop (kernel stays up until GPU quota expires or user stops it)
"""

import os
import sys
import time
import subprocess
import threading

# ── Injected by kaggle_runner.py at push time ──────────────────────────────
# These two lines are prepended dynamically; fallbacks here are for local dev.
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")
NGROK_TOKEN  = os.environ.get("NGROK_TOKEN",  "")
API_PORT     = 8000
# ───────────────────────────────────────────────────────────────────────────


# ── Step 1: Install Python dependencies ────────────────────────────────────
def install_dependencies():
    print("[BOOTSTRAP] Installing Python dependencies...")
    pkgs = ["fastapi", "uvicorn[standard]", "pyngrok==7.2.0", "httpx"]
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", "--upgrade"] + pkgs,
        check=True,
    )
    print("[BOOTSTRAP] Python dependencies installed.")


# ── Step 2: Install Ollama ──────────────────────────────────────────────────
def install_ollama():
    print("[BOOTSTRAP] Installing Ollama...")
    subprocess.run(
        "curl -fsSL https://ollama.com/install.sh | sh",
        shell=True,
        check=True,
    )
    print("[BOOTSTRAP] Ollama installed.")


# ── Step 3: Start Ollama server in background ──────────────────────────────
def start_ollama_server() -> subprocess.Popen:
    print("[BOOTSTRAP] Starting Ollama server...")
    proc = subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give Ollama a moment to bind to port 11434
    time.sleep(4)
    print("[BOOTSTRAP] Ollama server is up.")
    return proc


# ── Step 4: Pull the requested model ──────────────────────────────────────
def pull_model(model_name: str):
    print(f"[BOOTSTRAP] Pulling model '{model_name}' — this may take a few minutes...")
    subprocess.run(["ollama", "pull", model_name], check=True)
    print(f"[BOOTSTRAP] Model '{model_name}' is ready.")


# ── Step 5: Write & start FastAPI inference server ─────────────────────────
API_SERVER_CODE = """
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn, asyncio

app = FastAPI(title="Ollama Kaggle Bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_BASE = "http://localhost:11434"

class GenerateRequest(BaseModel):
    model: str
    prompt: str
    system: str = ""
    temperature: float = 0.2
    stream: bool = False

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/models")
async def list_models():
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{OLLAMA_BASE}/api/tags")
        r.raise_for_status()
        return r.json()

@app.post("/generate")
async def generate(req: GenerateRequest):
    payload = {
        "model": req.model,
        "prompt": req.prompt,
        "stream": False,
        "options": {"temperature": req.temperature},
    }
    if req.system:
        payload["system"] = req.system
    async with httpx.AsyncClient(timeout=300) as c:
        try:
            r = await c.post(f"{OLLAMA_BASE}/api/generate", json=payload)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(status_code=502, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
"""

def start_api_server() -> subprocess.Popen:
    server_path = "/tmp/api_server.py"
    with open(server_path, "w") as f:
        f.write(API_SERVER_CODE)
    print("[BOOTSTRAP] Starting FastAPI inference server on port 8000...")
    proc = subprocess.Popen(
        [sys.executable, server_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    print("[BOOTSTRAP] Inference server is up.")
    return proc


# ── Step 6: Open ngrok tunnel & print URL ─────────────────────────────────
def start_ngrok_tunnel(token: str, port: int = API_PORT) -> str:
    from pyngrok import ngrok, conf  # imported here — after pip install

    print("[BOOTSTRAP] Opening ngrok tunnel...")
    conf.get_default().auth_token = token
    tunnel = ngrok.connect(port, "http")
    url: str = tunnel.public_url

    # ⚠️  This exact marker is parsed by kaggle_runner.poll_for_tunnel_url()
    print(f"[TUNNEL_URL]{url}[/TUNNEL_URL]", flush=True)
    print(f"[BOOTSTRAP] Public API URL: {url}")
    return url


# ── Step 7: Keep-alive ─────────────────────────────────────────────────────
def keep_alive():
    print("[BOOTSTRAP] Kernel is live. Staying up until GPU quota runs out.")
    try:
        while True:
            time.sleep(120)
            print("[BOOTSTRAP] ♥ heartbeat — still running", flush=True)
    except KeyboardInterrupt:
        print("[BOOTSTRAP] Shutting down.")


# ── Main ────────────────────────────────────────────────────────────────────
def main():
    install_dependencies()
    install_ollama()
    start_ollama_server()
    pull_model(OLLAMA_MODEL)
    start_api_server()

    if not NGROK_TOKEN:
        print(
            "[BOOTSTRAP] ⚠  NGROK_TOKEN not set — "
            "server is running locally on port 8000 only."
        )
    else:
        start_ngrok_tunnel(NGROK_TOKEN)

    keep_alive()


if __name__ == "__main__":
    main()
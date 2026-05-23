# KaggleLLM-IDE

Run frontier coding models on **your own free Kaggle GPU** — no shared server, no VRAM limits on your laptop.

Each user brings their own Kaggle account. The app spins up a private GPU kernel, installs [Ollama](https://ollama.com), pulls your chosen model, and tunnels the inference endpoint directly to your browser via ngrok. Your prompts never touch anyone else's server.

```
You → Setup form → Kaggle API → Your GPU kernel → ngrok tunnel → Chat UI
```

---

## Why this exists

Most coding LLMs worth running (Qwen2.5-Coder 32B, DeepSeek-Coder-V2) need 16–20 GB of VRAM. Most laptops have 4–8 GB. Kaggle gives every verified account **30 free GPU hours per week** on P100/T4 instances. This app is the bridge.

---

## Supported models

| Model | VRAM | Best for |
|---|---|---|
| `qwen2.5-coder:7b` | ~5 GB | Fast completions, everyday coding |
| `qwen2.5-coder:14b` | ~9 GB | Balanced speed + quality |
| `qwen2.5-coder:32b` | ~20 GB | Best quality (P100 only) |
| `deepseek-coder-v2:16b` | ~10 GB | Strong reasoning + code |
| `codellama:13b` | ~8 GB | General purpose |

---

## Prerequisites

You need three things before starting:

### 1. Kaggle account + API key
1. Sign up at [kaggle.com](https://kaggle.com)
2. Go to **Settings → API → Create New Token** — this downloads `kaggle.json`
3. Your username and key are inside that file

### 2. Phone verification (required for GPU)
Kaggle requires phone verification to unlock GPU kernels.
Complete it at: **[kaggle.com/settings/phone-verification](https://www.kaggle.com/settings/phone-verification)**

### 3. ngrok auth token
1. Sign up at [ngrok.com](https://ngrok.com) (free)
2. Go to **Dashboard → Your Authtoken**
3. Copy the token

---

## Getting started

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
# Runs on http://localhost:8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
```

Open [http://localhost:5173](http://localhost:5173), fill in your credentials, pick a model, and hit **Launch GPU Kernel**.

First launch takes **5–8 minutes** (Ollama install + model download). Subsequent launches of the same model are faster since Kaggle caches the environment.

---

## Project structure

```
kaggle-gpu-ide/
├── backend/
│   ├── main.py              # FastAPI app — session lifecycle endpoints
│   ├── kaggle_runner.py     # Kaggle API client — push, poll, stop kernels
│   ├── auth.py              # Credential + GPU access verification
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   └── src/
│       ├── App.jsx          # Setup / launching / chat screens
│       ├── index.css
│       ├── main.jsx
│       ├── hooks/
│       │   ├── useSession.js   # Session state + polling
│       │   └── useChat.js      # Message history + inference
│       └── lib/
│           └── api.js          # Backend + tunnel API clients
├── kernel/
│   └── kernel_bootstrap.py  # Runs ON Kaggle GPU — installs Ollama + ngrok
└── pyproject.toml
```

---

## How it works

```
1. You enter Kaggle credentials + ngrok token in the setup form

2. Backend calls POST /auth/verify
   ├── Checks API key is valid
   └── Confirms GPU access is enabled on your account

3. Backend calls Kaggle API to push kernel_bootstrap.py
   to your Kaggle account with GPU + internet enabled

4. kernel_bootstrap.py runs on Kaggle's GPU:
   ├── Installs Ollama
   ├── Pulls your chosen model
   ├── Starts a FastAPI inference server on port 8000
   └── Opens an ngrok tunnel → prints [TUNNEL_URL]https://...[/TUNNEL_URL]

5. Backend polls the kernel log every 8s until the URL appears

6. Frontend receives the tunnel URL → all prompts go DIRECTLY
   to your Kaggle kernel — no inference traffic through any shared server
```

---

## API reference

### Backend (`http://localhost:8000`)

| Method | Path | Description |
|---|---|---|
| `POST` | `/auth/verify` | Validate credentials + GPU access |
| `POST` | `/session/start` | Push kernel + begin polling |
| `GET` | `/session/{id}/status` | `launching` / `ready` / `error` |
| `DELETE` | `/session/{id}` | Stop kernel + clear session |
| `GET` | `/health` | Liveness check |

### Kernel tunnel (`https://<ngrok-url>`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Kernel liveness |
| `GET` | `/models` | List pulled Ollama models |
| `POST` | `/generate` | Run inference |

---

## Environment variables

Create a `.env` file in `backend/` (see `.env.example`):

```env
# Not strictly required — credentials are passed per-request from the frontend.
# Set these if you want to hardcode a single-user deployment.
KAGGLE_USERNAME=
KAGGLE_KEY=
NGROK_AUTHTOKEN=
SECRET_KEY=
```

---

## Kaggle GPU quota

- **30 hours/week** per verified account
- Resets every Sunday
- Kernels auto-terminate after **12 hours** of continuous runtime
- GPU types: **Tesla P100** (16 GB VRAM) or **Tesla T4** (15 GB VRAM) — assigned automatically

---

## Contributing

```bash
# Fork → clone → create a feature branch
git checkout -b feat/your-feature

# Make changes, then open a PR against dev (not main)
```

Please keep PRs focused. One feature or fix per PR.

---

## License

GNU — see [LICENSE](LICENSE).

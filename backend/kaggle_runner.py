"""
kaggle_runner.py
----------------
Orchestrates the user's Kaggle GPU kernel entirely via the Kaggle REST API.

Responsibilities:
  - Push kernel_bootstrap.py to the user's Kaggle account
  - Enable GPU + internet on the kernel
  - Poll the kernel's log output until the ngrok URL appears
  - Expose helpers to check status and stop the kernel

The user's credentials never leave their machine — they are passed
directly to the Kaggle API from the backend and are NOT stored by us.
"""

import re
import asyncio
import textwrap
from pathlib import Path

import httpx

KAGGLE_API_BASE = "https://www.kaggle.com/api/v1"
KERNEL_SLUG     = "ollama-gpu-bridge"          # slug used on Kaggle
TUNNEL_PATTERN  = re.compile(r"\[TUNNEL_URL\](https://[^\[]+)\[/TUNNEL_URL\]")


class KaggleRunner:
    """One instance per user session."""

    def __init__(self, username: str, api_key: str, ngrok_token: str):
        self.username    = username.lower().strip()
        self.api_key     = api_key.strip()
        self.ngrok_token = ngrok_token.strip()
        self._auth       = (self.username, self.api_key)
        self.full_slug   = f"{self.username}/{KERNEL_SLUG}"

    # ── Internal HTTP helpers ───────────────────────────────────────────────

    async def _get(self, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{KAGGLE_API_BASE}{path}", auth=self._auth, **kwargs)
            r.raise_for_status()
            return r.json()

    async def _post(self, path: str, payload: dict, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                f"{KAGGLE_API_BASE}{path}",
                auth=self._auth,
                json=payload,
                **kwargs,
            )
            r.raise_for_status()
            return r.json()

    # ── Kernel push ─────────────────────────────────────────────────────────

    async def push_kernel(self, model_name: str = "qwen2.5-coder:7b") -> dict:
        """
        Push kernel_bootstrap.py to Kaggle with GPU + internet enabled.
        Injects OLLAMA_MODEL and NGROK_TOKEN at the top of the script so
        no secrets travel through Kaggle's environment-variable system.
        """
        bootstrap_path = (
            Path(__file__).parent.parent / "kernel" / "kernel_bootstrap.py"
        )
        raw_code = bootstrap_path.read_text(encoding="utf-8")

        # Prepend runtime config — replaces the os.environ.get() fallbacks
        injected_header = textwrap.dedent(f"""\
            # ── Injected by kaggle_runner.push_kernel() ──
            import os
            os.environ["OLLAMA_MODEL"] = "{model_name}"
            os.environ["NGROK_TOKEN"]  = "{self.ngrok_token}"
            # ─────────────────────────────────────────────
        """)
        full_source = injected_header + "\n" + raw_code

        metadata = {
            "id":                 self.full_slug,
            "title":              "Ollama GPU Bridge",
            "code_file":          "kernel_bootstrap.py",
            "language":           "python",
            "kernel_type":        "script",
            "is_private":         True,   # keeps the kernel private to the user
            "enable_gpu":         True,
            "enable_internet":    True,   # required for Ollama install + ngrok
            "dataset_sources":    [],
            "competition_sources":[],
            "kernel_sources":     [],
        }

        payload = {
            "metadata": metadata,
            "blob":     {"source": full_source},
        }

        print(f"[RUNNER] Pushing kernel '{self.full_slug}' to Kaggle...")
        result = await self._post("/kernels/push", payload)
        print(f"[RUNNER] Kernel pushed. Response: {result}")
        return result

    # ── Status & output ─────────────────────────────────────────────────────

    async def get_status(self) -> dict:
        """
        Returns the kernel metadata dict.
        Relevant field: data['status'] — one of:
          'running' | 'complete' | 'error' | 'cancelAcknowledged' | 'queued'
        """
        return await self._get(f"/kernels/{self.full_slug}")

    async def get_log(self) -> str:
        """
        Fetches the raw stdout log from the most recent kernel run.
        Kaggle returns this under the 'log' key.
        """
        try:
            data = await self._get(f"/kernels/{self.full_slug}/output")
            return data.get("log", "")
        except httpx.HTTPStatusError:
            return ""  # output not available yet — kernel still starting

    # ── Tunnel URL polling ──────────────────────────────────────────────────

    async def poll_for_tunnel_url(
        self,
        timeout_seconds: int = 720,   # 12 min — Ollama + model pull can be slow
        poll_interval:   int = 12,
    ) -> str:
        """
        Repeatedly fetches the kernel log until the [TUNNEL_URL]...[/TUNNEL_URL]
        marker printed by kernel_bootstrap.py is found.

        Raises TimeoutError if the URL doesn't appear within `timeout_seconds`.
        """
        print(f"[RUNNER] Waiting for tunnel URL (timeout={timeout_seconds}s)...")
        elapsed = 0

        while elapsed < timeout_seconds:
            log = await self.get_log()

            match = TUNNEL_PATTERN.search(log)
            if match:
                url = match.group(1).strip()
                print(f"[RUNNER] ✓ Tunnel URL found: {url}")
                return url

            # Also surface kernel errors early
            try:
                status_data = await self.get_status()
                if status_data.get("currentRunningVersion", {}).get("status") == "error":
                    raise RuntimeError(
                        "Kaggle kernel entered error state. "
                        "Check the kernel page for details."
                    )
            except httpx.HTTPStatusError:
                pass  # status endpoint not ready yet

            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            print(f"[RUNNER]   ... {elapsed}s elapsed, still waiting")

        raise TimeoutError(
            f"Tunnel URL not found within {timeout_seconds}s. "
            "The kernel may still be starting — check your Kaggle dashboard."
        )

    # ── Stop / cleanup ──────────────────────────────────────────────────────

    async def stop_kernel(self) -> dict:
        """
        Kaggle has no direct 'interrupt' API endpoint for script kernels.
        We push a trivial replacement script which terminates the session
        because Kaggle serialises kernel versions — the new push cancels
        the running one.
        """
        print(f"[RUNNER] Stopping kernel '{self.full_slug}'...")
        payload = {
            "metadata": {
                "id":              self.full_slug,
                "title":           "Ollama GPU Bridge",
                "code_file":       "stop.py",
                "language":        "python",
                "kernel_type":     "script",
                "is_private":      True,
                "enable_gpu":      False,
                "enable_internet": False,
                "dataset_sources":    [],
                "competition_sources":[],
                "kernel_sources":     [],
            },
            "blob": {"source": 'print("Session stopped by user.")'},
        }
        result = await self._post("/kernels/push", payload)
        print("[RUNNER] Stop signal sent.")
        return result
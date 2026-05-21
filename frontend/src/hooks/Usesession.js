import { useState, useRef, useCallback } from "react";
import { verifyCredentials, startSession, getSessionStatus, stopSession } from "../lib/api";

export function useSession() {
  const [phase, setPhase]         = useState("idle");   // idle | verifying | launching | ready | error
  const [sessionId, setSessionId] = useState(null);
  const [tunnelUrl, setTunnelUrl] = useState(null);
  const [error, setError]         = useState(null);
  const [elapsed, setElapsed]     = useState(0);
  const pollRef  = useRef(null);
  const timerRef = useRef(null);

  const clearTimers = () => {
    clearInterval(pollRef.current);
    clearInterval(timerRef.current);
  };

  const launch = useCallback(async (credentials) => {
    setError(null);
    setElapsed(0);
    setTunnelUrl(null);

    // ── Step 1: verify credentials + GPU access ──────────────────────
    setPhase("verifying");
    try {
      const check = await verifyCredentials(credentials);
      if (!check.valid) {
        setError(check.error || "Invalid Kaggle credentials.");
        setPhase("error");
        return;
      }
      if (!check.gpu_enabled) {
        setError(check.error || "GPU access not enabled on your Kaggle account.");
        setPhase("error");
        return;
      }
    } catch (e) {
      setError(e.message);
      setPhase("error");
      return;
    }

    // ── Step 2: launch kernel ────────────────────────────────────────
    setPhase("launching");
    try {
      const { session_id } = await startSession(credentials);
      setSessionId(session_id);

      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);

      pollRef.current = setInterval(async () => {
        try {
          const data = await getSessionStatus(session_id);
          if (data.status === "ready") {
            clearTimers();
            setTunnelUrl(data.tunnel_url);
            setPhase("ready");
          } else if (data.status === "error") {
            clearTimers();
            setError(data.error || "Kernel failed to start");
            setPhase("error");
          }
        } catch {}
      }, 8000);
    } catch (e) {
      clearTimers();
      setError(e.message);
      setPhase("error");
    }
  }, []);

  const stop = useCallback(async () => {
    clearTimers();
    if (sessionId) {
      try { await stopSession(sessionId); } catch {}
    }
    setPhase("idle");
    setSessionId(null);
    setTunnelUrl(null);
    setError(null);
    setElapsed(0);
  }, [sessionId]);

  return { phase, sessionId, tunnelUrl, error, elapsed, launch, stop };
}

export function useSession() {
  const [phase, setPhase]         = useState("idle");   // idle | launching | ready | error
  const [sessionId, setSessionId] = useState(null);
  const [tunnelUrl, setTunnelUrl] = useState(null);
  const [error, setError]         = useState(null);
  const [elapsed, setElapsed]     = useState(0);        // seconds since launch
  const pollRef  = useRef(null);
  const timerRef = useRef(null);

  const clearTimers = () => {
    clearInterval(pollRef.current);
    clearInterval(timerRef.current);
  };

  const launch = useCallback(async (credentials) => {
    setPhase("launching");
    setError(null);
    setElapsed(0);
    setTunnelUrl(null);

    try {
      const { session_id } = await startSession(credentials);
      setSessionId(session_id);

      // Tick elapsed seconds
      timerRef.current = setInterval(() => setElapsed(e => e + 1), 1000);

      // Poll status every 8 seconds
      pollRef.current = setInterval(async () => {
        try {
          const data = await getSessionStatus(session_id);
          if (data.status === "ready") {
            clearTimers();
            setTunnelUrl(data.tunnel_url);
            setPhase("ready");
          } else if (data.status === "error") {
            clearTimers();
            setError(data.error || "Kernel failed to start");
            setPhase("error");
          }
        } catch (e) {
          // transient network error — keep polling
        }
      }, 8000);
    } catch (e) {
      clearTimers();
      setError(e.message);
      setPhase("error");
    }
  }, []);

  const stop = useCallback(async () => {
    clearTimers();
    if (sessionId) {
      try { await stopSession(sessionId); } catch {}
    }
    setPhase("idle");
    setSessionId(null);
    setTunnelUrl(null);
    setError(null);
    setElapsed(0);
  }, [sessionId]);

  return { phase, sessionId, tunnelUrl, error, elapsed, launch, stop };
}
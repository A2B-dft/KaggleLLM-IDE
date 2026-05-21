// src/App.jsx
import { useState, useRef, useEffect } from "react";
import { useSession } from "./hooks/useSession";
import { useChat }    from "./hooks/useChat";

// ── Available coding models ──────────────────────────────────────────────
const MODELS = [
  { value: "qwen2.5-coder:7b",   label: "Qwen2.5-Coder 7B",   vram: "~5 GB"  },
  { value: "qwen2.5-coder:14b",  label: "Qwen2.5-Coder 14B",  vram: "~9 GB"  },
  { value: "qwen2.5-coder:32b",  label: "Qwen2.5-Coder 32B",  vram: "~20 GB" },
  { value: "deepseek-coder-v2:16b", label: "DeepSeek-Coder V2 16B", vram: "~10 GB" },
  { value: "codellama:13b",      label: "Code Llama 13B",      vram: "~8 GB"  },
];

// ── Tiny markdown-ish renderer (code blocks + inline code only) ──────────
function MessageContent({ text }) {
  const parts = text.split(/(```[\s\S]*?```)/g);
  return (
    <div className="msg-body">
      {parts.map((part, i) => {
        if (part.startsWith("```")) {
          const lines = part.slice(3).split("\n");
          const lang  = lines[0].trim();
          const code  = lines.slice(1).join("\n").replace(/```$/, "").trimEnd();
          return (
            <div key={i} className="code-block">
              {lang && <span className="code-lang">{lang}</span>}
              <pre><code>{code}</code></pre>
            </div>
          );
        }
        // Inline code
        const inline = part.split(/(`[^`]+`)/g);
        return (
          <span key={i}>
            {inline.map((s, j) =>
              s.startsWith("`") && s.endsWith("`")
                ? <code key={j} className="inline-code">{s.slice(1, -1)}</code>
                : <span key={j}>{s}</span>
            )}
          </span>
        );
      })}
    </div>
  );
}

// ── Setup form ───────────────────────────────────────────────────────────
function SetupScreen({ onLaunch }) {
  const [form, setForm] = useState({
    kaggleUsername: "",
    kaggleApiKey:   "",
    ngrokToken:     "",
    model:          MODELS[0].value,
  });
  const [showKey, setShowKey] = useState(false);

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }));
  const ready = form.kaggleUsername && form.kaggleApiKey && form.ngrokToken;

  return (
    <div className="setup-screen">
      <div className="setup-card">
        <div className="setup-logo">
          <span className="logo-bracket">[</span>
          <span className="logo-text">KAGGLE<span className="logo-accent">GPU</span></span>
          <span className="logo-bracket">]</span>
        </div>
        <p className="setup-tagline">
          Run frontier coding models on your own free Kaggle GPU.
        </p>

        <div className="form-group">
          <label>Kaggle Username</label>
          <input
            type="text"
            placeholder="jdoe"
            value={form.kaggleUsername}
            onChange={set("kaggleUsername")}
            autoComplete="off"
          />
        </div>

        <div className="form-group">
          <label>Kaggle API Key</label>
          <div className="input-row">
            <input
              type={showKey ? "text" : "password"}
              placeholder="From kaggle.com → Settings → API"
              value={form.kaggleApiKey}
              onChange={set("kaggleApiKey")}
              autoComplete="off"
            />
            <button
              className="toggle-btn"
              onClick={() => setShowKey(s => !s)}
              tabIndex={-1}
            >
              {showKey ? "hide" : "show"}
            </button>
          </div>
          <span className="hint">
            <a href="https://www.kaggle.com/settings" target="_blank" rel="noreferrer">
              kaggle.com → Settings → Create New Token
            </a>
          </span>
        </div>

        <div className="form-group">
          <label>ngrok Auth Token</label>
          <input
            type="password"
            placeholder="From dashboard.ngrok.com"
            value={form.ngrokToken}
            onChange={set("ngrokToken")}
            autoComplete="off"
          />
          <span className="hint">
            <a href="https://dashboard.ngrok.com/get-started/your-authtoken" target="_blank" rel="noreferrer">
              dashboard.ngrok.com → Your Authtoken
            </a>
          </span>
        </div>

        <div className="form-group">
          <label>Model</label>
          <select value={form.model} onChange={set("model")}>
            {MODELS.map(m => (
              <option key={m.value} value={m.value}>
                {m.label} — {m.vram}
              </option>
            ))}
          </select>
          <span className="hint">Kaggle P100 has 16 GB VRAM. T4 has 15 GB.</span>
        </div>

        <button
          className="launch-btn"
          disabled={!ready}
          onClick={() => onLaunch(form)}
        >
          LAUNCH GPU KERNEL →
        </button>

        <p className="fine-print">
          Your credentials are sent directly to Kaggle's API — never stored on our servers.
        </p>
      </div>
    </div>
  );
}

// ── Launching screen ─────────────────────────────────────────────────────
const LAUNCH_STAGES = [
  { at:   0, text: "Pushing kernel to Kaggle..."          },
  { at:  15, text: "Kaggle queuing GPU instance..."       },
  { at:  30, text: "Installing Ollama..."                 },
  { at:  90, text: "Pulling model weights..."             },
  { at: 240, text: "Starting inference server..."         },
  { at: 360, text: "Opening tunnel... (almost there)"     },
];

function LaunchingScreen({ elapsed, onCancel }) {
  const stage = [...LAUNCH_STAGES].reverse().find(s => elapsed >= s.at) || LAUNCH_STAGES[0];
  const pct   = Math.min(95, Math.round((elapsed / 480) * 100));
  const mm    = String(Math.floor(elapsed / 60)).padStart(2, "0");
  const ss    = String(elapsed % 60).padStart(2, "0");

  return (
    <div className="launch-screen">
      <div className="launch-card">
        <div className="spinner-ring" />
        <div className="launch-timer">{mm}:{ss}</div>
        <div className="launch-stage">{stage.text}</div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${pct}%` }} />
        </div>
        <p className="launch-note">
          First launch takes 5–8 min (model download). Subsequent launches are faster.
        </p>
        <button className="cancel-btn" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

// ── Chat UI ───────────────────────────────────────────────────────────────
function ChatScreen({ tunnelUrl, model, onStop }) {
  const { messages, loading, error, send, clear } = useChat(tunnelUrl, model);
  const [input, setInput] = useState("");
  const bottomRef = useRef(null);
  const inputRef  = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const handleSend = () => {
    if (!input.trim()) return;
    send(input);
    setInput("");
    inputRef.current?.focus();
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const modelLabel = MODELS.find(m => m.value === model)?.label ?? model;

  return (
    <div className="chat-screen">
      <header className="chat-header">
        <div className="header-left">
          <span className="header-logo">[KGPU]</span>
          <span className="header-model">{modelLabel}</span>
          <span className="status-dot" title="Kernel running" />
        </div>
        <div className="header-right">
          <button className="icon-btn" onClick={clear} title="Clear chat">
            ⌫ clear
          </button>
          <button className="stop-btn" onClick={onStop}>
            ■ STOP KERNEL
          </button>
        </div>
      </header>

      <div className="messages">
        {messages.length === 0 && (
          <div className="empty-state">
            <div className="empty-icon">⬡</div>
            <p>Kernel is live. Ask anything about code.</p>
            <div className="example-chips">
              {[
                "Write a Python binary search",
                "Explain async/await in JS",
                "Fix this SQL query",
                "Review my React component",
              ].map(q => (
                <button key={q} className="chip" onClick={() => send(q)}>{q}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <div key={msg.id} className={`message message--${msg.role}`}>
            <span className="msg-role">{msg.role === "user" ? "YOU" : "AI"}</span>
            <MessageContent text={msg.content} />
          </div>
        ))}

        {loading && (
          <div className="message message--assistant message--thinking">
            <span className="msg-role">AI</span>
            <div className="thinking-dots">
              <span/><span/><span/>
            </div>
          </div>
        )}

        {error && (
          <div className="error-banner">⚠ {error}</div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="input-bar">
        <textarea
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask about code... (Enter to send, Shift+Enter for newline)"
          rows={1}
          disabled={loading}
        />
        <button
          className="send-btn"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          ▶
        </button>
      </div>
    </div>
  );
}

// ── Root ─────────────────────────────────────────────────────────────────
export default function App() {
  const { phase, tunnelUrl, error, elapsed, launch, stop } = useSession();
  const [chosenModel, setChosenModel] = useState(MODELS[0].value);

  const handleLaunch = (form) => {
    setChosenModel(form.model);
    launch(form);
  };

  return (
    <>
      {phase === "idle"      && <SetupScreen onLaunch={handleLaunch} />}
      {phase === "launching" && <LaunchingScreen elapsed={elapsed} onCancel={stop} />}
      {phase === "ready"     && <ChatScreen tunnelUrl={tunnelUrl} model={chosenModel} onStop={stop} />}
      {phase === "error"     && (
        <div className="error-screen">
          <div className="error-card">
            <div className="error-icon">✕</div>
            <h2>Kernel failed to start</h2>
            <p>{error}</p>
            <button className="launch-btn" onClick={stop}>← Try Again</button>
          </div>
        </div>
      )}
    </>
  );
}
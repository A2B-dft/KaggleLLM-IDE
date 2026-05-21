// src/hooks/useChat.js
import { useState, useCallback } from "react";
import { generateCompletion } from "../lib/api";

export function useChat(tunnelUrl, model) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);

  const buildPrompt = (history, newUserMsg) => {
    // Simple conversation format Ollama understands
    const lines = history.map(m =>
      m.role === "user" ? `User: ${m.content}` : `Assistant: ${m.content}`
    );
    lines.push(`User: ${newUserMsg}`);
    lines.push("Assistant:");
    return lines.join("\n\n");
  };

  const send = useCallback(async (userText) => {
    if (!userText.trim() || loading) return;
    setError(null);

    const userMsg = { id: Date.now(), role: "user", content: userText };
    setMessages(prev => [...prev, userMsg]);
    setLoading(true);

    try {
      const prompt = buildPrompt(messages, userText);
      const response = await generateCompletion(tunnelUrl, {
        model,
        prompt,
        system:
          "You are an expert coding assistant. Provide clear, concise, correct code. " +
          "Format code blocks with the appropriate language tag.",
        temperature: 0.2,
      });

      const assistantMsg = {
        id: Date.now() + 1,
        role: "assistant",
        content: response,
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [messages, loading, tunnelUrl, model]);

  const clear = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return { messages, loading, error, send, clear };
}
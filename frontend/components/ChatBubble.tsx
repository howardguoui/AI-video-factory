"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface ChatBubbleProps {
  context?: string;
}

export function ChatBubble({ context }: ChatBubbleProps = {}) {
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [modelName, setModelName] = useState<string | null>(null);
  const [modelError, setModelError] = useState<string | null>(null); // null = ok, string = error message
  const [statusChecked, setStatusChecked] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Check Ollama connectivity when the panel opens (or on retry)
  function checkStatus() {
    setStatusChecked(false);
    setModelName(null);
    setModelError(null);
    fetch(`${API_URL}/chat/status`)
      .then((r) => r.json())
      .then((d: { ok: boolean; model: string | null; error?: string | null }) => {
        if (d.ok && d.model) {
          setModelName(d.model);
          setModelError(null);
        } else {
          setModelName(null);
          setModelError(d.error ?? "Ollama unreachable");
        }
      })
      .catch(() => {
        setModelName(null);
        setModelError("Backend unreachable — is the FastAPI server running on port 8000?");
      })
      .finally(() => setStatusChecked(true));
  }

  useEffect(() => {
    if (isOpen && !statusChecked) checkStatus();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  useEffect(() => {
    if (isOpen) messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isOpen]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, 120)}px`;
  }, [input]);

  async function sendMessage() {
    const text = input.trim();
    if (!text || isStreaming || modelError) return;

    const userMsg: Message = { role: "user", content: text };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setIsStreaming(true);

    // Add empty placeholder for the streaming reply
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    const abort = new AbortController();
    abortRef.current = abort;

    try {
      const res = await fetch(`${API_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: nextMessages, context: context ?? null }),
        signal: abort.signal,
      });

      if (!res.ok || !res.body) {
        throw new Error(`Server returned HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let done = false;

      while (!done) {
        const { done: streamDone, value } = await reader.read();
        if (streamDone) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const data = line.slice(6);
          if (data === "[DONE]") {
            done = true;   // exit the outer while loop after this iteration
            break;
          }
          try {
            const token = JSON.parse(data) as string;
            setMessages((prev) => {
              const last = prev[prev.length - 1];
              return [...prev.slice(0, -1), { ...last, content: last.content + token }];
            });
          } catch {
            // ignore malformed SSE chunks
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        // User cancelled — leave partial response
      } else {
        const msg = err instanceof Error ? err.message : String(err);
        setMessages((prev) => [
          ...prev.slice(0, -1),
          { role: "assistant", content: `⚠ ${msg}\n\nMake sure Ollama is running (\`ollama serve\`) and a model is loaded (\`ollama run <model>\`).` },
        ]);
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  }

  function stopStreaming() {
    abortRef.current?.abort();
  }

  // Short display name for the model (last segment after /)
  const shortModel = modelName
    ? modelName.split("/").pop()?.split(":")[0] ?? modelName
    : null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {/* Chat panel */}
      {isOpen && (
        <div
          className="w-80 sm:w-96 bg-zinc-900 border border-zinc-700 rounded-2xl shadow-2xl shadow-black/60 flex flex-col overflow-hidden"
          style={{ height: "480px" }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800 flex-shrink-0">
            <div className="flex items-center gap-2 min-w-0">
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  modelError ? "bg-red-400" : modelName ? "bg-emerald-400 animate-pulse" : "bg-yellow-400 animate-pulse"
                }`}
              />
              <span className="text-white text-sm font-semibold">AI Assistant</span>
              {modelError ? (
                <span className="text-red-400 text-xs truncate">error</span>
              ) : shortModel ? (
                <span className="text-zinc-500 text-xs truncate" title={modelName ?? ""}>{shortModel}</span>
              ) : (
                <span className="text-zinc-600 text-xs">connecting…</span>
              )}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {modelError && (
                <button
                  onClick={checkStatus}
                  title="Retry connection"
                  className="text-zinc-500 hover:text-yellow-400 transition-colors text-xs px-1.5 py-0.5 rounded border border-zinc-700 hover:border-yellow-600"
                >
                  Retry
                </button>
              )}
              {messages.length > 0 && !modelError && (
                <button
                  onClick={() => setMessages([])}
                  className="text-zinc-600 hover:text-zinc-400 transition-colors text-xs px-1.5 py-0.5 rounded"
                >
                  Clear
                </button>
              )}
              <button
                onClick={() => setIsOpen(false)}
                className="text-zinc-500 hover:text-white transition-colors p-0.5"
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          </div>

          {/* Error banner with exact message */}
          {modelError && (
            <div className="mx-3 mt-3 px-3 py-2.5 bg-red-950 border border-red-800 rounded-xl text-red-300 text-xs leading-relaxed flex-shrink-0 space-y-1">
              <p className="font-medium text-red-400">Cannot connect to Ollama</p>
              <p>{modelError}</p>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 space-y-3 min-h-0">
            {messages.length === 0 ? (
              <div className="text-center text-zinc-600 text-sm pt-8 space-y-1 select-none">
                <p className="text-2xl">💬</p>
                <p className="font-medium text-zinc-500">Ask anything</p>
                <p className="text-xs leading-relaxed">
                  Translation settings, pipeline modes,
                  <br />troubleshooting, TTS engines…
                </p>
              </div>
            ) : (
              messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] px-3 py-2 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap break-words ${
                      msg.role === "user"
                        ? "bg-indigo-600 text-white rounded-br-md"
                        : "bg-zinc-800 text-zinc-200 rounded-bl-md"
                    }`}
                  >
                    {msg.content || (isStreaming && i === messages.length - 1
                      ? <span className="inline-block w-1.5 h-4 bg-zinc-400 animate-pulse rounded-sm" />
                      : null
                    )}
                  </div>
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-3 border-t border-zinc-800 flex-shrink-0">
            <div className="flex gap-2 items-end">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask… (Enter to send, Shift+Enter for newline)"
                rows={1}
                disabled={isStreaming || !!modelError}
                className="flex-1 bg-zinc-800 border border-zinc-700 text-white placeholder-zinc-500 rounded-xl px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-indigo-500 resize-none disabled:opacity-40"
                style={{ minHeight: "38px", maxHeight: "120px" }}
              />
              {isStreaming ? (
                <button
                  onClick={stopStreaming}
                  title="Stop"
                  className="p-2 bg-zinc-700 hover:bg-zinc-600 text-white rounded-xl transition-colors flex-shrink-0"
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                    <rect x="4" y="4" width="12" height="12" rx="1" />
                  </svg>
                </button>
              ) : (
                <button
                  onClick={sendMessage}
                  disabled={!input.trim() || !!modelError}
                  title="Send (Enter)"
                  className="p-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-xl transition-colors flex-shrink-0"
                >
                  <svg viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                    <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z" />
                  </svg>
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Toggle button */}
      <button
        onClick={() => setIsOpen((o) => !o)}
        className={`w-14 h-14 rounded-full shadow-lg transition-all flex items-center justify-center ${
          isOpen
            ? "bg-zinc-700 hover:bg-zinc-600 shadow-black/40"
            : "bg-indigo-600 hover:bg-indigo-500 shadow-indigo-900/50 hover:scale-105"
        }`}
        title={isOpen ? "Close assistant" : "Open AI assistant"}
      >
        {isOpen ? (
          <svg viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5 text-white">
            <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="currentColor" className="w-6 h-6 text-white">
            <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z" />
          </svg>
        )}
      </button>
    </div>
  );
}

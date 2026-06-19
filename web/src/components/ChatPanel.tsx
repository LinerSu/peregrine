import { useRef, useState } from "react";
import { api } from "../api";

interface Msg {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPanel({ onAction }: { onAction: () => void }) {
  const [messages, setMessages] = useState<Msg[]>([
    {
      role: "assistant",
      content:
        'Hi! I\'m Peregrine, your local job-search assistant. Paste your CV, or try: "find jobs matching my CV" — I\'ll scan supported boards, score fit, prep materials, and track your applications.\n\nA note on what I can\'t do: I only fetch boards that allow it, so I won\'t scrape sites like LinkedIn or Indeed (paste those job descriptions instead), I never bypass logins or bot-checks, and I never submit an application for you — you always click Apply yourself.',
    },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    setBusy(true);
    try {
      const res = await api.chat(text, history);
      setMessages((m) => [...m, { role: "assistant", content: res.reply }]);
      if (res.actions && res.actions.length > 0) onAction();
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${(e as Error).message}` }]);
    } finally {
      setBusy(false);
      setTimeout(() => scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight), 50);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-3 border-b border-gray-200 font-semibold text-gray-700">Assistant</div>
      <div ref={scrollRef} className="flex-1 overflow-auto p-3 space-y-3">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[85%] px-3 py-2 rounded-lg text-sm whitespace-pre-wrap ${
                m.role === "user" ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-800"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {busy && <div className="text-xs text-gray-400">thinking…</div>}
      </div>
      <div className="p-3 border-t border-gray-200">
        <div className="flex gap-2">
          <textarea
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md resize-none"
            rows={2}
            placeholder="Ask the assistant…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
          <button
            onClick={send}
            disabled={busy}
            className="px-4 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}

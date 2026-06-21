import { useState } from "react";
import ChatPanel from "./ChatPanel";
import TerminalPanel from "./TerminalPanel";

// The assistant runs in one of two modes:
//   external — API-backed chat. Uses LLM_PROVIDER + key (anthropic/openai/...),
//              billed per token. The "core" path for whoever has API budget.
//   internal — a local terminal running `claude` on your own machine, so you
//              drive Claude on your existing subscription (no API key, no
//              per-token cost). See TerminalPanel / scripts/terminal.sh.
type Mode = "external" | "internal";

export default function AssistantPanel({ onAction }: { onAction: () => void }) {
  const [mode, setMode] = useState<Mode>("external");

  const tab = (m: Mode, label: string, title: string) => (
    <button
      onClick={() => setMode(m)}
      title={title}
      className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
        mode === m
          ? "bg-indigo-600 text-white"
          : "text-gray-500 hover:text-gray-700"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-1 p-2 border-b border-gray-200">
        {tab("external", "External", "API-backed assistant (uses LLM_PROVIDER + key)")}
        {tab("internal", "Internal (Claude)", "Local Claude in a terminal — runs on your own subscription")}
      </div>
      <div className="flex-1 min-h-0">
        {mode === "external" ? <ChatPanel onAction={onAction} /> : <TerminalPanel />}
      </div>
    </div>
  );
}

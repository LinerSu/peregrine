import ChatPanel from "./ChatPanel";
import TerminalPanel from "./TerminalPanel";
import type { AssistantMode } from "../App";

// The assistant runs in one of two modes. The toggle lives in the app header (top bar),
// since the mode governs EVERY LLM action across all tabs — not just this panel — so a single
// global control belongs there rather than duplicated here. This panel just renders whichever
// the mode selects:
//   external — API-backed chat. Uses LLM_PROVIDER + key (anthropic/openai/...), billed per token.
//   internal — a local terminal running `claude` on your own subscription (no API key).
export default function AssistantPanel({
  onAction,
  mode,
}: {
  onAction: () => void;
  mode: AssistantMode;
}) {
  // BOTH children stay mounted, hidden by CSS — a ternary would unmount the ttyd
  // iframe on every mode flip and kill the live terminal session (and drop chat
  // history on the way back). Same rule as the rail collapse in App.tsx.
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className={mode === "external" ? "flex flex-col h-full min-h-0" : "hidden"}>
        <ChatPanel onAction={onAction} />
      </div>
      <div className={mode === "internal" ? "flex flex-col h-full min-h-0" : "hidden"}>
        <TerminalPanel />
      </div>
    </div>
  );
}

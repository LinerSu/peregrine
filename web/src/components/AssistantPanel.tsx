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
  return (
    <div className="flex flex-col h-full min-h-0">
      {mode === "external" ? <ChatPanel onAction={onAction} /> : <TerminalPanel />}
    </div>
  );
}

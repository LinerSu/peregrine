import { useRef } from "react";
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
  // The terminal mounts LAZILY — only once the user first selects Internal — and
  // never unmounts after (CSS-hide only, so the live ttyd session survives mode
  // flips and the rail collapse). Eager mounting would make the hidden iframe
  // connect on EVERY page load, and ttyd spawns a full `claude` process per
  // websocket client — one hidden host process per tab, even for users who never
  // leave External mode.
  const booted = useRef(mode === "internal");
  if (mode === "internal") booted.current = true;
  return (
    <div className="flex flex-col h-full min-h-0">
      <div className={mode === "external" ? "flex flex-col h-full min-h-0" : "hidden"}>
        <ChatPanel onAction={onAction} />
      </div>
      {booted.current && (
        <div className={mode === "internal" ? "flex flex-col h-full min-h-0" : "hidden"}>
          <TerminalPanel />
        </div>
      )}
    </div>
  );
}

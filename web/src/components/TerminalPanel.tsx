// Embeds a LOCAL-ONLY web terminal (ttyd) running on the host machine, so you
// can drive an interactive `claude` session on your own Anthropic subscription —
// no API key, no per-token cost. The browser loads this iframe directly from the
// host (it isn't proxied through the API container), which is why it can reach a
// process that lives on your machine rather than inside Docker.
//
// Start the terminal server with `./scripts/terminal.sh` (binds to 127.0.0.1).
// It is full shell access — never expose that port off your machine.
// `||` (not `??`) so an empty build-time value also falls back to the default —
// the Docker build injects VITE_TERMINAL_URL as "" when the arg is unset.
const TERMINAL_URL = import.meta.env.VITE_TERMINAL_URL || "http://localhost:7681";

export default function TerminalPanel() {
  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 text-xs text-gray-500 border-b border-gray-200 bg-gray-50">
        Local terminal on your machine. If blank, start it with{" "}
        <code className="px-1 rounded bg-gray-200 text-gray-700">./scripts/terminal.sh</code>.{" "}
        <a
          href={TERMINAL_URL}
          target="_blank"
          rel="noreferrer"
          className="text-indigo-600 hover:underline"
        >
          Open in a new tab
        </a>
      </div>
      <iframe
        title="Local terminal"
        src={TERMINAL_URL}
        className="flex-1 w-full border-0"
      />
    </div>
  );
}

import { useState } from "react";

// A copyable, EDITABLE prompt for an external agent (another Claude session,
// ChatGPT, …) that produces markdown Peregrine can take back in. Editable so the
// user can trim fields or append context ("the posting is at <url>") before
// copying; the hint says where to paste the agent's OUTPUT back into the app.
export default function AgentPromptModal({
  title,
  prompt,
  hint,
  onClose,
}: {
  title: string;
  prompt: string;
  hint: string;
  onClose: () => void;
}) {
  const [text, setText] = useState(prompt);
  const [copied, setCopied] = useState(false);

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4 overflow-auto">
      <div
        className="w-full max-w-2xl my-8 rounded-lg bg-white shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="agent-prompt-title"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
          <h2 id="agent-prompt-title" className="text-sm font-semibold text-gray-800">
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="px-2 py-0.5 text-gray-400 hover:text-gray-600"
          >
            ✕
          </button>
        </div>
        <div className="p-5 space-y-3">
          <p className="text-xs text-gray-600">
            Review or edit the prompt (e.g. add the posting URL at the end), copy it, and give
            it to any AI agent. {hint}
          </p>
          <textarea
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              setCopied(false);
            }}
            rows={18}
            spellCheck={false}
            className="w-full px-3 py-2 text-xs font-mono border border-gray-300 rounded-md text-gray-800"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={() =>
                navigator.clipboard
                  ?.writeText(text)
                  .then(() => setCopied(true))
                  .catch(() => {})
              }
              className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
            >
              {copied ? "Copied ✓" : "Copy prompt"}
            </button>
            <button
              onClick={() => {
                setText(prompt);
                setCopied(false);
              }}
              className="px-3 py-1.5 text-sm text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              Reset
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

import { useEffect, useRef, useState } from "react";
import { api, type Evaluation, type Job } from "../api";
import type { AssistantMode } from "../App";
import { legitimacyClass } from "../format";
import JobMarkdown from "./JobMarkdown";

// Job detail with the human-in-the-loop apply gate. "Evaluate fit" is mode-aware:
//   External — the API runs the evaluation on click.
//   Internal — you run one line in the Claude terminal; this panel polls for the
//   evaluation Claude saves (fit score + "Agent evaluation" section) and reloads.
export default function JobDetail({
  jobId,
  onChanged,
  mode,
}: {
  jobId: string;
  onChanged: () => void;
  mode: AssistantMode;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState(false);
  const [applyUrl, setApplyUrl] = useState<string | null>(null);
  const [evalPrompt, setEvalPrompt] = useState(""); // Internal: the line to run
  const [waitingEval, setWaitingEval] = useState(false);
  const [copied, setCopied] = useState(false);
  const baseline = useRef(""); // job markdown before the run

  // Empty {} from the API (no evaluation yet) -> null.
  const normEval = (ev: Evaluation | null) => (ev && Object.keys(ev).length ? ev : null);

  const load = async () => {
    const { job, markdown } = await api.getJob(jobId);
    setJob(job);
    setMarkdown(markdown);
    setEvaluation(normEval(await api.getEvaluation(jobId).catch(() => null)));
  };

  useEffect(() => {
    setApplyUrl(null);
    setEvalPrompt("");
    setWaitingEval(false);
    setEvaluation(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  // Internal: poll until Claude saves an evaluation (the markdown changes).
  useEffect(() => {
    if (!waitingEval) return;
    const started = Date.now();
    let inFlight = false; // don't let a slow request overlap the next tick
    let live = true; // don't setState after cleanup if a request is mid-flight
    const id = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await api.getJob(jobId).catch(() => null);
        if (!live) return;
        if (res && res.markdown !== baseline.current) {
          setJob(res.job);
          setMarkdown(res.markdown);
          const ev = await api.getEvaluation(jobId).catch(() => null);
          if (!live) return;
          setEvaluation(normEval(ev));
          onChanged();
          setWaitingEval(false);
        } else if (Date.now() - started > 180_000) {
          setWaitingEval(false);
        }
      } finally {
        inFlight = false;
      }
    }, 3000);
    return () => {
      live = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waitingEval, jobId]);

  const evaluate = async () => {
    if (mode === "internal") {
      if (waitingEval) return; // already waiting on a save — don't restart/overlap
      baseline.current = markdown;
      setEvalPrompt(`evaluate fit for ${jobId}`);
      setCopied(false);
      setWaitingEval(true);
      return;
    }
    setBusy(true);
    try {
      await api.evaluate(jobId);
      await load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const prepare = async () => {
    setBusy(true);
    try {
      const res = await api.prepare(jobId);
      setApplyUrl(res.apply_url);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const markApplied = async () => {
    setBusy(true);
    try {
      await api.markApplied(jobId);
      await load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  if (!job) return <div className="p-6 text-gray-400">Loading…</div>;

  const applied = job.status === "applied";

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold">{job.position}</h2>
        <p className="text-sm text-gray-500">
          {job.company} · {job.location || "—"} · fit {job.fit_score != null ? job.fit_score.toFixed(2) : "n/a"}
        </p>
        <div className="flex gap-2 mt-3">
          <button
            onClick={evaluate}
            disabled={busy || waitingEval}
            className="px-3 py-1.5 text-sm font-medium text-white bg-emerald-600 rounded-md hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? "Working…" : waitingEval ? "Waiting…" : "Evaluate fit"}
          </button>
          <button
            onClick={prepare}
            disabled={busy}
            className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-100 rounded-md hover:bg-indigo-200 disabled:opacity-50"
          >
            Prepare to apply
          </button>
        </div>

        {/* Internal mode: the guided prompt to run in the Claude terminal. */}
        {mode === "internal" && evalPrompt && (
          <div className="mt-3 rounded-md border border-indigo-200 bg-indigo-50 p-3 text-sm">
            <p className="text-indigo-900 font-medium">Run this in the Internal (Claude) terminal:</p>
            <div className="mt-1.5 flex items-center gap-2">
              <code className="flex-1 px-2 py-1 rounded bg-white border border-indigo-200 text-gray-800">
                {evalPrompt}
              </code>
              <button
                onClick={() =>
                  navigator.clipboard
                    ?.writeText(evalPrompt)
                    .then(() => setCopied(true))
                    .catch(() => {})
                }
                className="px-2 py-1 text-xs font-medium text-indigo-700 bg-white border border-indigo-300 rounded hover:bg-indigo-100"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-1.5 text-xs text-indigo-700">
              {waitingEval
                ? "Waiting for Claude to save the evaluation… it'll appear below."
                : "Switch the assistant to Internal (Claude) and run it — the result appears below."}
            </p>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-auto p-4 bg-gray-50">
        {evaluation && (evaluation.archetype || evaluation.legitimacy_score != null) && (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {evaluation.archetype && (
              <span
                className="px-2 py-0.5 text-xs font-medium rounded-full bg-indigo-100 text-indigo-700"
                title="Role archetype — the working style of this role"
              >
                {evaluation.archetype}
              </span>
            )}
            {evaluation.legitimacy_score != null && (
              <span
                className={`px-2 py-0.5 text-xs font-medium rounded-full ${legitimacyClass(evaluation.legitimacy_score)}`}
                title="Posting legitimacy — higher means less likely a ghost job"
              >
                legitimacy {evaluation.legitimacy_score.toFixed(2)}
              </span>
            )}
            {evaluation.legitimacy_flags?.map((f) => (
              <span
                key={f}
                className="px-2 py-0.5 text-xs rounded-full border border-rose-200 bg-rose-50 text-rose-600"
              >
                ⚠ {f}
              </span>
            ))}
          </div>
        )}
        <JobMarkdown md={markdown} />
      </div>

      <div className="p-4 border-t border-gray-200 bg-gray-50">
        {applied ? (
          <p className="text-sm text-center font-medium text-blue-700">
            ✓ Applied — tracked in the Applications tab.
          </p>
        ) : applyUrl ? (
          <div className="flex gap-2">
            <a
              href={applyUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 text-center px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
            >
              Apply on company site ↗
            </a>
            <button
              onClick={markApplied}
              disabled={busy}
              className="px-4 py-2 text-sm font-semibold text-indigo-700 bg-white border border-indigo-300 rounded-md hover:bg-indigo-50 disabled:opacity-50"
            >
              I applied ✓
            </button>
          </div>
        ) : (
          <p className="text-xs text-center text-gray-500">
            Review strengths, weaknesses &amp; materials above, then click <b>Prepare to apply</b> to unlock the
            Apply link.
          </p>
        )}
      </div>
    </div>
  );
}

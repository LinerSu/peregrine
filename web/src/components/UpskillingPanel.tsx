import { useEffect, useRef, useState } from "react";
import { api, type Job } from "../api";
import type { AssistantMode } from "../App";

interface Gap {
  skill: string;
  why: string;
  how_to_close: string;
}

// Upskilling: pick a job, see the skill gaps vs. your profile.
//   External — the API runs the analysis on click.
//   Internal — you run one line in the Claude terminal; this panel shows the
//   prompt and polls for the result Claude saves, so the outcome is identical.
export default function UpskillingPanel({ jobs, mode }: { jobs: Job[]; mode: AssistantMode }) {
  const [jobId, setJobId] = useState("");
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState("");
  const [gaps, setGaps] = useState<Gap[] | null>(null);
  const [prompt, setPrompt] = useState(""); // Internal: the line to run
  const [waiting, setWaiting] = useState(false); // Internal: polling for Claude's save
  const [copied, setCopied] = useState(false);
  const baseline = useRef(""); // signature of the saved result before the run

  const show = (r: { summary?: string; missing_skills?: Gap[] } | null) => {
    setSummary(r?.summary ?? "");
    setGaps(r?.missing_skills ?? null);
  };

  // Load any previously-saved analysis when the selected job changes.
  useEffect(() => {
    setPrompt("");
    setWaiting(false);
    show(null); // clear the previous job's result first, so an error leaves it cleared
    if (!jobId) return;
    let live = true;
    api
      .getUpskilling(jobId)
      .then((r) => live && show(r && Object.keys(r).length ? r : null))
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [jobId]);

  // Internal: poll until Claude saves a result that differs from the baseline.
  useEffect(() => {
    if (!waiting || !jobId) return;
    const started = Date.now();
    let inFlight = false; // don't let a slow request overlap the next tick
    const id = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const r = await api.getUpskilling(jobId).catch(() => null);
        const sig = r ? JSON.stringify(r) : "";
        if (sig && sig !== baseline.current && (r?.missing_skills || r?.summary)) {
          show(r);
          setWaiting(false);
        } else if (Date.now() - started > 180_000) {
          setWaiting(false); // give up after 3 min
        }
      } finally {
        inFlight = false;
      }
    }, 3000);
    return () => clearInterval(id);
  }, [waiting, jobId]);

  const analyze = async () => {
    if (!jobId || busy) return;
    if (mode === "internal") {
      if (waiting) return; // already waiting on a save — don't reset the baseline mid-poll
      const current = await api.getUpskilling(jobId).catch(() => null);
      baseline.current = current ? JSON.stringify(current) : "";
      setPrompt(`analyze skill gaps for ${jobId}`);
      setCopied(false);
      setWaiting(true);
      return;
    }
    setBusy(true);
    try {
      show(await api.upskilling(jobId));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full overflow-auto p-5">
      <div className="max-w-2xl mx-auto space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">Upskilling</h3>
          <p className="text-sm text-gray-500">
            Compare a job's requirements against your profile to see what to learn next.
          </p>
        </div>

        <div className="flex gap-2">
          <select
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md bg-white"
          >
            <option value="">Select a job…</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.company} — {j.position}
              </option>
            ))}
          </select>
          <button
            onClick={analyze}
            disabled={busy || !jobId}
            className="px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Analyzing…" : "Analyze gaps"}
          </button>
        </div>

        {jobs.length === 0 && (
          <p className="text-sm text-gray-400">No jobs yet — scan or ingest one first.</p>
        )}

        {/* Internal mode: the guided prompt to run in the Claude terminal. */}
        {mode === "internal" && prompt && (
          <div className="rounded-md border border-indigo-200 bg-indigo-50 p-3 text-sm">
            <p className="text-indigo-900 font-medium">Run this in the Internal (Claude) terminal:</p>
            <div className="mt-1.5 flex items-center gap-2">
              <code className="flex-1 px-2 py-1 rounded bg-white border border-indigo-200 text-gray-800">
                {prompt}
              </code>
              <button
                onClick={() =>
                  navigator.clipboard
                    ?.writeText(prompt)
                    .then(() => setCopied(true))
                    .catch(() => {})
                }
                className="px-2 py-1 text-xs font-medium text-indigo-700 bg-white border border-indigo-300 rounded hover:bg-indigo-100"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-1.5 text-xs text-indigo-700">
              {waiting
                ? "Waiting for Claude to save the analysis… it'll appear below."
                : "Switch the assistant to Internal (Claude) and run it — the result appears below."}
            </p>
          </div>
        )}

        {summary && <p className="text-sm text-gray-700 bg-gray-50 rounded-md p-3">{summary}</p>}

        {gaps && (
          <div className="space-y-2">
            {gaps.length === 0 && (
              <p className="text-sm text-green-700">No notable gaps — you're well matched. 🎯</p>
            )}
            {gaps.map((g, i) => (
              <div
                key={i}
                className="rounded-md border border-gray-200 border-l-4 border-l-amber-400 bg-white p-3 shadow-sm"
              >
                <div className="text-sm font-semibold text-gray-800">{g.skill}</div>
                <div className="text-sm text-gray-600 mt-0.5">{g.why}</div>
                <div className="text-sm text-indigo-700 mt-1">→ {g.how_to_close}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

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
  const [coverLetter, setCoverLetter] = useState<string | null>(null);
  const [coverPrompt, setCoverPrompt] = useState(""); // Internal: the line to run
  const [waitingCover, setWaitingCover] = useState(false);
  const [coverPromptCopied, setCoverPromptCopied] = useState(false);
  const [coverTextCopied, setCoverTextCopied] = useState(false);
  const [coverError, setCoverError] = useState("");
  const [cvTex, setCvTex] = useState<string | null>(null);
  const [cvPdf, setCvPdf] = useState(false);
  const [cvTexPrompt, setCvTexPrompt] = useState(""); // Internal: the line to run
  const [waitingCvTex, setWaitingCvTex] = useState(false);
  const [cvTexPromptCopied, setCvTexPromptCopied] = useState(false);
  const [cvTexCopied, setCvTexCopied] = useState(false);
  const [cvError, setCvError] = useState("");
  const baseline = useRef(""); // job markdown before the run
  const coverBaseline = useRef<string | null>(null); // cover letter before the run
  const cvTexBaseline = useRef<string | null>(null); // tailored CV before the run

  // Empty {} from the API (no evaluation yet) -> null.
  const normEval = (ev: Evaluation | null) => (ev && Object.keys(ev).length ? ev : null);

  // Fetch job + evaluation in parallel. `isLive` lets the mount effect drop a
  // stale response if jobId changed while the requests were in flight.
  const load = async (isLive: () => boolean = () => true) => {
    const [{ job, markdown }, ev, cover, cv] = await Promise.all([
      api.getJob(jobId),
      api.getEvaluation(jobId).catch(() => null),
      api.getCoverLetter(jobId).catch(() => null),
      api.getCv(jobId).catch(() => null),
    ]);
    if (!isLive()) return;
    setJob(job);
    setMarkdown(markdown);
    setEvaluation(normEval(ev));
    setCoverLetter(cover?.content ?? null);
    setCoverTextCopied(false); // new/refreshed content -> reset the Copy button
    setCvTex(cv?.tex ?? null);
    setCvPdf(!!cv?.pdf_available);
    setCvTexCopied(false);
  };

  useEffect(() => {
    setApplyUrl(null);
    setEvalPrompt("");
    setWaitingEval(false);
    setEvaluation(null);
    setCoverPrompt("");
    setWaitingCover(false);
    setCoverLetter(null);
    setCoverError("");
    setCoverPromptCopied(false);
    setCoverTextCopied(false);
    setCvTex(null);
    setCvPdf(false);
    setCvTexPrompt("");
    setWaitingCvTex(false);
    setCvTexPromptCopied(false);
    setCvTexCopied(false);
    setCvError("");
    let live = true;
    load(() => live);
    return () => {
      live = false;
    };
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

  // Internal: poll until Claude saves the cover letter (its content changes).
  useEffect(() => {
    if (!waitingCover) return;
    const started = Date.now();
    let inFlight = false;
    let live = true;
    const id = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await api.getCoverLetter(jobId).catch(() => null);
        if (!live) return;
        const content = res?.content ?? null;
        // null = not saved yet; a non-null value (even "") that differs is a save.
        if (content != null && content !== coverBaseline.current) {
          setCoverLetter(content);
          setCoverTextCopied(false);
          setWaitingCover(false);
        } else if (Date.now() - started > 180_000) {
          setWaitingCover(false);
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
  }, [waitingCover, jobId]);

  // Internal: poll until Claude saves the tailored CV (its .tex changes).
  useEffect(() => {
    if (!waitingCvTex) return;
    const started = Date.now();
    let inFlight = false;
    let live = true;
    const id = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await api.getCv(jobId).catch(() => null);
        if (!live) return;
        const tex = res?.tex ?? null;
        if (tex != null && tex !== cvTexBaseline.current) {
          setCvTex(tex);
          setCvPdf(!!res?.pdf_available);
          setCvTexCopied(false);
          setCvTexPrompt("");
          setWaitingCvTex(false);
          return;
        }
        if (Date.now() - started > 180_000) setWaitingCvTex(false);
      } finally {
        inFlight = false;
      }
    }, 3000);
    return () => {
      live = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waitingCvTex, jobId]);

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

  const draftCoverLetter = async () => {
    setCoverError("");
    if (mode === "internal") {
      if (waitingCover) return; // already waiting on a save — don't restart/overlap
      coverBaseline.current = coverLetter;
      setCoverPrompt(`draft a cover letter for ${jobId}`);
      setCoverPromptCopied(false);
      setWaitingCover(true);
      return;
    }
    setBusy(true);
    try {
      const res = await api.generateCoverLetter(jobId);
      setCoverLetter(res.content);
      setCoverTextCopied(false);
    } catch {
      // The cover-letter LLM call is the longest in the app — surface failures.
      setCoverError("Couldn't generate the cover letter. Try again, or use Internal mode.");
    } finally {
      setBusy(false);
    }
  };

  const tailorCv = async () => {
    setCvError("");
    if (mode === "internal") {
      if (waitingCvTex) return; // already waiting on a save — don't restart/overlap
      cvTexBaseline.current = cvTex;
      setCvTexPrompt(`tailor my cv for ${jobId}`);
      setCvTexPromptCopied(false);
      setWaitingCvTex(true);
      return;
    }
    setBusy(true);
    try {
      const res = await api.generateCv(jobId);
      setCvTex(res.tex);
      setCvPdf(res.pdf_available);
      setCvTexCopied(false);
    } catch {
      setCvError("Couldn't generate the tailored CV. Try again, or use Internal mode.");
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
          <button
            onClick={draftCoverLetter}
            disabled={busy || waitingCover}
            className="px-3 py-1.5 text-sm font-medium text-purple-700 bg-purple-100 rounded-md hover:bg-purple-200 disabled:opacity-50"
          >
            {busy ? "Working…" : waitingCover ? "Waiting…" : coverLetter != null ? "Redraft cover letter" : "Cover letter"}
          </button>
          <button
            onClick={tailorCv}
            disabled={busy || waitingCvTex}
            className="px-3 py-1.5 text-sm font-medium text-teal-700 bg-teal-100 rounded-md hover:bg-teal-200 disabled:opacity-50"
          >
            {busy ? "Working…" : waitingCvTex ? "Waiting…" : cvTex != null ? "Re-tailor CV" : "Tailor CV"}
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

        {/* Internal mode: the guided prompt to draft the cover letter. */}
        {mode === "internal" && coverPrompt && (
          <div className="mt-3 rounded-md border border-purple-200 bg-purple-50 p-3 text-sm">
            <p className="text-purple-900 font-medium">Run this in the Internal (Claude) terminal:</p>
            <div className="mt-1.5 flex items-center gap-2">
              <code className="flex-1 px-2 py-1 rounded bg-white border border-purple-200 text-gray-800">
                {coverPrompt}
              </code>
              <button
                onClick={() =>
                  navigator.clipboard
                    ?.writeText(coverPrompt)
                    .then(() => setCoverPromptCopied(true))
                    .catch(() => {})
                }
                className="px-2 py-1 text-xs font-medium text-purple-700 bg-white border border-purple-300 rounded hover:bg-purple-100"
              >
                {coverPromptCopied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-1.5 text-xs text-purple-700">
              {waitingCover
                ? "Waiting for Claude to save the cover letter… it'll appear below."
                : "Switch the assistant to Internal (Claude) and run it — the draft appears below."}
            </p>
          </div>
        )}

        {coverError && <p className="mt-3 text-sm text-rose-600">{coverError}</p>}

        {/* Internal mode: the guided prompt to tailor the CV. */}
        {mode === "internal" && cvTexPrompt && (
          <div className="mt-3 rounded-md border border-teal-200 bg-teal-50 p-3 text-sm">
            <p className="text-teal-900 font-medium">Run this in the Internal (Claude) terminal:</p>
            <div className="mt-1.5 flex items-center gap-2">
              <code className="flex-1 px-2 py-1 rounded bg-white border border-teal-200 text-gray-800">
                {cvTexPrompt}
              </code>
              <button
                onClick={() =>
                  navigator.clipboard
                    ?.writeText(cvTexPrompt)
                    .then(() => setCvTexPromptCopied(true))
                    .catch(() => {})
                }
                className="px-2 py-1 text-xs font-medium text-teal-700 bg-white border border-teal-300 rounded hover:bg-teal-100"
              >
                {cvTexPromptCopied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="mt-1.5 text-xs text-teal-700">
              {waitingCvTex
                ? "Waiting for Claude to save the tailored CV…"
                : "Run it in the Claude terminal — the CV (and a PDF) appear below."}
            </p>
          </div>
        )}
        {cvError && <p className="mt-3 text-sm text-rose-600">{cvError}</p>}
      </div>

      <div className="flex-1 overflow-auto p-4 bg-gray-50">
        {evaluation &&
          (evaluation.archetype ||
            Number.isFinite(evaluation.legitimacy_score) ||
            evaluation.legitimacy_flags?.length) && (
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {evaluation.archetype && (
              <span
                className="px-2 py-0.5 text-xs font-medium rounded-full bg-indigo-100 text-indigo-700"
                title="Role archetype — the working style of this role"
              >
                {evaluation.archetype}
              </span>
            )}
            {Number.isFinite(evaluation.legitimacy_score) && (
              <span
                className={`px-2 py-0.5 text-xs font-medium rounded-full ${legitimacyClass(evaluation.legitimacy_score)}`}
                title="Posting legitimacy — higher means less likely a ghost job"
              >
                legitimacy {evaluation.legitimacy_score!.toFixed(2)}
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

        {coverLetter != null && (
          <div className="mt-4 rounded-lg border border-purple-200 bg-white">
            <div className="flex items-center justify-between border-b border-purple-100 px-3 py-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-purple-700">
                Cover letter
              </h4>
              <button
                onClick={() =>
                  navigator.clipboard
                    ?.writeText(coverLetter)
                    .then(() => setCoverTextCopied(true))
                    .catch(() => {})
                }
                className="px-2 py-0.5 text-xs font-medium text-purple-700 border border-purple-300 rounded hover:bg-purple-50"
              >
                {coverTextCopied ? "Copied" : "Copy"}
              </button>
            </div>
            <pre className="whitespace-pre-wrap px-3 py-3 text-sm text-gray-800 font-sans">{coverLetter}</pre>
          </div>
        )}

        {cvTex != null && (
          <div className="mt-4 rounded-lg border border-teal-200 bg-white">
            <div className="flex items-center justify-between border-b border-teal-100 px-3 py-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-teal-700">
                Tailored CV (LaTeX)
              </h4>
              <div className="flex items-center gap-2">
                {cvPdf && (
                  <a
                    href={api.cvPdfUrl(jobId)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2 py-0.5 text-xs font-medium text-white bg-teal-600 rounded hover:bg-teal-700"
                  >
                    Download PDF ↓
                  </a>
                )}
                <button
                  onClick={() =>
                    navigator.clipboard
                      ?.writeText(cvTex)
                      .then(() => setCvTexCopied(true))
                      .catch(() => {})
                  }
                  className="px-2 py-0.5 text-xs font-medium text-teal-700 border border-teal-300 rounded hover:bg-teal-50"
                >
                  {cvTexCopied ? "Copied" : "Copy .tex"}
                </button>
              </div>
            </div>
            <pre className="whitespace-pre-wrap px-3 py-3 text-xs text-gray-700 font-mono max-h-80 overflow-auto">
              {cvTex}
            </pre>
            {!cvPdf && (
              <p className="px-3 pb-2 text-xs text-gray-400">
                PDF not compiled here (no LaTeX engine) — copy the .tex and compile it locally.
              </p>
            )}
          </div>
        )}
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

import { useEffect, useRef, useState } from "react";
import { api, type Evaluation, type Job } from "../api";
import type { AssistantMode } from "../App";
import { fitClass, legitimacyClass, relativeTime, safeHttpUrl, salaryRange, statusClass } from "../format";
import JobMarkdown from "./JobMarkdown";
import ContactsEditor from "./ContactsEditor";

// One line of the Internal-mode prompt strip: the command to copy into the Claude
// terminal + its per-action copied state and waiting indicator. Accent classes are
// written out literally per color so Tailwind's scanner keeps them.
const PROMPT_ACCENTS = {
  indigo: {
    code: "border-indigo-200",
    btn: "text-indigo-700 border-indigo-300 hover:bg-indigo-50",
  },
  purple: {
    code: "border-purple-200",
    btn: "text-purple-700 border-purple-300 hover:bg-purple-50",
  },
  teal: {
    code: "border-teal-200",
    btn: "text-teal-700 border-teal-300 hover:bg-teal-50",
  },
} as const;

function PromptLine({
  prompt,
  copied,
  onCopied,
  waiting,
  waitingText,
  accent,
}: {
  prompt: string;
  copied: boolean;
  onCopied: () => void;
  waiting: boolean;
  waitingText: string;
  accent: keyof typeof PROMPT_ACCENTS;
}) {
  const a = PROMPT_ACCENTS[accent];
  return (
    <div className="flex items-center gap-2">
      <code className={`flex-1 px-2 py-1 rounded bg-white border ${a.code} text-xs text-gray-800`}>
        {prompt}
      </code>
      <button
        onClick={() => navigator.clipboard?.writeText(prompt).then(onCopied).catch(() => {})}
        className={`px-2 py-1 text-xs font-medium bg-white border rounded ${a.btn}`}
      >
        {copied ? "Copied" : "Copy"}
      </button>
      {waiting && (
        <span className="text-xs text-gray-400 animate-pulse" title={waitingText}>
          waiting…
        </span>
      )}
    </div>
  );
}

// Job detail with the human-in-the-loop apply gate. "Evaluate fit" is mode-aware:
//   External — the API runs the evaluation on click.
//   Internal — you run one line in the Claude terminal; this panel polls for the
//   evaluation Claude saves (fit score + "Agent evaluation" section) and reloads.
export default function JobDetail({
  jobId,
  onChanged,
  onDeleted,
  onNavigateProfile,
  mode,
}: {
  jobId: string;
  onChanged: () => void;
  onDeleted: () => void; // clear the selection — this job no longer exists
  onNavigateProfile: () => void; // "Update profile" in the qualification-match card
  mode: AssistantMode;
}) {
  const [job, setJob] = useState<Job | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [appStatus, setAppStatus] = useState("");  // linked application's status ("" = none)
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
  const [starBusy, setStarBusy] = useState(false); // in-flight guard for the star PATCH
  const [coverStale, setCoverStale] = useState(false); // drafted against a previous CV
  const [showStaleCover, setShowStaleCover] = useState(false);
  const baseline = useRef(""); // job markdown before the run
  const coverBaseline = useRef<string | null>(null); // cover letter before the run
  const cvTexBaseline = useRef<string | null>(null); // tailored CV before the run
  const gateRef = useRef<HTMLDivElement>(null); // the apply gate lives at the END of the scroll now

  // Empty {} from the API (no evaluation yet) -> null.
  const normEval = (ev: Evaluation | null) => (ev && Object.keys(ev).length ? ev : null);

  // Fetch job + evaluation in parallel. `isLive` lets the mount effect drop a
  // stale response if jobId changed while the requests were in flight.
  const load = async (isLive: () => boolean = () => true) => {
    const [{ job, markdown, application_status }, ev, cover, cv] = await Promise.all([
      api.getJob(jobId),
      api.getEvaluation(jobId).catch(() => null),
      api.getCoverLetter(jobId).catch(() => null),
      api.getCv(jobId).catch(() => null),
    ]);
    if (!isLive()) return;
    setJob(job);
    setAppStatus(application_status ?? "");
    setMarkdown(markdown);
    setEvaluation(normEval(ev));
    setCoverLetter(cover?.content ?? null);
    setCoverStale(!!cover?.stale);
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
    setCoverStale(false); // per-job — must not leak the previous job's stale state
    setShowStaleCover(false); // nor its "show anyway" bypass
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
          setCoverStale(false); // freshly saved -> current by definition
          setShowStaleCover(false);
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
        const snap = JSON.stringify({ tex, pdf: !!res?.pdf_available });
        if (tex != null && snap !== cvTexBaseline.current) {
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
      // Freshly drafted -> current by definition; without this the new letter stays
      // hidden behind the stale banner (mode-contract: Internal's poll clears these
      // on save, External must too).
      setCoverStale(false);
      setShowStaleCover(false);
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
      // snapshot both .tex and pdf so a PDF flip on an unchanged .tex still resolves
      cvTexBaseline.current = JSON.stringify({ tex: cvTex, pdf: cvPdf });
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
      // The gate lives at the END of the scroll now — bring it into view so the
      // unlocked Apply link is never a mystery below the fold.
      requestAnimationFrame(() =>
        gateRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" })
      );
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

  const deleteThisJob = async () => {
    if (
      !window.confirm(
        `Delete "${job?.position ?? jobId}" and all its generated materials? This cannot be undone.`
      )
    )
      return;
    setBusy(true);
    try {
      await api.deleteJob(jobId);
      onChanged();
      onDeleted();
    } catch (e) {
      // Most common reason: a linked application exists (the API refuses with 409).
      window.alert(e instanceof Error ? e.message : "Couldn't delete this job.");
    } finally {
      setBusy(false);
    }
  };

  if (!job) return <div className="p-6 text-gray-400">Loading…</div>;

  // "Have I applied?" is answered by whether an application is LINKED to this posting —
  // not by the job's status word, which is ambiguous: "closed" is a dead posting when
  // nothing is linked and a closed application when something is. The status list is the
  // fallback for a job whose status was set by hand without a tracker row, and it covers
  // every post-application status: "interviewing" contradicted "Prepare to apply" too.
  const applied = !!appStatus || ["applied", "interviewing", "offer", "rejected"].includes(job.status);
  // Analysis built against a PREVIOUS CV is hidden, not shown as current (fit score,
  // strengths/weaknesses section, archetype/legitimacy chips) — a banner points at
  // re-running. Tailored CVs are deliberately untouched (their story is still open).
  const evalStale = evaluation?.stale === true;
  const skillFit = job.skill_fit;
  const hasSkillFit = !!skillFit && skillFit.have.length + skillFit.missing.length > 0;
  const postedAgo = relativeTime(job.posted_date);
  const metaLine = [postedAgo && `Posted ${postedAgo}`, job.close_date && `Apply by ${job.close_date}`]
    .filter(Boolean)
    .join(" · ");
  const salary = salaryRange(job.salary_min, job.salary_max, job.currency);
  const people: unknown[] = (() => {
    try {
      const p = JSON.parse(job.people || "[]");
      return Array.isArray(p) ? p : [];
    } catch {
      return [];
    }
  })();
  const postingHref = safeHttpUrl(job.url); // never render a non-http(s) scheme as a link
  const toggleStar = async () => {
    if (starBusy) return; // two rapid clicks would race their PATCHes out of order
    const next = !job.starred;
    setStarBusy(true);
    setJob({ ...job, starred: next }); // optimistic — reverted below if the PATCH fails
    try {
      await api.updateJob(job.id, { starred: next });
      onChanged();
    } catch {
      setJob((j) => (j ? { ...j, starred: !next } : j));
    } finally {
      setStarBusy(false);
    }
  };

  return (
    // ONE scroll container — the old fixed header could grow unbounded (chips +
    // contacts + buttons + prompt cards) and crush the markdown body on short
    // viewports, and the old fixed footer reserved ~52px for a mostly-empty hint.
    <div className="h-full overflow-auto">
      <div className="p-4 bg-white border-b border-gray-200">
        <div className="flex items-baseline gap-2">
          <h2 className="flex-1 text-lg font-semibold">{job.position}</h2>
          {/* The job id: what the terminal commands take ("evaluate fit for 2026-001") and
              what tells two same-title postings apart in the application picker. It was
              addressable everywhere except on screen. */}
          <span title="Job id — use it in Claude-terminal commands" className="text-xs font-mono text-gray-400">
            {job.id}
          </span>
        </div>
        <p className="text-sm text-gray-500">
          {[job.company, job.location || null].filter(Boolean).join(" · ")}
        </p>
        {metaLine && <p className="mt-0.5 text-xs text-gray-400">{metaLine}</p>}

        {/* Action row: bookmark + the posting itself first (reference layout), then
            the AI actions. "View posting" is just the source link — the APPLY gate
            (Prepare → review → Apply) is unchanged, at the end of the page. */}
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <button
            onClick={toggleStar}
            title={job.starred ? "Unstar" : "Star this job"}
            className={`px-2.5 py-1.5 text-sm rounded-md border ${
              job.starred
                ? "border-amber-400 bg-amber-50 text-amber-600"
                : "border-gray-300 text-gray-400 hover:text-amber-600"
            }`}
          >
            {job.starred ? "★" : "☆"}
          </button>
          {postingHref && (
            <a
              href={postingHref}
              target="_blank"
              rel="noopener noreferrer"
              title="Open the original posting (viewing ≠ applying — the apply gate is below)"
              className="px-3 py-1.5 text-sm font-medium text-gray-700 border border-gray-300 rounded-md hover:bg-gray-50"
            >
              View posting ↗
            </a>
          )}
          <button
            onClick={evaluate}
            disabled={busy || waitingEval}
            className="px-3 py-1.5 text-sm font-medium text-white bg-emerald-600 rounded-md hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? "Working…" : waitingEval ? "Waiting…" : "Evaluate fit"}
          </button>
          {!applied && (
            <button
              onClick={prepare}
              disabled={busy}
              className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-100 rounded-md hover:bg-indigo-200 disabled:opacity-50"
            >
              Prepare to apply
            </button>
          )}
          <button
            onClick={draftCoverLetter}
            disabled={busy || waitingCover}
            className="px-2.5 py-1.5 text-xs font-medium text-purple-700 bg-purple-50 border border-purple-200 rounded-md hover:bg-purple-100 disabled:opacity-50"
          >
            {busy ? "Working…" : waitingCover ? "Waiting…" : coverLetter != null ? "Redraft cover letter" : "Cover letter"}
          </button>
          <button
            onClick={tailorCv}
            disabled={busy || waitingCvTex}
            className="px-2.5 py-1.5 text-xs font-medium text-teal-700 bg-teal-50 border border-teal-200 rounded-md hover:bg-teal-100 disabled:opacity-50"
          >
            {busy ? "Working…" : waitingCvTex ? "Waiting…" : cvTex != null ? "Re-tailor CV" : "Tailor CV"}
          </button>
          <button
            onClick={deleteThisJob}
            disabled={busy}
            title="Delete this job and its generated materials (refused while a linked application exists)"
            className="ml-auto px-2.5 py-1.5 text-xs font-medium text-rose-600 border border-rose-200 rounded-md hover:bg-rose-50 disabled:opacity-50"
          >
            Delete
          </button>
        </div>

        {/* Internal mode: ONE compact strip for the guided prompts (was three ~90px
            cards that pushed the posting content off-screen). */}
        {mode === "internal" && (evalPrompt || coverPrompt || cvTexPrompt) && (
          <div className="mt-3 rounded-md border border-gray-200 bg-gray-50 p-2.5 space-y-1.5">
            <p className="text-xs font-medium text-gray-600">
              Run in the Internal (Claude) terminal — results appear below when saved:
            </p>
            {evalPrompt && (
              <PromptLine
                prompt={evalPrompt}
                copied={copied}
                onCopied={() => setCopied(true)}
                waiting={waitingEval}
                waitingText="Waiting for Claude to save the evaluation…"
                accent="indigo"
              />
            )}
            {coverPrompt && (
              <PromptLine
                prompt={coverPrompt}
                copied={coverPromptCopied}
                onCopied={() => setCoverPromptCopied(true)}
                waiting={waitingCover}
                waitingText="Waiting for Claude to save the cover letter…"
                accent="purple"
              />
            )}
            {cvTexPrompt && (
              <PromptLine
                prompt={cvTexPrompt}
                copied={cvTexPromptCopied}
                onCopied={() => setCvTexPromptCopied(true)}
                waiting={waitingCvTex}
                waitingText="Waiting for Claude to save the tailored CV…"
                accent="teal"
              />
            )}
          </div>
        )}
        {coverError && <p className="mt-2 text-sm text-rose-600">{coverError}</p>}
        {cvError && <p className="mt-2 text-sm text-rose-600">{cvError}</p>}

        {/* At a glance — the facts the old layout never showed (salary, flexibility,
            deadline lives in the meta line) plus status + fit at a glance. */}
        <div className="flex flex-wrap items-center gap-1.5 mt-3">
          {salary !== "—" && (
            <span className="px-2 py-0.5 text-xs rounded-full bg-emerald-50 text-emerald-800" title="Salary range from the posting">
              {salary}
            </span>
          )}
          {job.flexibility && (
            <span className="px-2 py-0.5 text-xs rounded-full bg-sky-50 text-sky-700" title="Work arrangement">
              {job.flexibility}
            </span>
          )}
          {job.level && (
            <span className="px-2 py-0.5 text-xs rounded-full bg-amber-100 text-amber-800" title="Required degree">
              🎓 {job.level}
            </span>
          )}
          {job.role_category && job.role_category !== "Other" && (
            <span className="px-2 py-0.5 text-xs rounded-full bg-gray-100 text-gray-700" title="Role family">
              {job.role_category}
            </span>
          )}
          <span className={`px-2 py-0.5 text-xs rounded-full ${statusClass(job.status)}`} title="Tracking status">
            {job.status}
          </span>
          {job.fit_score != null && !evalStale && (
            <span className={`px-2 py-0.5 text-xs rounded-full ${fitClass(job.fit_score)}`} title="LLM fit score">
              fit {job.fit_score.toFixed(2)}
            </span>
          )}
        </div>

        {/* Structured tags pulled from the posting: domains (+ required skills only
            when there's no skill_fit — with it, the "What they're looking for" card
            below owns the skills story). Role + degree live in the glance row. */}
        {(job.domains || (!hasSkillFit && job.req_skills)) && (
          <div className="flex flex-wrap items-center gap-1.5 mt-2">
            {(job.domains || "").split(",").map((d) => d.trim()).filter(Boolean).map((d) => (
              <span key={`d-${d}`} className="px-2 py-0.5 text-xs rounded-full bg-indigo-50 text-indigo-700" title="Field / domain">
                {d}
              </span>
            ))}
            {!hasSkillFit &&
              (job.req_skills || "").split(",").map((s) => s.trim()).filter(Boolean).map((s) => (
                <span key={`s-${s}`} className="px-2 py-0.5 text-xs rounded-full bg-emerald-50 text-emerald-700" title="Required skill">
                  {s}
                </span>
              ))}
          </div>
        )}

        {/* People — recruiter / hiring manager you found yourself (user-entered, never
            scraped). The bordered band only appears when there ARE people; empty state
            is ContactsEditor's own one-line "+ add people" link. */}
        <div className={people.length ? "mt-3 border-t border-gray-100 pt-2" : "mt-2"}>
          <ContactsEditor
            key={`${job.id}:${job.people}`}
            value={job}
            onSave={async (f) => {
              await api.updateJob(job.id, f);
              onChanged();
            }}
          />
        </div>
      </div>

      <div className="p-4 bg-gray-50">
        {/* Qualification match — the cheap no-LLM signal, front and center (reference
            layout's "What they're looking for"). Always current: recomputed from the
            live profile on every request, so it needs no staleness handling. */}
        {hasSkillFit && skillFit && (
          <div className="mb-4 rounded-lg border border-gray-200 bg-white p-4">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-gray-500 mb-1.5">
              What they're looking for
            </h4>
            <p className="text-sm font-medium text-gray-800">
              {skillFit.missing.length === 0
                ? `You match all ${skillFit.have.length} required skill${skillFit.have.length === 1 ? "" : "s"}. Nice!`
                : skillFit.have.length === 0
                ? `None of the ${skillFit.missing.length} required skills are in your profile yet`
                : `You match ${skillFit.have.length} of ${skillFit.have.length + skillFit.missing.length} required skills`}
            </p>
            <div className="flex flex-wrap items-center gap-1.5 mt-2">
              {skillFit.have.map((s) => (
                <span key={`h-${s}`} className="px-2 py-0.5 text-xs rounded-full bg-emerald-100 text-emerald-700" title="Required — in your profile">
                  ✓ {s}
                </span>
              ))}
              {skillFit.missing.map((s) => (
                <span key={`m-${s}`} className="px-2 py-0.5 text-xs rounded-full border border-gray-300 text-gray-500 bg-white" title="Required — not in your profile">
                  ✗ {s}
                </span>
              ))}
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Matching is based on your profile.{" "}
              <button onClick={onNavigateProfile} className="text-indigo-600 hover:underline">
                Update profile
              </button>
            </p>
          </div>
        )}

        {/* Analysis from a PREVIOUS CV is hidden, not shown as current (user rule):
            the banner replaces the fit/strengths/weaknesses until re-run. */}
        {evalStale && (
          <div className="mb-4 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            ⚠ The fit evaluation for this job was made with your <b>previous CV</b> and is
            hidden. Click <b>Evaluate fit</b> to re-run it against your current profile.
          </div>
        )}
        {!evalStale &&
          evaluation &&
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
        <JobMarkdown md={markdown} hideSections={evalStale ? ["Agent evaluation"] : []} />

        {coverLetter != null && coverStale && !showStaleCover && (
          <div className="mt-4 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2.5 text-sm text-amber-800">
            ⚠ The cover letter for this job was drafted with your <b>previous CV</b> and is
            hidden. Click <b>Redraft cover letter</b> above — or{" "}
            <button onClick={() => setShowStaleCover(true)} className="underline font-medium">
              show the old draft
            </button>
            .
          </div>
        )}
        {coverLetter != null && (!coverStale || showStaleCover) && (
          <div className="mt-4 rounded-lg border border-purple-200 bg-white">
            <div className="flex items-center justify-between border-b border-purple-100 px-3 py-2">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-purple-700">
                Cover letter{coverStale ? " — from your previous CV" : ""}
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
                No PDF — LaTeX isn't installed here, or the document didn't compile. Copy the .tex
                and compile it locally.
              </p>
            )}
          </div>
        )}

        {/* Apply gate — inline at the end of the review flow (was a permanently
            reserved footer row). Semantics unchanged: the Apply link unlocks only
            after Prepare; prepare() scrolls here. */}
        <div ref={gateRef} className="mt-4 rounded-lg border border-gray-200 bg-white p-4">
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
    </div>
  );
}

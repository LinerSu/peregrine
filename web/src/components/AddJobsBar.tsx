import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import type { AssistantMode } from "../App";
import JobIngestPanel from "./JobIngestPanel";
import AgentPromptModal from "./AgentPromptModal";
import { JOB_AGENT_PROMPT } from "../prompts";

// Job acquisition, separate from the view controls in JobsTable:
//   Scan  — zero-token fetch from configured ATS sources (config/portals.yml).
//   Add   — from a URL, or by pasting / uploading a posting (no fetching) — the
//           reusable JobIngestPanel handles both modes; here it just refreshes.
export default function AddJobsBar({
  mode,
  onChanged,
  unscored = 0,
}: {
  mode: AssistantMode;
  onChanged: () => void;
  unscored?: number;   // open jobs with no CURRENT fit score (the list nulls stale ones)
}) {
  const [open, setOpen] = useState(false);
  const [showAgentPrompt, setShowAgentPrompt] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scanMsg, setScanMsg] = useState("");
  const [sources, setSources] = useState<{ name: string; provider: string }[]>([]);
  const [selected, setSelected] = useState<string[]>([]); // [] = scan all configured companies
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");
  const [helpOpen, setHelpOpen] = useState(false); // "why isn't my company here?" explainer
  const [scoreMsg, setScoreMsg] = useState("");
  const [scorePrompt, setScorePrompt] = useState(false); // Internal: show the command instead
  const [scoreCopied, setScoreCopied] = useState(false);

  // Jobs tracked before auto-evaluate existed — plus any whose evaluation went stale after a
  // CV re-upload — never get scored on their own. Without this the only way to fix that was
  // the Internal terminal, which left External-mode users with no route at all.
  const scoreMissing = async () => {
    if (mode === "internal") {   // metered route: never call it on the user's behalf here
      setScoreMsg("");           // a message from an earlier External click isn't about this
      setScorePrompt(true);
      setScoreCopied(false);
      return;
    }
    setBusy(true);
    setScoreMsg("");
    try {
      const r = await api.evaluateMissing();
      setScoreMsg(
        r.scheduled
          ? `Scoring ${r.scheduled} job${r.scheduled > 1 ? "s" : ""} in the background…` +
            (r.remaining ? ` ${r.remaining} left — click again when these land.` : "")
          : r.reason || "Nothing to score."
      );
      if (r.scheduled) setTimeout(onChanged, 4000);  // scores land in the background
    } catch (e) {
      // The API's own reason is usually the useful part (a guard explaining itself, a
      // config problem). Fall back to the generic hint only for a bare HTTP status.
      const reason = e instanceof Error ? e.message : "";
      setScoreMsg(
        !reason || /^\d{3}\b/.test(reason)
          ? "Couldn't start scoring — is the API running?"
          : reason
      );
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    api.sources().then((r) => setSources(r.companies)).catch(() => {});
  }, []);

  const toggle = (name: string) =>
    setSelected((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));

  // Filtered list for the picker — keeps it usable whether there are 2 companies or 100.
  const pickerList = useMemo(() => {
    const q = pickerQuery.trim().toLowerCase();
    return q ? sources.filter((s) => s.name.toLowerCase().includes(q)) : sources;
  }, [sources, pickerQuery]);

  const scan = async () => {
    setBusy(true);
    setScanMsg("");
    try {
      const r = await api.scan(selected.length ? selected : undefined);
      const tail = `${r.duplicates} dupes · ${r.filtered} filtered`;
      const more = r.capped ? " — stopped at the per-scan safety cap; click Scan again for more." : ".";
      setScanMsg(
        r.new > 0
          ? `Found ${r.new} new (${tail}${r.dead ? ` · ${r.dead} closed` : ""})${more}`
          : r.dead > 0
            ? `Closed ${r.dead} stale (gone or aged out); no new jobs (${tail}).`
            : `No new jobs (${tail}). Add sources in config/portals.yml, or paste/upload a posting below.`
      );
      onChanged();
    } catch {
      setScanMsg("Scan failed — check the API / logs.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-b border-gray-200 bg-white px-2 py-1.5">
      <div className="flex flex-wrap items-center gap-2">
        {sources.length > 1 && (
          <div className="relative flex items-center gap-1.5 text-sm">
            <span className="text-gray-500">Scan:</span>
            <button
              type="button"
              onClick={() => setPickerOpen((v) => !v)}
              disabled={busy}
              aria-expanded={pickerOpen}
              aria-haspopup="true"
              title="Choose which companies to scan (none = all)"
              className="px-2.5 py-1.5 border border-gray-300 rounded-md bg-white hover:bg-gray-50 flex items-center gap-1 disabled:opacity-50"
            >
              {selected.length ? `${selected.length} selected` : "All companies"}
              <span className="text-gray-400">▾</span>
            </button>
            {pickerOpen && (
              <>
                {/* click-outside backdrop */}
                <div className="fixed inset-0 z-10" onClick={() => setPickerOpen(false)} />
                <div className="absolute top-full left-0 z-20 mt-1 w-72 max-h-80 flex flex-col rounded-md border border-gray-200 bg-white shadow-lg">
                  <div className="p-2 border-b border-gray-100">
                    <input
                      autoFocus
                      value={pickerQuery}
                      onChange={(e) => setPickerQuery(e.target.value)}
                      placeholder="Filter companies…"
                      className="w-full px-2 py-1 text-sm border border-gray-300 rounded-md"
                    />
                    <div className="flex items-center gap-3 mt-1.5 px-1 text-xs">
                      <button type="button" disabled={busy} className="text-indigo-600 hover:underline disabled:opacity-50"
                        onClick={() => setSelected(sources.map((s) => s.name))}>
                        Select all
                      </button>
                      <button type="button" disabled={busy} className="text-gray-500 hover:underline disabled:opacity-50"
                        onClick={() => setSelected([])}>
                        Clear
                      </button>
                      <span className="ml-auto text-gray-400">
                        {selected.length ? `${selected.length} selected` : "all"}
                      </span>
                    </div>
                  </div>
                  <div className="overflow-y-auto p-1">
                    {pickerList.map((s) => (
                      <label
                        key={s.name}
                        className="flex items-center gap-2 px-2 py-1 rounded hover:bg-gray-50 cursor-pointer"
                      >
                        <input
                          type="checkbox"
                          checked={selected.includes(s.name)}
                          disabled={busy}
                          onChange={() => toggle(s.name)}
                        />
                        <span className="flex-1 truncate">{s.name}</span>
                        <span className="text-[11px] text-gray-400">{s.provider}</span>
                      </label>
                    ))}
                    {!pickerList.length && (
                      <p className="px-2 py-2 text-xs text-gray-500">
                        No matches. Companies on Workday or their own careers sites (Meta, Google,
                        Microsoft, Nvidia…) aren't scannable — close this and use{" "}
                        <button
                          type="button"
                          className="text-indigo-600 hover:underline"
                          onClick={() => {
                            setPickerOpen(false);
                            setOpen(true);
                          }}
                        >
                          Add a job
                        </button>{" "}
                        to paste that posting.
                      </p>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        )}
        <button
          type="button"
          onClick={scan}
          disabled={busy}
          className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Working…" : selected.length ? `Scan ${selected.length} selected` : "Scan all"}
        </button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md hover:bg-indigo-100"
        >
          {open ? "Add a job ▴" : "Add a job ▾"}
        </button>
        <button
          type="button"
          onClick={() => setShowAgentPrompt(true)}
          title="Get a prompt for another AI agent that produces a posting markdown this app can ingest"
          className="px-2 py-1.5 text-xs font-medium text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
        >
          🤖 Agent prompt
        </button>
        <button
          type="button"
          onClick={() => setHelpOpen((v) => !v)}
          aria-expanded={helpOpen}
          className="text-xs text-gray-400 hover:text-gray-600 hover:underline"
        >
          Why these companies?
        </button>
        {unscored > 0 && (
          <button
            type="button"
            onClick={scoreMissing}
            disabled={busy}
            title={`${unscored} open job${unscored > 1 ? "s have" : " has"} no current fit score`}
            className="px-2 py-1.5 text-xs font-medium text-emerald-700 bg-emerald-50 border border-emerald-200 rounded-md hover:bg-emerald-100 disabled:opacity-50"
          >
            Score {unscored} unscored
          </button>
        )}
        {scanMsg && <span className="text-xs text-gray-500">{scanMsg}</span>}
        {scoreMsg && <span className="text-xs text-gray-500">{scoreMsg}</span>}
      </div>

      {mode === "internal" && scorePrompt && (
        <div className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-sm">
          <div className="flex items-center gap-2">
            <code className="flex-1 px-2 py-1 rounded bg-white border border-emerald-200 text-gray-800">
              evaluate all jobs missing a fit score
            </code>
            <button
              type="button"
              onClick={() =>
                navigator.clipboard
                  ?.writeText("evaluate all jobs missing a fit score")
                  .then(() => setScoreCopied(true))
                  .catch(() => {})
              }
              className="px-2 py-1 text-xs font-medium text-emerald-700 bg-white border border-emerald-300 rounded hover:bg-emerald-100"
            >
              {scoreCopied ? "Copied" : "Copy"}
            </button>
            <button
              type="button"
              onClick={() => setScorePrompt(false)}
              className="px-1.5 py-1 text-xs text-emerald-700 hover:bg-emerald-100 rounded"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
          <p className="mt-1 text-xs text-emerald-700">
            Run it in the Claude terminal — Internal mode scores on your machine, so the app
            doesn't spend an API key on your behalf. Refresh when it finishes.
          </p>
        </div>
      )}

      {helpOpen && (
        <div className="mt-2 rounded-md border border-gray-200 bg-gray-50 p-3 text-xs text-gray-600 space-y-1.5">
          <p>
            Scan only lists companies on <strong>supported, scrape-permissive ATS feeds</strong>{" "}
            (Greenhouse, Ashby, Lever, Recruitee, Workable, and Amazon's job search).
          </p>
          <p>
            Big employers on <strong>Workday or their own careers sites</strong> (Google, Microsoft,
            Meta, Nvidia, Intel, IBM…) aren't here: their terms restrict automated access, and we
            won't risk getting your IP banned. <strong>Meta / LinkedIn / Indeed / Glassdoor</strong>{" "}
            are blocked outright by policy.
          </p>
          <p>
            To track a job from <em>any</em> company —{" "}
            <button
              type="button"
              className="text-indigo-600 hover:underline"
              onClick={() => {
                setHelpOpen(false);
                setOpen(true);
              }}
            >
              Add a job
            </button>{" "}
            → paste its URL, or paste / upload the description (works for bot-blocking sites too).
          </p>
        </div>
      )}

      {open && (
        <div className="mt-2 rounded-md border border-gray-200 p-3">
          <JobIngestPanel mode={mode} onIngested={() => onChanged()} />
        </div>
      )}

      {showAgentPrompt && (
        <AgentPromptModal
          title="Prompt an agent to capture a job posting"
          prompt={JOB_AGENT_PROMPT}
          hint='Paste the markdown it returns via "Add a job ▾" (paste or .md upload).'
          onClose={() => setShowAgentPrompt(false)}
        />
      )}
    </div>
  );
}

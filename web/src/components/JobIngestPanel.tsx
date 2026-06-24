import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { AssistantMode } from "../App";

// Reusable both-modes job-ingest UI: add a job from a URL (fetched, allowlisted), or
// by pasting text / uploading a PDF (you provide the content -> works for sites that
// block bots). Parsing is mode-aware: External uses the LLM; Internal hands a command
// to local Claude and polls the ingest marker. On a successful ingest,
// onIngested(jobId, created, position) fires so the caller can refresh the jobs list
// or link the new job to an application.
type AddTab = "url" | "doc";

export default function JobIngestPanel({
  mode,
  onIngested,
  textPlaceholder = "Paste the job posting text (or save the page as PDF and upload it below)…",
}: {
  mode: AssistantMode;
  onIngested: (jobId: string, created: boolean, position: string) => void;
  textPlaceholder?: string;
}) {
  const [tab, setTab] = useState<AddTab>("url");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(""); // ingest result / error
  const [prompt, setPrompt] = useState(""); // Internal: the line to run
  const [waiting, setWaiting] = useState(false);
  const [copied, setCopied] = useState(false);
  const seqBaseline = useRef(0); // ingest-marker seq before an Internal ingest

  // Internal: poll the ingest marker (only the ingest path bumps it, so a Scan or
  // another tab can't false-trigger; resolves even when Claude's job dedups).
  useEffect(() => {
    if (!waiting) return;
    const started = Date.now();
    let live = true;
    let inFlight = false;
    const id = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await api.getIngestResult().catch(() => null);
        if (!live) return;
        if (res && res.seq > seqBaseline.current) {
          setWaiting(false);
          setPrompt("");
          setText("");
          setMsg(res.created ? `Added: ${res.position ?? "job"}.` : `Already tracked: ${res.position ?? "job"}.`);
          if (res.job_id) onIngested(res.job_id, !!res.created, res.position ?? "");
        } else if (Date.now() - started > 180_000) {
          setWaiting(false);
          setMsg("Didn't detect an added job — it may already be tracked, or the command hasn't run yet.");
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
  }, [waiting]);

  const startInternal = async (note: string) => {
    const r = await api.getIngestResult().catch(() => null);
    seqBaseline.current = r?.seq ?? 0; // resolve only on a NEW ingest beyond this point
    setPrompt("ingest the job I pasted");
    setMsg(note);
    setCopied(false);
    setWaiting(true);
  };

  const addUrl = async () => {
    if (!url.trim() || busy) return;
    setBusy(true);
    setMsg("");
    try {
      const r = await api.ingestUrl(url.trim());
      setUrl("");
      setMsg(r.created ? `Added: ${r.job?.position ?? "job"}.` : "Already tracked.");
      if (r.job?.id) onIngested(r.job.id, !!r.created, r.job.position ?? "");
    } catch (e) {
      // Show the API's actual reason when it's meaningful (e.g. a crawl-policy block like
      // "Meta bot-protects… paste the text instead"); fall back to the generic hint for a
      // bare HTTP status.
      const reason = e instanceof Error ? e.message : "";
      setMsg(
        !reason || /^\d{3}\b/.test(reason)
          ? "Couldn't fetch that URL (the site may block it) — paste the text or upload a PDF instead."
          : reason
      );
    } finally {
      setBusy(false);
    }
  };

  const addText = async () => {
    if (!text.trim() || busy || waiting) return;
    if (mode === "internal") {
      setBusy(true);
      let ok = true;
      try {
        await api.saveJobSource(text);
      } catch {
        ok = false;
        setMsg("Couldn't save the posting. Try again.");
      } finally {
        setBusy(false);
      }
      if (ok) await startInternal("Posting saved — run the command in the Claude terminal.");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const r = await api.ingestJobDoc(text);
      setText("");
      setMsg(r.created ? `Added: ${r.job?.position ?? "job"}.` : "Already tracked.");
      if (r.job?.id) onIngested(r.job.id, !!r.created, r.job.position ?? "");
    } catch {
      setMsg("Couldn't parse a job from that text — paste more of the posting.");
    } finally {
      setBusy(false);
    }
  };

  const addFile = async (file: File | undefined) => {
    if (!file || busy || waiting) return;
    if (mode === "internal") {
      setBusy(true);
      let ok = true;
      try {
        await api.uploadJobSource(file);
      } catch {
        ok = false;
        setMsg("Couldn't read / save that file. Try again.");
      } finally {
        setBusy(false);
      }
      if (ok) await startInternal("File saved — run the command in the Claude terminal.");
      return;
    }
    setBusy(true);
    setMsg("");
    try {
      const r = await api.uploadJobDoc(file);
      setMsg(r.created ? `Added: ${r.job?.position ?? "job"}.` : "Already tracked.");
      if (r.job?.id) onIngested(r.job.id, !!r.created, r.job.position ?? "");
    } catch {
      setMsg("Couldn't read / parse that file.");
    } finally {
      setBusy(false);
    }
  };

  const tabBtn = (t: AddTab, label: string) => (
    <button
      type="button"
      onClick={() => setTab(t)}
      className={`px-2 py-1 text-xs font-medium rounded ${
        tab === t ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
      }`}
    >
      {label}
    </button>
  );

  return (
    <div>
      <div className="flex gap-1.5">
        {tabBtn("url", "From URL")}
        {tabBtn("doc", "Paste / PDF")}
        <span className="ml-auto text-[10px] text-gray-400 self-center">
          {mode === "internal" ? "Internal: local Claude parses it" : "External: API parses it"}
        </span>
      </div>

      {tab === "url" ? (
        <div className="mt-2 flex items-center gap-2">
          <input
            className="flex-1 px-2 py-1.5 text-sm border border-gray-300 rounded-md"
            placeholder="https://… job posting URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button
            type="button"
            onClick={addUrl}
            disabled={busy || !url.trim()}
            className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            Fetch
          </button>
        </div>
      ) : (
        <div className="mt-2 space-y-2">
          <textarea
            className="w-full h-28 px-2 py-1.5 text-sm border border-gray-300 rounded-md resize-y font-mono"
            placeholder={textPlaceholder}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={addText}
              disabled={busy || waiting || !text.trim()}
              className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {waiting ? "Waiting…" : "Add from text"}
            </button>
            <label className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md cursor-pointer hover:bg-indigo-100">
              {busy ? "Working…" : waiting ? "Waiting…" : "Upload PDF / .txt / .md"}
              <input
                type="file"
                accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
                className="hidden"
                disabled={busy || waiting}
                onChange={(e) => addFile(e.target.files?.[0])}
              />
            </label>
          </div>
        </div>
      )}

      {mode === "internal" && prompt && (
        <div className="mt-2 rounded-md border border-emerald-200 bg-emerald-50 p-2 text-sm">
          <div className="flex items-center gap-2">
            <code className="flex-1 px-2 py-1 rounded bg-white border border-emerald-200 text-gray-800">
              {prompt}
            </code>
            <button
              type="button"
              onClick={() =>
                navigator.clipboard
                  ?.writeText(prompt)
                  .then(() => setCopied(true))
                  .catch(() => {})
              }
              className="px-2 py-1 text-xs font-medium text-emerald-700 bg-white border border-emerald-300 rounded hover:bg-emerald-100"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="mt-1 text-xs text-emerald-700">
            {waiting ? "Waiting for Claude to add the job…" : "Run it in the Claude terminal."}
          </p>
        </div>
      )}

      {msg && <p className="mt-2 text-xs text-gray-500">{msg}</p>}
    </div>
  );
}

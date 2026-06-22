import { useState } from "react";
import { api } from "../api";
import type { AssistantMode } from "../App";
import JobIngestPanel from "./JobIngestPanel";

// Job acquisition, separate from the view controls in JobsTable:
//   Scan  — zero-token fetch from configured ATS sources (config/portals.yml).
//   Add   — from a URL, or by pasting / uploading a posting (no fetching) — the
//           reusable JobIngestPanel handles both modes; here it just refreshes.
export default function AddJobsBar({
  mode,
  onChanged,
}: {
  mode: AssistantMode;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [scanMsg, setScanMsg] = useState("");

  const scan = async () => {
    setBusy(true);
    setScanMsg("");
    try {
      const r = await api.scan();
      setScanMsg(
        r.new > 0
          ? `Found ${r.new} new (${r.duplicates} dupes · ${r.filtered} filtered)` +
              (r.capped ? " — capped; narrow filters in config/portals.yml for more." : ".")
          : `No new jobs (${r.duplicates} dupes · ${r.filtered} filtered). Add sources in config/portals.yml, or paste/upload a posting below.`
      );
      onChanged();
    } catch {
      setScanMsg("Scan failed — check the API / logs.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-b border-gray-200 bg-white px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={scan}
          disabled={busy}
          className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Working…" : "Scan sources"}
        </button>
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md hover:bg-indigo-100"
        >
          {open ? "Add a job ▴" : "Add a job ▾"}
        </button>
        {scanMsg && <span className="text-xs text-gray-500">{scanMsg}</span>}
      </div>

      {open && (
        <div className="mt-2 rounded-md border border-gray-200 p-3">
          <JobIngestPanel mode={mode} onIngested={() => onChanged()} />
        </div>
      )}
    </div>
  );
}

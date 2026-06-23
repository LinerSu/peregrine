import { useEffect, useState } from "react";
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
  const [sources, setSources] = useState<{ name: string; provider: string }[]>([]);
  const [selected, setSelected] = useState<string[]>([]); // [] = scan all configured companies

  useEffect(() => {
    api.sources().then((r) => setSources(r.companies)).catch(() => {});
  }, []);

  const toggle = (name: string) =>
    setSelected((prev) => (prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name]));

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
    <div className="border-b border-gray-200 bg-white px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        {sources.length > 1 && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-gray-700"
               title="Tick companies to scan; none ticked = scan all">
            <span className="text-gray-500">Scan:</span>
            {sources.map((s) => (
              <label key={s.name} className="inline-flex items-center gap-1 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={selected.includes(s.name)}
                  disabled={busy}
                  onChange={() => toggle(s.name)}
                />
                {s.name}
              </label>
            ))}
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

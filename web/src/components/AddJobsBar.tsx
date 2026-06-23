import { useEffect, useMemo, useState } from "react";
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
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerQuery, setPickerQuery] = useState("");

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
    <div className="border-b border-gray-200 bg-white px-3 py-2">
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
                    {!pickerList.length && <p className="px-2 py-2 text-gray-400">No matches.</p>}
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

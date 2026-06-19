import { useEffect, useState } from "react";
import { api, type Targets } from "../api";

// "What I'm looking for" — the search-intent layer. Saved to config/profile.yml
// (targets); drives scan filtering and is visible to the fit-scoring LLM.
const toList = (s: string) =>
  s.split(",").map((x) => x.trim()).filter(Boolean);
const fromList = (l?: string[]) => (l ?? []).join(", ");

export default function PreferencesPanel({ onChanged }: { onChanged: () => void }) {
  const [t, setT] = useState<Targets>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.getPreferences().then(setT);
  }, []);

  const save = async () => {
    setBusy(true);
    setSaved(false);
    try {
      await api.savePreferences(t);
      setSaved(true);
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const field = "w-full px-3 py-2 text-sm border border-gray-300 rounded-md";
  const label = "block text-xs font-medium text-gray-600 mb-1";

  return (
    <div className="h-full overflow-auto p-5">
      <div className="max-w-2xl mx-auto space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">What I'm looking for</h3>
          <p className="text-sm text-gray-500">
            Drives which scanned jobs are kept, and is factored into fit scoring.
          </p>
        </div>

        <div>
          <label className={label}>Target roles / titles (comma-separated)</label>
          <input
            className={field}
            placeholder="Senior Backend Engineer, Platform Engineer"
            value={fromList(t.roles)}
            onChange={(e) => setT({ ...t, roles: toList(e.target.value) })}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={label}>Locations (comma-separated)</label>
            <input
              className={field}
              placeholder="San Francisco, Remote"
              value={fromList(t.locations)}
              onChange={(e) => setT({ ...t, locations: toList(e.target.value) })}
            />
          </div>
          <div>
            <label className={label}>Work mode</label>
            <select
              className={field}
              value={t.work_mode ?? "any"}
              onChange={(e) => setT({ ...t, work_mode: e.target.value })}
            >
              <option value="any">Any</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={label}>Minimum salary</label>
            <input
              type="number"
              className={field}
              placeholder="180000"
              value={t.min_salary ?? ""}
              onChange={(e) =>
                setT({ ...t, min_salary: e.target.value ? Number(e.target.value) : null })
              }
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className={label}>Must-have keywords</label>
            <input
              className={field}
              placeholder="python, distributed systems"
              value={fromList(t.include_keywords)}
              onChange={(e) => setT({ ...t, include_keywords: toList(e.target.value) })}
            />
          </div>
          <div>
            <label className={label}>Exclude keywords</label>
            <input
              className={field}
              placeholder="crypto, on-call only"
              value={fromList(t.exclude_keywords)}
              onChange={(e) => setT({ ...t, exclude_keywords: toList(e.target.value) })}
            />
          </div>
        </div>

        <div className="flex items-center gap-3 pt-1">
          <button
            onClick={save}
            disabled={busy}
            className="px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save preferences"}
          </button>
          {saved && <span className="text-sm text-green-600">Saved ✓</span>}
        </div>
      </div>
    </div>
  );
}

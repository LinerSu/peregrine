import { useEffect, useState } from "react";
import { api, type Company, type DetectedSource, type Portals, type Targets } from "../api";

// "What I'm looking for" — the search-intent layer. Saved to config/profile.yml
// (targets); drives scan filtering and is visible to the fit-scoring LLM. This panel is also
// where scan SOURCES (companies) and relevance QUERIES live, so all search config is one place
// (no YAML editing).
const toList = (s: string) =>
  s.split(",").map((x) => x.trim()).filter(Boolean);
const fromList = (l?: string[]) => (l ?? []).join(", ");

export default function PreferencesPanel({ onChanged }: { onChanged: () => void }) {
  const [t, setT] = useState<Targets>({});
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  // Scan config (portals): companies + relevance queries.
  const [portals, setPortals] = useState<Portals | null>(null);
  const [detectName, setDetectName] = useState("");
  const [detected, setDetected] = useState<DetectedSource[] | null>(null); // null = not searched
  const [detecting, setDetecting] = useState(false);
  const [queryText, setQueryText] = useState("");
  const [savingScan, setSavingScan] = useState(false);

  useEffect(() => {
    api.getPreferences().then(setT);
    api.getPortals().then((p) => {
      setPortals(p);
      setQueryText(p.queries.join("\n"));
    });
  }, []);

  // Persist companies (the list is a live editor) and refresh the scan picker on next visit.
  const saveCompanies = async (companies: Company[]) => {
    setSavingScan(true);
    try {
      const p = await api.putPortals({ companies });
      setPortals(p);
      onChanged();
    } finally {
      setSavingScan(false);
    }
  };
  const findCompany = async () => {
    const name = detectName.trim();
    if (!name) return;
    setDetecting(true);
    setDetected(null);
    try {
      const r = await api.detectSources(name);
      setDetected(r.sources);
    } finally {
      setDetecting(false);
    }
  };
  const addCompany = (name: string, provider: string, slug: string) => {
    if (!portals) return;
    const s = slug.trim();
    // Dedup on name+provider+slug — the same slug can legitimately exist on two providers.
    const exists = portals.companies.some(
      (c) => c.name.toLowerCase() === name.toLowerCase() && c.provider === provider && c.slug === s
    );
    const companies = exists ? portals.companies : [...portals.companies, { name, provider, slug: s }];
    saveCompanies(companies);
    setDetectName("");
    setDetected(null);
  };
  const removeCompany = (idx: number) => {
    if (!portals) return;
    saveCompanies(portals.companies.filter((_, i) => i !== idx));
  };
  const saveQueries = async () => {
    setSavingScan(true);
    try {
      // One query per LINE — don't split on commas (a query may legitimately contain one).
      const queries = queryText.split("\n").map((s) => s.trim()).filter(Boolean);
      const p = await api.putPortals({ queries });
      setPortals(p);
      setQueryText(p.queries.join("\n"));
    } finally {
      setSavingScan(false);
    }
  };
  // Fill the editor with queries derived from the user's CV/profile (they review, then Save).
  const suggestQueries = async () => {
    const r = await api.suggestQueries();
    if (r.queries.length) setQueryText(r.queries.join("\n"));
  };

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

        {/* Scan sources — add a company by name; we detect its ATS board. */}
        {portals && (
          <div className="border-t border-gray-200 pt-4 space-y-3">
            <div>
              <h3 className="text-sm font-semibold text-gray-700">Scan sources</h3>
              <p className="text-sm text-gray-500">
                Companies to scan — add by name and we'll find the board. (Megacaps on Workday or
                bespoke careers sites, e.g. Google/Meta, aren't scannable; paste those via “Add a
                job”.)
              </p>
            </div>

            <div className="flex gap-2">
              <input
                className={field}
                placeholder="Company name (e.g. Stripe)"
                value={detectName}
                onChange={(e) => setDetectName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && findCompany()}
              />
              <button
                onClick={findCompany}
                disabled={detecting || !detectName.trim()}
                className="px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
              >
                {detecting ? "Finding…" : "Find board"}
              </button>
            </div>
            {detected && detected.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {detected.map((d) => (
                  <button
                    key={`${d.provider}-${d.slug}`}
                    onClick={() => addCompany(detectName.trim(), d.provider, d.slug)}
                    disabled={savingScan}
                    className="px-2 py-1 text-xs rounded border border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                  >
                    + {d.provider} · {d.slug} ({d.count} jobs)
                  </button>
                ))}
              </div>
            )}
            {detected && detected.length === 0 && (
              <p className="text-xs text-gray-500">
                No supported board found for that name — for Workday/bespoke sites, paste a job's
                URL or description via “Add a job” instead.
              </p>
            )}

            <ul className="divide-y divide-gray-100 rounded-md border border-gray-200">
              {portals.companies.map((c, i) => (
                <li key={`${c.name}-${c.slug}-${i}`} className="flex items-center gap-2 px-3 py-2 text-sm">
                  <span className="flex-1 truncate">{c.name}</span>
                  <span className="text-xs text-gray-400">
                    {c.provider}
                    {c.slug ? ` · ${c.slug}` : ""}
                  </span>
                  <button
                    onClick={() => removeCompany(i)}
                    disabled={savingScan}
                    className="text-xs text-gray-400 hover:text-red-600 disabled:opacity-50"
                  >
                    remove
                  </button>
                </li>
              ))}
              {!portals.companies.length && (
                <li className="px-3 py-2 text-xs text-gray-400">No sources yet.</li>
              )}
            </ul>
            <ManualAdd providers={portals.providers} onAdd={addCompany} field={field} disabled={savingScan} />
          </div>
        )}

        {/* Search queries — the relevance gate. */}
        {portals && (
          <div className="border-t border-gray-200 pt-4 space-y-2">
            <div>
              <h3 className="text-sm font-semibold text-gray-700">Search queries</h3>
              <p className="text-sm text-gray-500">
                A scan keeps only jobs matching one of these (all of a query's words appear), and
                the Jobs tab hides the rest. One per line. Empty = keep everything.
              </p>
            </div>
            <textarea
              className={`${field} h-24 font-mono`}
              placeholder={"machine learning engineer\napplied scientist"}
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <button
                onClick={saveQueries}
                disabled={savingScan}
                className="px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
              >
                {savingScan ? "Saving…" : "Save queries"}
              </button>
              <button
                onClick={suggestQueries}
                className="px-3 py-2 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md hover:bg-indigo-100"
                title="Fill from your profile's roles + experience (review, then Save)"
              >
                Suggest from my profile
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// Add a company manually — for a known ATS slug, or an Amazon search query (slug = the query).
function ManualAdd({
  providers,
  onAdd,
  field,
  disabled,
}: {
  providers: string[];
  onAdd: (name: string, provider: string, slug: string) => void;
  field: string;
  disabled?: boolean;
}) {
  const [name, setName] = useState("");
  const [provider, setProvider] = useState(providers[0] ?? "greenhouse");
  const [slug, setSlug] = useState("");
  return (
    <details className="text-sm">
      <summary className="cursor-pointer text-xs text-gray-500 hover:text-gray-700">
        Add manually (known ATS slug, or an Amazon search query)
      </summary>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          className={`${field} flex-1 min-w-[8rem]`}
          placeholder="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <select className={field} value={provider} onChange={(e) => setProvider(e.target.value)}>
          {providers.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
        <input
          className={`${field} flex-1 min-w-[8rem]`}
          placeholder={provider === "amazon" ? "search query" : "slug"}
          value={slug}
          onChange={(e) => setSlug(e.target.value)}
        />
        <button
          onClick={() => {
            if (name.trim()) {
              onAdd(name.trim(), provider, slug.trim());
              setName("");
              setSlug("");
            }
          }}
          disabled={disabled}
          className="px-3 py-2 text-sm font-medium text-white bg-gray-700 rounded-md hover:bg-gray-800 disabled:opacity-50"
        >
          Add
        </button>
      </div>
    </details>
  );
}

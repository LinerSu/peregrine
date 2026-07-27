import { useEffect, useState } from "react";
import { api, type DetectedSource, type Portals, type Targets } from "../api";

// The "Search" tab — set up a job search end to end, in logical order:
//   1. Search terms (the roles you want)  -> the relevance gate + fit-scoring
//   2. Companies to scan                  -> which boards we fetch
//   3. Filters (optional)                 -> narrow what's kept
// Then the user hits Scan on the Jobs tab. No YAML.
const toList = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const parseSalary = (s: string) => {
  const digits = s.replace(/[^\d]/g, "");
  return digits ? Number(digits) : null;
};
const fmtSalary = (n?: number | null) => (n != null ? n.toLocaleString("en-US") : "");

export default function PreferencesPanel({ onChanged }: { onChanged: () => void }) {
  const [t, setT] = useState<Targets>({});
  const [portals, setPortals] = useState<Portals | null>(null);
  // Free-text mirrors — typed as plain strings so a space/comma isn't stripped mid-keystroke;
  // parsed to lists only on Save.
  const [termsText, setTermsText] = useState(""); // one role per line
  const [locText, setLocText] = useState("");
  const [includeText, setIncludeText] = useState("");
  const [excludeText, setExcludeText] = useState("");
  const [salaryText, setSalaryText] = useState("");
  const [detectName, setDetectName] = useState("");
  const [detected, setDetected] = useState<DetectedSource[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(""); // latest action feedback
  const [purgeDays, setPurgeDays] = useState("180"); // housekeeping: retention cutoff
  const [purgeBusy, setPurgeBusy] = useState(false);
  const [purgeMsg, setPurgeMsg] = useState("");

  useEffect(() => {
    api.getPreferences().then((tt) => {
      setT(tt);
      setLocText((tt.locations ?? []).join(", "));
      setIncludeText((tt.include_keywords ?? []).join(", "));
      setExcludeText((tt.exclude_keywords ?? []).join(", "));
      setSalaryText(fmtSalary(tt.min_salary));
    });
    api.getPortals().then((p) => {
      setPortals(p);
      setTermsText(p.queries.join("\n"));
    });
  }, []);

  const hasCompanies = (portals?.companies.length ?? 0) > 0;

  // ONE save persists everything on screen coherently (built from the live text mirrors, so a
  // partial edit in one section can't be dropped). Search terms go to BOTH the relevance gate
  // (portals.queries) AND fit-scoring (targets.roles); filters go to preferences.
  const save = async () => {
    setBusy(true);
    try {
      const roles = termsText.split("\n").map((s) => s.trim()).filter(Boolean);
      const next: Targets = {
        ...t,
        roles,
        locations: toList(locText),
        include_keywords: toList(includeText),
        exclude_keywords: toList(excludeText),
        min_salary: parseSalary(salaryText),
      };
      // Two independent stores — use allSettled so a partial failure is reported honestly and
      // each store's local state reflects only what actually persisted.
      const [rp, rt] = await Promise.allSettled([
        api.putPortals({ queries: roles }),
        api.savePreferences(next),
      ]);
      if (rp.status === "fulfilled") setPortals(rp.value);
      if (rt.status === "fulfilled") setT(next);
      const ok = rp.status === "fulfilled" && rt.status === "fulfilled";
      setMsg(ok ? "Saved ✓" : "Partly saved — please retry (search terms and filters may differ).");
      if (ok) onChanged();
    } finally {
      setBusy(false);
    }
  };
  const suggest = async () => {
    const r = await api.suggestQueries();
    if (r.queries.length) {
      setTermsText(r.queries.join("\n"));
      setMsg("Filled from your profile — review and Save.");
    } else {
      setMsg("No suggestions yet — import your CV on the Profile tab first.");
    }
  };

  const find = async () => {
    if (!detectName.trim()) return;
    setBusy(true);
    setDetected(null);
    setMsg("");
    try {
      setDetected((await api.detectSources(detectName.trim())).sources);
    } finally {
      setBusy(false);
    }
  };
  const addCompany = async (name: string, provider: string, slug: string) => {
    if (!portals) return;
    const s = slug.trim();
    const exists = portals.companies.some(
      (c) => c.name.toLowerCase() === name.toLowerCase() && c.provider === provider && c.slug === s
    );
    setBusy(true);
    try {
      const companies = exists ? portals.companies : [...portals.companies, { name, provider, slug: s }];
      setPortals(await api.putPortals({ companies }));
      setDetectName("");
      setDetected(null);
      setMsg(`Added ${name} as a scan source ✓ — go to the Jobs tab and click Scan to fetch its jobs.`);
    } finally {
      setBusy(false);
    }
  };
  const removeCompany = async (idx: number) => {
    if (!portals) return;
    setBusy(true);
    try {
      setPortals(await api.putPortals({ companies: portals.companies.filter((_, i) => i !== idx) }));
    } finally {
      setBusy(false);
    }
  };

  const field = "w-full px-3 py-2 text-sm border border-gray-300 rounded-md";
  const label = "block text-xs font-medium text-gray-600 mb-1";
  const h = "text-sm font-semibold text-gray-800";
  const help = "text-xs text-gray-500";

  return (
    <div className="h-full overflow-auto p-5">
      <div className="max-w-2xl mx-auto space-y-6">
        <div>
          <h2 className="text-base font-bold text-gray-900">Set up your search</h2>
          <p className={help}>
            Peregrine scans the <strong>companies</strong> you add and keeps the jobs matching your{" "}
            <strong>search terms</strong>. Tune optional filters, then hit <strong>Scan</strong> on the
            Jobs tab.
          </p>
        </div>

        {/* 1 — Search terms */}
        <section className="space-y-2">
          <div>
            <h3 className={h}>1 · Search terms — roles you want</h3>
            <p className={help}>
              A scan keeps a job only if it matches one of these (all of a term's words appear). One per
              line. These also tell fit-scoring what you're after.
            </p>
          </div>
          <textarea
            className={`${field} h-24 font-mono`}
            placeholder={"machine learning engineer\napplied scientist"}
            value={termsText}
            onChange={(e) => setTermsText(e.target.value)}
          />
          <button
            onClick={suggest}
            className="px-3 py-2 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md hover:bg-indigo-100"
            title="Fill from your profile's roles + experience"
          >
            Suggest from my profile
          </button>
        </section>

        {/* 2 — Companies */}
        <section className="space-y-2 border-t border-gray-200 pt-5">
          <div>
            <h3 className={h}>2 · Companies to scan</h3>
            <p className={help}>
              We fetch these companies' public job boards. Type a name and we'll find the board — adding
              one is a <em>source</em>, not the jobs themselves (those arrive when you Scan). Megacaps on
              Workday/bespoke sites (Google, Meta…) aren't scannable; paste those via “Add a job”.
            </p>
          </div>
          <div className="flex gap-2">
            <input
              className={field}
              placeholder="Company name (e.g. Stripe)"
              value={detectName}
              onChange={(e) => setDetectName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && find()}
            />
            <button
              onClick={find}
              disabled={busy || !detectName.trim()}
              className="px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
            >
              Find board
            </button>
          </div>
          {detected && detected.length > 0 && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-gray-500">Add as source:</span>
              {detected.map((d) => (
                <button
                  key={`${d.provider}-${d.slug}`}
                  onClick={() => addCompany(detectName.trim(), d.provider, d.slug)}
                  disabled={busy}
                  className="px-2 py-1 text-xs rounded border border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                >
                  + {d.provider} · {d.slug} ({d.count} open)
                </button>
              ))}
            </div>
          )}
          {detected && detected.length === 0 && (
            <p className={help}>
              No supported board for that name — paste a job URL/description via “Add a job” instead.
            </p>
          )}
          {portals && (
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
                    disabled={busy}
                    className="text-xs text-gray-400 hover:text-red-600 disabled:opacity-50"
                  >
                    remove
                  </button>
                </li>
              ))}
              {!portals.companies.length && (
                <li className="px-3 py-2 text-xs text-gray-400">No companies yet — add one above.</li>
              )}
            </ul>
          )}
          {portals && <ManualAdd providers={portals.providers} onAdd={addCompany} field={field} disabled={busy} />}
        </section>

        {/* 3 — Filters */}
        <section className="space-y-3 border-t border-gray-200 pt-5">
          <div>
            <h3 className={h}>3 · Filters (optional)</h3>
            <p className={help}>Narrow what a scan keeps. Leave blank for no limit.</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={label}>Locations (comma-separated)</label>
              <input
                className={field}
                placeholder="San Francisco, Remote"
                value={locText}
                onChange={(e) => setLocText(e.target.value)}
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
              <label className={label}>Minimum salary (USD)</label>
              <input
                className={field}
                inputMode="numeric"
                placeholder="180,000"
                value={salaryText}
                onChange={(e) => setSalaryText(fmtSalary(parseSalary(e.target.value)))}
              />
            </div>
            <div>
              <label className={label}>Must-have keywords (comma-separated)</label>
              <input
                className={field}
                placeholder="python, distributed systems"
                value={includeText}
                onChange={(e) => setIncludeText(e.target.value)}
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={label}>Exclude keywords (comma-separated)</label>
              <input
                className={field}
                placeholder="crypto, on-call only"
                value={excludeText}
                onChange={(e) => setExcludeText(e.target.value)}
              />
            </div>
          </div>
        </section>

        <section className="space-y-2">
          <h3 className={h}>Housekeeping</h3>
          <div className="flex flex-wrap items-center gap-2 text-sm text-gray-700">
            Remove <b>closed</b> jobs posted more than
            <input
              className="w-20 px-2 py-1 text-sm border border-gray-300 rounded-md"
              inputMode="numeric"
              value={purgeDays}
              onChange={(e) => setPurgeDays(e.target.value.replace(/\D/g, ""))}
            />
            days ago
            <button
              onClick={async () => {
                const days = parseInt(purgeDays, 10);
                if (!days || days < 1) {
                  setPurgeMsg("Enter a number of days (e.g. 180).");
                  return;
                }
                if (!window.confirm(`Permanently delete closed jobs posted over ${days} days ago (and their generated materials)?`)) return;
                setPurgeBusy(true);
                setPurgeMsg("");
                try {
                  const r = await api.purgeJobs(days);
                  setPurgeMsg(
                    `Removed ${r.deleted}` +
                      (r.skipped_linked ? ` · kept ${r.skipped_linked} with applications` : "") +
                      (r.skipped_undated ? ` · kept ${r.skipped_undated} without a posted date` : "")
                  );
                } catch {
                  setPurgeMsg("Purge failed — is the API up?");
                } finally {
                  setPurgeBusy(false);
                }
              }}
              disabled={purgeBusy}
              className="px-3 py-1.5 text-sm font-medium text-rose-700 border border-rose-300 rounded-md hover:bg-rose-50 disabled:opacity-50"
            >
              {purgeBusy ? "Purging…" : "Purge now"}
            </button>
            {purgeMsg && <span className="text-xs text-gray-500">{purgeMsg}</span>}
          </div>
          <p className="text-xs text-gray-500">
            Jobs linked to an application are never removed. For automatic cleanup after each
            scan, set <code className="px-1 rounded bg-gray-100">filters.retention_days</code> in{" "}
            <code className="px-1 rounded bg-gray-100">config/portals.yml</code>.
          </p>
        </section>

        <div className="border-t border-gray-200 pt-4 flex flex-wrap items-center gap-3">
          <button
            onClick={save}
            disabled={busy}
            className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Save search settings"}
          </button>
          <span className="text-sm text-gray-600">
            → then open the <strong>Jobs</strong> tab and click <strong>Scan</strong>
            {hasCompanies ? "" : " (add a company first)"}.
          </span>
          {msg && <span className="ml-auto text-xs text-emerald-700">{msg}</span>}
        </div>
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

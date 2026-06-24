import { useEffect, useState, type ReactNode } from "react";
import { api, type DetectedSource, type Portals, type Targets } from "../api";

// First-run guided setup: import CV -> confirm CV-derived queries -> add companies -> first scan.
// Pure orchestration over existing endpoints; the CV step hands off to the Profile tab so the
// mode-aware (External parse / Internal command) intake isn't duplicated. Auto-shown on an empty
// dataset, and re-openable from the header.
export default function Onboarding({
  onClose,
  onNavProfile,
  onChanged,
}: {
  onClose: () => void;
  onNavProfile: () => void; // switch to the Profile tab (where CV intake lives)
  onChanged: () => void; // refresh the app's jobs after a scan
}) {
  const [hasProfile, setHasProfile] = useState(false);
  const [portals, setPortals] = useState<Portals | null>(null);
  const [prefs, setPrefs] = useState<Targets>({}); // so search terms also feed fit-scoring
  const [queryText, setQueryText] = useState("");
  const [detectName, setDetectName] = useState("");
  const [detected, setDetected] = useState<DetectedSource[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [scanMsg, setScanMsg] = useState("");

  const load = async () => {
    const [p, port, pref] = await Promise.all([
      api.getProfile().catch(() => null),
      api.getPortals().catch(() => null),
      api.getPreferences().catch(() => ({}) as Targets),
    ]);
    setHasProfile(!!(p && (p.name || p.skills?.length || p.sections?.length)));
    setPrefs(pref);
    if (port) {
      setPortals(port);
      setQueryText(port.queries.join("\n"));
    }
  };
  useEffect(() => {
    load();
  }, []);

  const hasQueries = (portals?.queries.length ?? 0) > 0;
  const hasCompanies = (portals?.companies.length ?? 0) > 0;

  const suggest = async () => {
    const r = await api.suggestQueries();
    if (r.queries.length) setQueryText(r.queries.join("\n"));
  };
  const saveQueries = async () => {
    setBusy(true);
    try {
      const queries = queryText.split("\n").map((s) => s.trim()).filter(Boolean);
      // Mirror the Search tab: terms drive the relevance gate AND fit-scoring (targets.roles).
      const [p] = await Promise.all([
        api.putPortals({ queries }),
        api.savePreferences({ ...prefs, roles: queries }),
      ]);
      setPortals(p);
      setPrefs((prev) => ({ ...prev, roles: queries }));
    } finally {
      setBusy(false);
    }
  };
  const find = async () => {
    if (!detectName.trim()) return;
    setBusy(true);
    setDetected(null);
    try {
      setDetected((await api.detectSources(detectName.trim())).sources);
    } finally {
      setBusy(false);
    }
  };
  const addCompany = async (provider: string, slug: string) => {
    if (!portals) return;
    const name = detectName.trim();
    // Dedup (the backend doesn't) so double-clicking a detected board can't create duplicates.
    const exists = portals.companies.some(
      (c) => c.name.toLowerCase() === name.toLowerCase() && c.provider === provider && c.slug === slug
    );
    if (exists) {
      setDetectName("");
      setDetected(null);
      return;
    }
    setBusy(true);
    try {
      const companies = [...portals.companies, { name, provider, slug }];
      setPortals(await api.putPortals({ companies }));
      setDetectName("");
      setDetected(null);
    } finally {
      setBusy(false);
    }
  };
  const scan = async () => {
    setBusy(true);
    setScanMsg("Scanning…");
    try {
      const r = await api.scan();
      setScanMsg(`Found ${r.new} new job${r.new === 1 ? "" : "s"} matching your search.`);
      onChanged();
    } catch {
      setScanMsg("Scan failed — check the API / logs.");
    } finally {
      setBusy(false);
    }
  };

  const field = "w-full px-3 py-2 text-sm border border-gray-300 rounded-md";
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/30 p-4 overflow-auto">
      <div
        className="w-full max-w-xl my-8 rounded-lg bg-white shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="onboarding-title"
      >
        <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200">
          <div>
            <h2 id="onboarding-title" className="text-base font-bold text-gray-900">
              Get started
            </h2>
            <p className="text-xs text-gray-500">Four quick steps to your first matches.</p>
          </div>
          <button onClick={onClose} className="text-sm text-gray-400 hover:text-gray-700">
            Close
          </button>
        </div>

        <div className="px-5 py-4 space-y-5">
          <Step n={1} title="Import your CV" done={hasProfile}>
            {hasProfile ? (
              <p className="text-xs text-emerald-700">Profile loaded — everything below is tailored to it.</p>
            ) : (
              <div className="space-y-1.5">
                <p className="text-xs text-gray-500">Paste or upload your résumé in the Profile tab (PDF/DOCX/text).</p>
                <button
                  onClick={onNavProfile}
                  className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
                >
                  Open Profile tab →
                </button>
                <p className="text-[11px] text-gray-400">…then reopen “Get started” to continue.</p>
              </div>
            )}
          </Step>

          <Step n={2} title="Confirm your search" done={hasQueries}>
            <p className="text-xs text-gray-500 mb-1.5">
              Scans keep only jobs matching these. One per line.
            </p>
            <textarea
              className={`${field} h-20 font-mono`}
              placeholder={"machine learning engineer\napplied scientist"}
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
            />
            <div className="mt-1.5 flex items-center gap-2">
              <button
                onClick={saveQueries}
                disabled={busy}
                className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
              >
                Save
              </button>
              <button
                onClick={suggest}
                disabled={!hasProfile}
                title={hasProfile ? "Fill from your profile" : "Import your CV first"}
                className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md hover:bg-indigo-100 disabled:opacity-50"
              >
                Suggest from my profile
              </button>
            </div>
          </Step>

          <Step n={3} title="Add companies to scan" done={hasCompanies}>
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
                className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50 whitespace-nowrap"
              >
                Find board
              </button>
            </div>
            {detected && detected.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-2">
                {detected.map((d) => (
                  <button
                    key={`${d.provider}-${d.slug}`}
                    onClick={() => addCompany(d.provider, d.slug)}
                    disabled={busy}
                    className="px-2 py-1 text-xs rounded border border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                  >
                    + {d.provider} · {d.slug} ({d.count} open)
                  </button>
                ))}
              </div>
            )}
            {detected && detected.length === 0 && (
              <p className="mt-1.5 text-xs text-gray-500">
                No supported board for that name — paste a job URL/description via “Add a job” instead.
              </p>
            )}
            {portals && portals.companies.length > 0 && (
              <p className="mt-1.5 text-xs text-gray-500">
                Scanning: {portals.companies.map((c) => c.name).join(", ")}
              </p>
            )}
          </Step>

          <Step n={4} title="Run your first scan" done={false}>
            <button
              onClick={scan}
              disabled={busy || !hasCompanies}
              title={hasCompanies ? "" : "Add a company first"}
              className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
            >
              {busy ? "Scanning…" : "Scan now"}
            </button>
            {scanMsg && <p className="mt-1.5 text-xs text-gray-600">{scanMsg}</p>}
          </Step>
        </div>

        <div className="px-5 py-3 border-t border-gray-200 text-right">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm font-medium text-white bg-gray-800 rounded-md hover:bg-gray-900"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

function Step({ n, title, done, children }: { n: number; title: string; done: boolean; children: ReactNode }) {
  return (
    <div className="flex gap-3">
      <div
        className={`flex-none w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
          done ? "bg-emerald-500 text-white" : "bg-gray-200 text-gray-600"
        }`}
      >
        {done ? "✓" : n}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold text-gray-800">{title}</div>
        <div className="mt-1.5">{children}</div>
      </div>
    </div>
  );
}

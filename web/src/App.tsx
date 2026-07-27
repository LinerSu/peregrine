import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Application, type Job } from "./api";
import AssistantPanel from "./components/AssistantPanel";
import Onboarding from "./components/Onboarding";
import JobsTable from "./components/JobsTable";
import AddJobsBar from "./components/AddJobsBar";
import JobDetail from "./components/JobDetail";
import ApplicationsTable from "./components/ApplicationsTable";
import ProfilePanel from "./components/ProfilePanel";
import PreferencesPanel from "./components/PreferencesPanel";
import UpskillingPanel from "./components/UpskillingPanel";
import InsightsPanel from "./components/InsightsPanel";

type Tab = "jobs" | "applications" | "insights" | "targets" | "profile" | "upskilling";

const TABS: { id: Tab; label: string }[] = [
  { id: "jobs", label: "Jobs" },
  { id: "applications", label: "Applications" },
  { id: "insights", label: "Insights" },
  { id: "targets", label: "Search" },
  { id: "profile", label: "Profile / CV" },
  { id: "upskilling", label: "Upskilling" },
];

export type AssistantMode = "external" | "internal";

const MODE_KEY = "peregrine.mode";

export default function App() {
  const [tab, setTab] = useState<Tab>("jobs");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [llmMock, setLlmMock] = useState(false); // External mode has no LLM key -> mock
  const [dataset, setDataset] = useState<string | null>(null); // active demo persona, or null = live
  const [showOnboarding, setShowOnboarding] = useState(false);
  const ONBOARDED_KEY = "peregrine.onboarded";

  // Auto-open the guided setup ONCE for a fresh (unconfigured) dataset — no profile and no jobs.
  const bootedRef = useRef(false);
  useEffect(() => {
    if (bootedRef.current) return;
    bootedRef.current = true;
    (async () => {
      try {
        if (localStorage.getItem(ONBOARDED_KEY)) return;
        const [{ jobs }, profile] = await Promise.all([api.listJobs(), api.getProfile()]);
        const empty =
          jobs.length === 0 && !(profile.name || profile.skills?.length || profile.sections?.length);
        if (empty) setShowOnboarding(true);
      } catch {
        /* ignore — onboarding stays reachable from the header */
      }
    })();
  }, []);
  const closeOnboarding = () => {
    setShowOnboarding(false);
    try {
      localStorage.setItem(ONBOARDED_KEY, "1"); // don't auto-reopen; header re-opens it
    } catch {
      /* best-effort */
    }
  };
  // External = API-backed; Internal = local Claude terminal. Lifted here (and
  // persisted) so EVERY LLM-backed tab switches its behavior to match the global
  // mode — the single source of truth is this toggle in the header.
  const [mode, setMode] = useState<AssistantMode>(() => {
    try {
      const saved = localStorage.getItem(MODE_KEY);
      return saved === "internal" || saved === "external" ? saved : "external";
    } catch {
      return "external"; // localStorage can throw in private/sandboxed contexts
    }
  });

  // Jobs text search runs SERVER-SIDE (it matches the full posting incl. the description-keyword
  // index, which is never shipped to the client). Held in a ref so refresh()/onChanged keep the
  // current search after an edit, without re-creating the callback on every keystroke.
  const [jobQuery, setJobQuery] = useState("");
  const jobQueryRef = useRef("");

  const refreshJobs = useCallback(async () => {
    const q = jobQueryRef.current;
    try {
      const { jobs } = await api.listJobs(q);
      if (jobQueryRef.current === q) setJobs(jobs); // ignore a stale response — the query moved on
    } catch {
      /* a debounced search failure shouldn't spam the console; the next keystroke retries */
    }
  }, []);
  const refresh = useCallback(async () => {
    const [{ jobs }, { applications }] = await Promise.all([
      api.listJobs(jobQueryRef.current),
      api.listApplications(),
    ]);
    setJobs(jobs);
    setApplications(applications);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Debounced server search: refetch jobs (only) as the query changes. Skip the first run — the
  // mount effect above already did the initial full load.
  const firstJobQuery = useRef(true);
  useEffect(() => {
    jobQueryRef.current = jobQuery;
    if (firstJobQuery.current) {
      firstJobQuery.current = false;
      return;
    }
    const t = setTimeout(refreshJobs, 250);
    return () => clearTimeout(t);
  }, [jobQuery, refreshJobs]);

  // Is the API backed by a real LLM, or returning mock placeholders (no key)?
  // And is a demo dataset active (header badge — live vs demo is otherwise invisible)?
  useEffect(() => {
    let live = true;
    api.getLlmStatus().then((s) => live && setLlmMock(s.mock)).catch(() => {});
    api.getHealth().then((h) => live && setDataset(h.dataset)).catch(() => {});
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      /* persistence is best-effort */
    }
  }, [mode]);

  // Applications with no linked job posting — surfaced on the tab so they're
  // discoverable from anywhere (the row badge + in-panel hint let you fix them).
  const orphanCount = applications.filter((a) => a.job_tracked === false).length;

  return (
    <div className="flex flex-col h-screen text-gray-900">
      <header className="px-4 py-3 bg-white border-b border-gray-200 flex items-center gap-3">
        <img
          src="/peregrine-icon.png"
          alt="Peregrine"
          className="w-9 h-9 rounded-lg object-cover"
          onError={(e) => {
            e.currentTarget.style.display = "none";
          }}
        />
        <div>
          <h1 className="text-base font-bold">Peregrine</h1>
          <p className="text-xs text-gray-500">Personal AI job-search assistant</p>
        </div>

        {/* Demo-data badge: without it, demo and live modes are pixel-identical and a
            forgotten PEREGRINE_DATASET quietly impersonates the user's real workspace. */}
        {dataset && (
          <span
            title={`Demo dataset "${dataset}" is active (PEREGRINE_DATASET). Your real config/ + data/ are untouched — switch back with: ./scripts/dataset.sh off`}
            className="px-2.5 py-1 text-xs font-medium rounded-full border border-amber-300 bg-amber-50 text-amber-800"
          >
            🧪 Demo data: {dataset}
          </span>
        )}

        <button
          onClick={() => setShowOnboarding(true)}
          title="Guided setup: CV → search → companies → first scan"
          className="ml-auto px-2.5 py-1 text-xs font-medium text-indigo-700 border border-indigo-200 rounded-md hover:bg-indigo-50"
        >
          Get started
        </button>
        {/* New tab: /docs is a separate page (see main.tsx), so same-tab navigation
            would drop the app's state (open job, chat, scroll). */}
        <a
          href="/docs"
          target="_blank"
          rel="noopener noreferrer"
          title="Project documentation (opens in a new tab)"
          className="px-2.5 py-1 text-xs font-medium text-indigo-700 border border-indigo-200 rounded-md hover:bg-indigo-50"
        >
          Docs
        </a>

        {/* Global assistant mode — every LLM action follows this. */}
        <div className="flex flex-col items-end gap-0.5">
          <div className="flex items-center rounded-md border border-gray-200 p-0.5">
            {(["external", "internal"] as AssistantMode[]).map((m) => (
              <button
                key={m}
                type="button"
                aria-pressed={mode === m}
                onClick={() => setMode(m)}
                title={
                  m === "external"
                    ? "API-backed — uses LLM_PROVIDER + key (metered)"
                    : "Local Claude in the terminal — free on your own subscription"
                }
                className={`px-2.5 py-1 text-xs font-medium rounded transition-colors ${
                  mode === m
                    ? m === "internal"
                      ? "bg-emerald-600 text-white"
                      : "bg-indigo-600 text-white"
                    : "text-gray-500 hover:text-gray-700"
                }`}
              >
                {m === "external" ? "External" : "Internal (Claude)"}
              </button>
            ))}
          </div>
          <span className="text-[10px] text-gray-400">
            {mode === "internal"
              ? "LLM actions run on local Claude (free)"
              : llmMock
              ? "No LLM key — responses are mock"
              : "LLM actions use the API (metered)"}
          </span>
        </div>
      </header>

      {mode === "external" && llmMock && (
        <div className="px-4 py-2 bg-amber-50 border-b border-amber-200 text-xs text-amber-800">
          <span className="font-semibold">External mode is using mock responses</span> — AI
          results (fit scores, cover letters, CVs, chat) are <span className="font-semibold">placeholders,
          not real analysis</span>. Configure a real <code className="px-1 rounded bg-amber-100">LLM_PROVIDER</code> + key
          in <code className="px-1 rounded bg-amber-100">.env</code>, or switch to{" "}
          <span className="font-semibold">Internal (Claude)</span> above — free, runs on your local Claude.
        </div>
      )}

      <main className="flex flex-1 min-h-0">
        <section className="w-1/3 max-w-md border-r border-gray-200 bg-white">
          <AssistantPanel onAction={refresh} mode={mode} />
        </section>

        <section className="flex flex-col flex-1 min-w-0 bg-white">
          <nav className="flex items-center gap-1 px-3 pt-2 border-b border-gray-200 bg-white">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-2 text-sm font-medium rounded-t-md border-b-2 -mb-px transition-colors ${
                  tab === t.id
                    ? "border-indigo-600 text-indigo-700"
                    : "border-transparent text-gray-500 hover:text-gray-700"
                }`}
              >
                {t.label}
                {t.id === "applications" && applications.length > 0 && (
                  <span className="ml-1.5 px-1.5 py-0.5 text-xs rounded-full bg-indigo-100 text-indigo-700">
                    {applications.length}
                  </span>
                )}
                {t.id === "applications" && orphanCount > 0 && (
                  <span
                    title={`${orphanCount} application${orphanCount > 1 ? "s have" : " has"} no linked job posting`}
                    className="ml-1 px-1.5 py-0.5 text-xs rounded-full bg-amber-100 text-amber-700"
                  >
                    ⚠{orphanCount}
                  </span>
                )}
              </button>
            ))}
          </nav>

          <div className="flex-1 min-h-0">
            {tab === "jobs" && (
              <div className="flex h-full min-h-0">
                <div className="w-2/5 min-w-[320px] border-r border-gray-200 flex flex-col min-h-0">
                  <AddJobsBar mode={mode} onChanged={refresh} />
                  <div className="flex-1 min-h-0">
                    <JobsTable
                      jobs={jobs}
                      query={jobQuery}
                      onQueryChange={setJobQuery}
                      selectedId={selectedId}
                      onSelect={setSelectedId}
                      onChanged={refresh}
                    />
                  </div>
                </div>
                <div className="flex-1 min-w-0">
                  {selectedId ? (
                    <JobDetail jobId={selectedId} onChanged={refresh} mode={mode} />
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-400 text-sm px-6 text-center">
                      Select a job to see fit, strengths, weaknesses, and the apply gate.
                    </div>
                  )}
                </div>
              </div>
            )}

            {tab === "applications" && (
              <ApplicationsTable applications={applications} mode={mode} onChanged={refresh} />
            )}

            {tab === "insights" && <InsightsPanel mode={mode} />}

            {tab === "targets" && <PreferencesPanel onChanged={refresh} />}

            {tab === "profile" && <ProfilePanel onChanged={refresh} mode={mode} />}

            {tab === "upskilling" && <UpskillingPanel jobs={jobs} mode={mode} />}
          </div>
        </section>
      </main>

      {showOnboarding && (
        <Onboarding
          onClose={closeOnboarding}
          onNavProfile={() => {
            setShowOnboarding(false);
            setTab("profile");
          }}
          onChanged={refresh}
        />
      )}
    </div>
  );
}

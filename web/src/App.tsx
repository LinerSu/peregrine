import { useCallback, useEffect, useState } from "react";
import { api, type Application, type Job } from "./api";
import AssistantPanel from "./components/AssistantPanel";
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
  { id: "targets", label: "Targets" },
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

  const refresh = useCallback(async () => {
    const [{ jobs }, { applications }] = await Promise.all([
      api.listJobs(),
      api.listApplications(),
    ]);
    setJobs(jobs);
    setApplications(applications);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    try {
      localStorage.setItem(MODE_KEY, mode);
    } catch {
      /* persistence is best-effort */
    }
  }, [mode]);

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

        {/* Global assistant mode — every LLM action follows this. */}
        <div className="ml-auto flex flex-col items-end gap-0.5">
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
              : "LLM actions use the API (metered)"}
          </span>
        </div>
      </header>

      <main className="flex flex-1 min-h-0">
        <section className="w-1/3 max-w-md border-r border-gray-200 bg-white">
          <AssistantPanel onAction={refresh} mode={mode} setMode={setMode} />
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

            {tab === "insights" && <InsightsPanel />}

            {tab === "targets" && <PreferencesPanel onChanged={refresh} />}

            {tab === "profile" && <ProfilePanel onChanged={refresh} mode={mode} />}

            {tab === "upskilling" && <UpskillingPanel jobs={jobs} mode={mode} />}
          </div>
        </section>
      </main>
    </div>
  );
}

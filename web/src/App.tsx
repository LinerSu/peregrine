import { useCallback, useEffect, useState } from "react";
import { api, type Application, type Job } from "./api";
import ChatPanel from "./components/ChatPanel";
import JobsTable from "./components/JobsTable";
import JobDetail from "./components/JobDetail";
import ApplicationsTable from "./components/ApplicationsTable";
import ProfilePanel from "./components/ProfilePanel";
import UpskillingPanel from "./components/UpskillingPanel";

type Tab = "jobs" | "applications" | "profile" | "upskilling";

const TABS: { id: Tab; label: string }[] = [
  { id: "jobs", label: "Jobs" },
  { id: "applications", label: "Applications" },
  { id: "profile", label: "Profile / CV" },
  { id: "upskilling", label: "Upskilling" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("jobs");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [applications, setApplications] = useState<Application[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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

  const scan = async () => {
    setLoading(true);
    try {
      await api.scan();
      await refresh();
    } finally {
      setLoading(false);
    }
  };

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
      </header>

      <main className="flex flex-1 min-h-0">
        <section className="w-1/3 max-w-md border-r border-gray-200 bg-white">
          <ChatPanel onAction={refresh} />
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
                <div className="w-2/5 min-w-[320px] border-r border-gray-200">
                  <JobsTable
                    jobs={jobs}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                    onScan={scan}
                    loading={loading}
                  />
                </div>
                <div className="flex-1 min-w-0">
                  {selectedId ? (
                    <JobDetail jobId={selectedId} onChanged={refresh} />
                  ) : (
                    <div className="flex items-center justify-center h-full text-gray-400 text-sm px-6 text-center">
                      Select a job to see fit, strengths, weaknesses, and the apply gate.
                    </div>
                  )}
                </div>
              </div>
            )}

            {tab === "applications" && (
              <ApplicationsTable applications={applications} onChanged={refresh} />
            )}

            {tab === "profile" && <ProfilePanel onChanged={refresh} />}

            {tab === "upskilling" && <UpskillingPanel />}
          </div>
        </section>
      </main>
    </div>
  );
}

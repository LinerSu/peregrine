import { useCallback, useEffect, useState } from "react";
import { api, type Job } from "./api";
import ChatPanel from "./components/ChatPanel";
import JobsTable from "./components/JobsTable";
import JobDetail from "./components/JobDetail";

export default function App() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    const { jobs } = await api.listJobs();
    setJobs(jobs);
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
      <header className="px-4 py-3 bg-white border-b border-gray-200">
        <h1 className="text-base font-bold">Peregrine</h1>
        <p className="text-xs text-gray-500">Personal AI job-search assistant</p>
      </header>

      <main className="flex flex-1 min-h-0">
        <section className="w-1/3 border-r border-gray-200 bg-white">
          <ChatPanel onAction={refresh} />
        </section>

        <section className="w-1/3 border-r border-gray-200 bg-white">
          <JobsTable
            jobs={jobs}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onScan={scan}
            loading={loading}
          />
        </section>

        <section className="flex-1 bg-white">
          {selectedId ? (
            <JobDetail jobId={selectedId} onChanged={refresh} />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
              Select a job to see fit, strengths, weaknesses, and the apply gate.
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

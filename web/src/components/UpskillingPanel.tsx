import { useState } from "react";
import { api, type Job } from "../api";

interface Gap {
  skill: string;
  why: string;
  how_to_close: string;
}

// Upskilling: pick a job, and the assistant compares its requirements against
// your profile, flags gaps, and suggests how to close them (advisory only).
export default function UpskillingPanel({ jobs }: { jobs: Job[] }) {
  const [jobId, setJobId] = useState("");
  const [busy, setBusy] = useState(false);
  const [summary, setSummary] = useState("");
  const [gaps, setGaps] = useState<Gap[] | null>(null);

  const analyze = async () => {
    if (!jobId || busy) return;
    setBusy(true);
    try {
      const res = await api.upskilling(jobId);
      setSummary(res.summary);
      setGaps(res.missing_skills ?? []);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="h-full overflow-auto p-5">
      <div className="max-w-2xl mx-auto space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-gray-700">Upskilling</h3>
          <p className="text-sm text-gray-500">
            Compare a job's requirements against your profile to see what to learn next.
          </p>
        </div>

        <div className="flex gap-2">
          <select
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            className="flex-1 px-3 py-2 text-sm border border-gray-300 rounded-md bg-white"
          >
            <option value="">Select a job…</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.company} — {j.position}
              </option>
            ))}
          </select>
          <button
            onClick={analyze}
            disabled={busy || !jobId}
            className="px-3 py-2 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Analyzing…" : "Analyze gaps"}
          </button>
        </div>

        {jobs.length === 0 && (
          <p className="text-sm text-gray-400">No jobs yet — scan or ingest one first.</p>
        )}

        {summary && <p className="text-sm text-gray-700 bg-gray-50 rounded-md p-3">{summary}</p>}

        {gaps && (
          <div className="space-y-2">
            {gaps.length === 0 && (
              <p className="text-sm text-green-700">No notable gaps — you're well matched. 🎯</p>
            )}
            {gaps.map((g, i) => (
              <div
                key={i}
                className="rounded-md border border-gray-200 border-l-4 border-l-amber-400 bg-white p-3 shadow-sm"
              >
                <div className="text-sm font-semibold text-gray-800">{g.skill}</div>
                <div className="text-sm text-gray-600 mt-0.5">{g.why}</div>
                <div className="text-sm text-indigo-700 mt-1">→ {g.how_to_close}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

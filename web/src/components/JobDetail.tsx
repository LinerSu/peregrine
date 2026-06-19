import { useEffect, useState } from "react";
import { api, type Job } from "../api";
import JobMarkdown from "./JobMarkdown";

// Job detail with the human-in-the-loop apply gate: the Apply link is only
// revealed after the user reviews strengths / weaknesses / materials and clicks
// "Prepare to apply".
export default function JobDetail({ jobId, onChanged }: { jobId: string; onChanged: () => void }) {
  const [job, setJob] = useState<Job | null>(null);
  const [markdown, setMarkdown] = useState("");
  const [busy, setBusy] = useState(false);
  const [applyUrl, setApplyUrl] = useState<string | null>(null);

  const load = async () => {
    const { job, markdown } = await api.getJob(jobId);
    setJob(job);
    setMarkdown(markdown);
  };

  useEffect(() => {
    setApplyUrl(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  const evaluate = async () => {
    setBusy(true);
    try {
      await api.evaluate(jobId);
      await load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const prepare = async () => {
    setBusy(true);
    try {
      const res = await api.prepare(jobId);
      setApplyUrl(res.apply_url);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const markApplied = async () => {
    setBusy(true);
    try {
      await api.markApplied(jobId);
      await load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  if (!job) return <div className="p-6 text-gray-400">Loading…</div>;

  const applied = job.status === "applied";

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-200">
        <h2 className="text-lg font-semibold">{job.position}</h2>
        <p className="text-sm text-gray-500">
          {job.company} · {job.location || "—"} · fit {job.fit_score != null ? job.fit_score.toFixed(2) : "n/a"}
        </p>
        <div className="flex gap-2 mt-3">
          <button
            onClick={evaluate}
            disabled={busy}
            className="px-3 py-1.5 text-sm font-medium text-white bg-emerald-600 rounded-md hover:bg-emerald-700 disabled:opacity-50"
          >
            {busy ? "Working…" : "Evaluate fit"}
          </button>
          <button
            onClick={prepare}
            disabled={busy}
            className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-100 rounded-md hover:bg-indigo-200 disabled:opacity-50"
          >
            Prepare to apply
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-auto p-4 bg-gray-50">
        <JobMarkdown md={markdown} />
      </div>

      <div className="p-4 border-t border-gray-200 bg-gray-50">
        {applied ? (
          <p className="text-sm text-center font-medium text-blue-700">
            ✓ Applied — tracked in the Applications tab.
          </p>
        ) : applyUrl ? (
          <div className="flex gap-2">
            <a
              href={applyUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 text-center px-4 py-2 text-sm font-semibold text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
            >
              Apply on company site ↗
            </a>
            <button
              onClick={markApplied}
              disabled={busy}
              className="px-4 py-2 text-sm font-semibold text-indigo-700 bg-white border border-indigo-300 rounded-md hover:bg-indigo-50 disabled:opacity-50"
            >
              I applied ✓
            </button>
          </div>
        ) : (
          <p className="text-xs text-center text-gray-500">
            Review strengths, weaknesses &amp; materials above, then click <b>Prepare to apply</b> to unlock the
            Apply link.
          </p>
        )}
      </div>
    </div>
  );
}

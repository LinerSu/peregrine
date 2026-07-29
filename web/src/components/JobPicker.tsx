import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Job } from "../api";
import { relativeTime, statusClass } from "../format";

// Pick a tracked job instead of describing one. Recording an application for a job the
// app already has means retyping company + position, which is both busywork and the only
// reason the backend ever has to GUESS which posting you meant. Here you choose the row,
// so the application is linked by id and there is nothing left to match.
//
// Two postings can share a company AND a title (the same req listed in two cities, or a
// repost), so each row carries what actually separates them — location, posted date, and
// the job id, which the rest of the UI otherwise never shows.
export default function JobPicker({
  onPick,
  emptyHint,
}: {
  onPick: (job: Job) => void;
  emptyHint?: React.ReactNode;
}) {
  const [jobs, setJobs] = useState<Job[] | null>(null);
  const [query, setQuery] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .listJobs()
      .then((r) => setJobs(r.jobs))
      .catch(() => setJobs([]));
    searchRef.current?.focus();
  }, []);

  // Already-applied jobs stay VISIBLE (so you can see the one you're looking for is
  // already tracked) but aren't selectable — a second application for the same posting
  // would just be a duplicate row.
  const applied = (j: Job) => ["applied", "interviewing", "offer", "rejected"].includes(j.status);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const matches = (j: Job) =>
      !q || [j.position, j.company, j.location, j.id].some((v) => (v || "").toLowerCase().includes(q));
    const hits = (jobs || []).filter(matches);
    // Selectable first — the ones you can act on shouldn't sit below the ones you can't.
    return [...hits].sort((a, b) => Number(applied(a)) - Number(applied(b)));
  }, [jobs, query]);

  return (
    <div className="space-y-2">
      <input
        ref={searchRef}
        className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md"
        placeholder="Search your tracked jobs — title, company, location…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      {jobs === null ? (
        <p className="px-1 py-2 text-xs text-gray-500">Loading your jobs…</p>
      ) : rows.length === 0 ? (
        <p className="px-1 py-2 text-xs text-gray-500">
          {jobs.length === 0 ? "No tracked jobs yet. " : "No tracked job matches that. "}
          {emptyHint}
        </p>
      ) : (
        <ul className="max-h-64 overflow-y-auto rounded-md border border-gray-200 bg-white divide-y divide-gray-100">
          {rows.map((j) => {
            const done = applied(j);
            const meta = [
              j.company,
              j.location,
              j.posted_date ? `posted ${relativeTime(j.posted_date)}` : "",
              j.fit_score != null ? `fit ${j.fit_score.toFixed(2)}` : "",
            ].filter(Boolean);
            return (
              <li key={j.id}>
                <button
                  type="button"
                  disabled={done}
                  onClick={() => onPick(j)}
                  title={done ? "Already tracked as an application" : `Record an application for ${j.id}`}
                  className={`w-full px-3 py-2 text-left ${
                    done ? "opacity-60 cursor-not-allowed" : "hover:bg-indigo-50"
                  }`}
                >
                  <div className="flex items-baseline gap-2">
                    <span className="flex-1 text-sm font-medium text-gray-900 truncate">{j.position}</span>
                    {done && (
                      <span className={`px-1.5 py-0.5 text-[10px] rounded-full ${statusClass(j.status)}`}>
                        {j.status}
                      </span>
                    )}
                    <span className="text-[11px] font-mono text-gray-400">{j.id}</span>
                  </div>
                  <div className="text-xs text-gray-500 truncate">{meta.join(" · ")}</div>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

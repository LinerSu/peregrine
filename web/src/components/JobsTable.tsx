import { useEffect, useState } from "react";
import { type Job } from "../api";

export default function JobsTable({
  jobs,
  selectedId,
  onSelect,
  onScan,
  loading,
}: {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onScan: () => void;
  loading: boolean;
}) {
  const [query, setQuery] = useState("");
  const [filtered, setFiltered] = useState<Job[]>(jobs);

  useEffect(() => {
    const q = query.toLowerCase();
    setFiltered(
      q ? jobs.filter((j) => j.company.toLowerCase().includes(q) || j.position.toLowerCase().includes(q)) : jobs
    );
  }, [query, jobs]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 p-3 border-b border-gray-200">
        <input
          className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-md"
          placeholder="Filter jobs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          onClick={onScan}
          disabled={loading}
          className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Scanning…" : "Scan"}
        </button>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 text-gray-600">
            <tr>
              <th className="px-3 py-2 text-left font-medium">Fit</th>
              <th className="px-3 py-2 text-left font-medium">Company</th>
              <th className="px-3 py-2 text-left font-medium">Position</th>
              <th className="px-3 py-2 text-left font-medium">Location</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((j) => (
              <tr
                key={j.id}
                onClick={() => onSelect(j.id)}
                className={`cursor-pointer border-t border-gray-100 hover:bg-indigo-50 ${
                  selectedId === j.id ? "bg-indigo-50" : ""
                }`}
              >
                <td className="px-3 py-2">{j.fit_score != null ? j.fit_score.toFixed(2) : "—"}</td>
                <td className="px-3 py-2 font-medium">{j.company}</td>
                <td className="px-3 py-2">{j.position}</td>
                <td className="px-3 py-2 text-gray-500">{j.location || "—"}</td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-8 text-center text-gray-400">
                  No jobs yet. Ask the assistant to "find jobs matching my CV" or click Scan.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

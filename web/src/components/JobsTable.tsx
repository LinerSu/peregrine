import { useEffect, useMemo, useState } from "react";
import { type Job } from "../api";
import { salaryRange, statusClass } from "../format";

type SortKey = "fit_score" | "company" | "position" | "status" | "salary" | "location";
type SortDir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "fit_score", label: "Fit" },
  { key: "company", label: "Company" },
  { key: "position", label: "Position" },
  { key: "status", label: "Status" },
  { key: "flexibility" as SortKey, label: "Flex" },
  { key: "salary", label: "Salary" },
  { key: "location", label: "Location" },
];

function sortValue(j: Job, key: SortKey): number | string {
  switch (key) {
    case "fit_score":
      return j.fit_score ?? -1;
    case "salary":
      return j.salary_max ?? j.salary_min ?? -1;
    default:
      return (j[key as keyof Job] as string | null)?.toLowerCase?.() ?? "";
  }
}

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
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "fit_score", dir: "desc" });

  const [filtered, setFiltered] = useState<Job[]>(jobs);
  useEffect(() => {
    const q = query.toLowerCase();
    setFiltered(
      q ? jobs.filter((j) => j.company.toLowerCase().includes(q) || j.position.toLowerCase().includes(q)) : jobs
    );
  }, [query, jobs]);

  const rows = useMemo(() => {
    const sorted = [...filtered].sort((a, b) => {
      const av = sortValue(a, sort.key);
      const bv = sortValue(b, sort.key);
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [filtered, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "fit_score" ? "desc" : "asc" }
    );

  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "");

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
              {COLUMNS.map((c) => (
                <th
                  key={c.key}
                  onClick={() => toggleSort(c.key)}
                  className="px-3 py-2 text-left font-medium cursor-pointer select-none hover:text-gray-900 whitespace-nowrap"
                >
                  {c.label}
                  {arrow(c.key)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((j) => (
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
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${statusClass(j.status)}`}>
                    {j.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-500">{j.flexibility || "—"}</td>
                <td className="px-3 py-2 text-gray-500 whitespace-nowrap">
                  {salaryRange(j.salary_min, j.salary_max, j.currency)}
                </td>
                <td className="px-3 py-2 text-gray-500">{j.location || "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-3 py-8 text-center text-gray-400">
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

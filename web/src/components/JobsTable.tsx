import { useMemo, useState } from "react";
import { api, type Job } from "../api";
import { salaryRange, statusClass } from "../format";

type SortKey = "fit_score" | "company" | "position" | "role_category" | "status" | "salary" | "location";
type SortDir = "asc" | "desc";

const COLUMNS: { key: SortKey; label: string }[] = [
  { key: "fit_score", label: "Fit" },
  { key: "company", label: "Company" },
  { key: "position", label: "Position" },
  { key: "role_category", label: "Role" },
  { key: "status", label: "Status" },
  { key: "salary", label: "Salary" },
  { key: "location", label: "Location" },
];

function sortValue(j: Job, key: SortKey): number | string {
  if (key === "fit_score") return j.fit_score ?? -1;
  if (key === "salary") return j.salary_max ?? j.salary_min ?? -1;
  return ((j[key as keyof Job] as string | null) ?? "").toString().toLowerCase();
}

export default function JobsTable({
  jobs,
  selectedId,
  onSelect,
  onScan,
  onChanged,
  loading,
}: {
  jobs: Job[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onScan: () => void;
  onChanged: () => void;
  loading: boolean;
}) {
  const [query, setQuery] = useState("");
  const [role, setRole] = useState("All");
  const [starredOnly, setStarredOnly] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "fit_score", dir: "desc" });

  const roles = useMemo(
    () => ["All", ...Array.from(new Set(jobs.map((j) => j.role_category).filter(Boolean))).sort()],
    [jobs]
  );

  const rows = useMemo(() => {
    const q = query.toLowerCase();
    const filtered = jobs.filter(
      (j) =>
        (!q || j.company.toLowerCase().includes(q) || j.position.toLowerCase().includes(q)) &&
        (role === "All" || j.role_category === role) &&
        (!starredOnly || j.starred)
    );
    return [...filtered].sort((a, b) => {
      const av = sortValue(a, sort.key);
      const bv = sortValue(b, sort.key);
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [jobs, query, role, starredOnly, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) =>
      s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: key === "fit_score" ? "desc" : "asc" }
    );
  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "");

  const toggleStar = async (e: React.MouseEvent, j: Job) => {
    e.stopPropagation();
    await api.updateJob(j.id, { starred: !j.starred });
    onChanged();
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-wrap items-center gap-2 p-3 border-b border-gray-200">
        <input
          className="flex-1 min-w-[120px] px-3 py-1.5 text-sm border border-gray-300 rounded-md"
          placeholder="Filter jobs…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="px-2 py-1.5 text-sm border border-gray-300 rounded-md bg-white"
          title="Filter by role"
        >
          {roles.map((r) => (
            <option key={r} value={r}>
              {r === "All" ? "All roles" : r}
            </option>
          ))}
        </select>
        <button
          onClick={() => setStarredOnly((v) => !v)}
          title="Show starred only"
          className={`px-2 py-1.5 text-sm rounded-md border ${
            starredOnly ? "border-amber-400 bg-amber-50 text-amber-700" : "border-gray-300 text-gray-500"
          }`}
        >
          {starredOnly ? "★" : "☆"}
        </button>
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
              <th className="px-2 py-2"></th>
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
                <td className="px-2 py-2 text-center">
                  <button
                    onClick={(e) => toggleStar(e, j)}
                    title={j.starred ? "Unstar" : "Star"}
                    className={j.starred ? "text-amber-500" : "text-gray-300 hover:text-amber-400"}
                  >
                    {j.starred ? "★" : "☆"}
                  </button>
                </td>
                <td className="px-3 py-2">{j.fit_score != null ? j.fit_score.toFixed(2) : "—"}</td>
                <td className="px-3 py-2 font-medium">{j.company}</td>
                <td className="px-3 py-2">{j.position}</td>
                <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{j.role_category || "—"}</td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 text-xs rounded-full font-medium ${statusClass(j.status)}`}>
                    {j.status}
                  </span>
                </td>
                <td className="px-3 py-2 text-gray-500 whitespace-nowrap">
                  {salaryRange(j.salary_min, j.salary_max, j.currency)}
                </td>
                <td className="px-3 py-2 text-gray-500">{j.location || "—"}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length + 1} className="px-3 py-8 text-center text-gray-400">
                  No jobs match. Adjust filters, or ask the assistant to "find jobs matching my CV".
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

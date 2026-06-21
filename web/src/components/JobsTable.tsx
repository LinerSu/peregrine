import { Fragment, useEffect, useMemo, useState } from "react";
import { api, type Job } from "../api";
import { fitClass, salaryRange, statusClass } from "../format";

type SortKey =
  | "fit_score" | "company" | "position" | "role_category"
  | "status" | "salary" | "location" | "posted_date";
type SortDir = "asc" | "desc";

// Always-on columns are Fit / Company / Position / Status. These are toggleable.
type ColKey = "role_category" | "salary" | "location" | "posted_date";
const OPTIONAL_COLS: { key: ColKey; label: string }[] = [
  { key: "role_category", label: "Role" },
  { key: "salary", label: "Salary" },
  { key: "location", label: "Location" },
  { key: "posted_date", label: "Posted" },
];
const COL_STORAGE = "peregrine.jobcols";

const STATUSES = ["open", "applied", "interviewing", "offer", "rejected", "closed", "removed"];

type Tab = "all" | "open" | "evaluated" | "applied" | "interviewing" | "offer" | "rejected";
const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "open", label: "Open" },
  { key: "evaluated", label: "Evaluated" },
  { key: "applied", label: "Applied" },
  { key: "interviewing", label: "Interviewing" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
];
const matchesTab = (j: Job, tab: Tab) =>
  tab === "all" ? true : tab === "evaluated" ? j.fit_score != null : j.status === tab;

// Order in which status groups appear in the grouped view. ("evaluated" is a
// derived tab, not a real status, so it isn't a group here.)
const GROUP_ORDER = ["interviewing", "offer", "applied", "open", "rejected", "closed", "removed"];

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
  const [tab, setTab] = useState<Tab>("all");
  const [grouped, setGrouped] = useState(false);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [showCols, setShowCols] = useState(false);
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "fit_score", dir: "desc" });
  const [visibleCols, setVisibleCols] = useState<Set<ColKey>>(() => {
    try {
      const saved = localStorage.getItem(COL_STORAGE);
      if (saved) return new Set(JSON.parse(saved) as ColKey[]);
    } catch {
      /* ignore bad localStorage */
    }
    return new Set<ColKey>(["role_category", "salary", "location"]);
  });

  useEffect(() => {
    try {
      localStorage.setItem(COL_STORAGE, JSON.stringify([...visibleCols]));
    } catch {
      /* ignore */
    }
  }, [visibleCols]);

  // Number keys 1-7 select a status tab (ignored while typing in a field).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName)) return;
      const n = Number(e.key);
      if (n >= 1 && n <= TABS.length) setTab(TABS[n - 1].key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const roles = useMemo(
    () => ["All", ...Array.from(new Set(jobs.map((j) => j.role_category).filter(Boolean))).sort()],
    [jobs]
  );

  // Everything except the status tab — so the tab badge counts reflect other filters.
  const baseFiltered = useMemo(() => {
    const q = query.toLowerCase();
    return jobs.filter(
      (j) =>
        (!q || j.company.toLowerCase().includes(q) || j.position.toLowerCase().includes(q)) &&
        (role === "All" || j.role_category === role) &&
        (!starredOnly || j.starred)
    );
  }, [jobs, query, role, starredOnly]);

  // Tab badge counts in a single pass (avoids O(tabs × rows) per render).
  const tabCounts = useMemo(() => {
    const c: Record<Tab, number> = {
      all: 0, open: 0, evaluated: 0, applied: 0, interviewing: 0, offer: 0, rejected: 0,
    };
    for (const j of baseFiltered) {
      c.all += 1;
      if (j.fit_score != null) c.evaluated += 1;
      if (
        j.status === "open" || j.status === "applied" || j.status === "interviewing" ||
        j.status === "offer" || j.status === "rejected"
      ) {
        c[j.status] += 1;
      }
    }
    return c;
  }, [baseFiltered]);

  const rows = useMemo(() => {
    const filtered = baseFiltered.filter((j) => matchesTab(j, tab));
    return [...filtered].sort((a, b) => {
      const av = sortValue(a, sort.key);
      const bv = sortValue(b, sort.key);
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [baseFiltered, tab, sort]);

  const groups = useMemo(() => {
    if (!grouped) return null;
    const byStatus = new Map<string, Job[]>();
    for (const j of rows) {
      const list = byStatus.get(j.status) ?? [];
      list.push(j);
      byStatus.set(j.status, list);
    }
    return GROUP_ORDER.filter((s) => byStatus.has(s)).map((s) => ({ status: s, jobs: byStatus.get(s)! }));
  }, [rows, grouped]);

  const toggleSort = (key: SortKey) =>
    setSort((s) =>
      s.key === key
        ? { key, dir: s.dir === "asc" ? "desc" : "asc" }
        : { key, dir: key === "fit_score" ? "desc" : "asc" }
    );
  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "");
  const toggleStar = async (e: React.MouseEvent, j: Job) => {
    e.stopPropagation();
    await api.updateJob(j.id, { starred: !j.starred });
    onChanged();
  };
  const setStatus = async (id: string, status: string) => {
    setEditingStatus(null);
    await api.updateJob(id, { status });
    onChanged();
  };
  const toggleCol = (k: ColKey) =>
    setVisibleCols((s) => {
      const n = new Set(s);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });
  const colVisible = (k: ColKey) => visibleCols.has(k);
  const colCount = 1 + 4 + visibleCols.size; // star + Fit/Company/Position/Status + optionals

  const sortableTh = (key: SortKey, label: string) => (
    <th
      key={key}
      onClick={() => toggleSort(key)}
      className="px-3 py-2 text-left font-medium cursor-pointer select-none hover:text-gray-900 whitespace-nowrap"
    >
      {label}
      {arrow(key)}
    </th>
  );

  const renderRow = (j: Job) => (
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
      <td className="px-3 py-2">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${fitClass(j.fit_score)}`}>
          {j.fit_score != null ? j.fit_score.toFixed(2) : "—"}
        </span>
      </td>
      <td className="px-3 py-2 font-medium">{j.company}</td>
      <td className="px-3 py-2">{j.position}</td>
      {colVisible("role_category") && (
        <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{j.role_category || "—"}</td>
      )}
      <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
        {editingStatus === j.id ? (
          <select
            autoFocus
            value={j.status}
            onChange={(e) => setStatus(j.id, e.target.value)}
            onBlur={() => setEditingStatus(null)}
            className="text-xs border border-gray-300 rounded px-1 py-0.5 bg-white"
          >
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        ) : (
          <button
            onClick={() => setEditingStatus(j.id)}
            title="Change status"
            className={`px-2 py-0.5 text-xs rounded-full font-medium ${statusClass(j.status)} hover:ring-1 hover:ring-indigo-300`}
          >
            {j.status}
          </button>
        )}
      </td>
      {colVisible("salary") && (
        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">
          {salaryRange(j.salary_min, j.salary_max, j.currency)}
        </td>
      )}
      {colVisible("location") && <td className="px-3 py-2 text-gray-500">{j.location || "—"}</td>}
      {colVisible("posted_date") && (
        <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{j.posted_date || "—"}</td>
      )}
    </tr>
  );

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
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
          onClick={() => setGrouped((v) => !v)}
          title="Group by status"
          className={`px-2 py-1.5 text-sm rounded-md border ${
            grouped ? "border-indigo-400 bg-indigo-50 text-indigo-700" : "border-gray-300 text-gray-500"
          }`}
        >
          Group
        </button>
        <div className="relative">
          <button
            onClick={() => setShowCols((v) => !v)}
            title="Choose columns"
            className="px-2 py-1.5 text-sm rounded-md border border-gray-300 text-gray-500"
          >
            Columns
          </button>
          {showCols && (
            <div className="absolute right-0 z-20 mt-1 w-40 rounded-md border border-gray-200 bg-white p-2 shadow-lg">
              {OPTIONAL_COLS.map((c) => (
                <label key={c.key} className="flex items-center gap-2 px-1 py-1 text-sm text-gray-700">
                  <input type="checkbox" checked={colVisible(c.key)} onChange={() => toggleCol(c.key)} />
                  {c.label}
                </label>
              ))}
            </div>
          )}
        </div>
        <button
          onClick={onScan}
          disabled={loading}
          className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
        >
          {loading ? "Scanning…" : "Scan"}
        </button>
      </div>

      {/* Status tabs */}
      <div className="flex flex-wrap items-center gap-1 px-3 py-2 border-b border-gray-200 bg-white">
        {TABS.map((t) => {
          const n = tabCounts[t.key];
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${
                tab === t.key ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {t.label}
              <span className={`ml-1 ${tab === t.key ? "text-indigo-100" : "text-gray-400"}`}>{n}</span>
            </button>
          );
        })}
      </div>

      <div className="flex-1 overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-gray-50 text-gray-600">
            <tr>
              <th className="px-2 py-2"></th>
              {sortableTh("fit_score", "Fit")}
              {sortableTh("company", "Company")}
              {sortableTh("position", "Position")}
              {colVisible("role_category") && sortableTh("role_category", "Role")}
              {sortableTh("status", "Status")}
              {colVisible("salary") && sortableTh("salary", "Salary")}
              {colVisible("location") && sortableTh("location", "Location")}
              {colVisible("posted_date") && sortableTh("posted_date", "Posted")}
            </tr>
          </thead>
          <tbody>
            {groups
              ? groups.map((g) => (
                  <Fragment key={g.status}>
                    <tr className="bg-gray-50/80">
                      <td colSpan={colCount} className="px-3 py-1.5 text-xs font-semibold text-gray-500">
                        <span className={`px-2 py-0.5 rounded-full ${statusClass(g.status)}`}>{g.status}</span>
                        <span className="ml-2 text-gray-400">{g.jobs.length}</span>
                      </td>
                    </tr>
                    {g.jobs.map(renderRow)}
                  </Fragment>
                ))
              : rows.map(renderRow)}
            {rows.length === 0 && (
              <tr>
                <td colSpan={colCount} className="px-3 py-8 text-center text-gray-400">
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

import { Fragment, useEffect, useMemo, useState } from "react";
import { api, type Job } from "../api";
import { fitClass, salaryRange, statusClass } from "../format";

type SortKey =
  | "fit_score" | "skill_fit" | "company" | "position" | "role_category"
  | "status" | "salary" | "location" | "posted_date";
type SortDir = "asc" | "desc";

// Always-on columns are Fit / Company / Position / Status. These are toggleable.
type ColKey = "skill_fit" | "role_category" | "salary" | "location" | "posted_date";
const OPTIONAL_COLS: { key: ColKey; label: string }[] = [
  { key: "skill_fit", label: "Skill fit" },
  { key: "role_category", label: "Role" },
  { key: "salary", label: "Salary" },
  { key: "location", label: "Location" },
  { key: "posted_date", label: "Posted" },
];
const COL_STORAGE = "peregrine.jobcols";
const SF_MIGRATED = "peregrine.jobcols.sfmigrated"; // one-time: reveal the new Skill-fit column
const SAVED_STORAGE = "peregrine.savedOnly"; // the ★ Saved lens survives reloads

const STATUSES = ["open", "applied", "interviewing", "offer", "rejected", "closed", "removed"];

type Tab = "all" | "open" | "evaluated" | "applied" | "interviewing" | "offer" | "rejected" | "closed";
const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All" },
  { key: "open", label: "Open" },
  { key: "evaluated", label: "Evaluated" },
  { key: "applied", label: "Applied" },
  { key: "interviewing", label: "Interviewing" },
  { key: "offer", label: "Offer" },
  { key: "rejected", label: "Rejected" },
  { key: "closed", label: "Closed" },
];
// Dead = closed (posting gone / auto-pruned) or removed (you removed it). "All" means all
// ACTIVE jobs, so dead ones leave the list; the "Closed" tab is where they go (reviewable
// and recoverable — set the status back to open).
const isDead = (j: Job) => j.status === "closed" || j.status === "removed";
const matchesTab = (j: Job, tab: Tab) =>
  tab === "all" ? !isDead(j)
    : tab === "closed" ? isDead(j)
    : tab === "evaluated" ? j.fit_score != null && !isDead(j)  // dead jobs live only under "Closed"
    : j.status === tab;

// Order in which status groups appear in the grouped view. ("evaluated" is a
// derived tab, not a real status, so it isn't a group here.)
const GROUP_ORDER = ["interviewing", "offer", "applied", "open", "rejected", "closed", "removed"];

function sortValue(j: Job, key: SortKey): number | string {
  if (key === "fit_score") return j.fit_score ?? -1;
  // Coverage first (how qualified), then # of skills matched as a tie-break (more substantive).
  if (key === "skill_fit") return j.skill_fit ? j.skill_fit.score + j.skill_fit.have.length / 1000 : -1;
  if (key === "salary") return j.salary_max ?? j.salary_min ?? -1;
  return ((j[key as keyof Job] as string | null) ?? "").toString().toLowerCase();
}

export default function JobsTable({
  jobs,
  query,
  onQueryChange,
  selectedId,
  onSelect,
  onChanged,
}: {
  jobs: Job[];
  query: string;
  onQueryChange: (q: string) => void;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onChanged: () => void;
}) {
  const [role, setRole] = useState("All");
  const [domain, setDomain] = useState("All");
  const [level, setLevel] = useState("All");
  const [advancedOpen, setAdvancedOpen] = useState(false); // role/domain/degree filters, collapsed
  // The ★ Saved lens — an overlay that composes with the lifecycle tabs (a starred
  // job can be open, applied, …), persisted so the shortlist survives reloads. Safe
  // to restore even with zero starred jobs: the toggle stays visible (amber) to undo.
  const [starredOnly, setStarredOnly] = useState(() => {
    try {
      return localStorage.getItem(SAVED_STORAGE) === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    try {
      localStorage.setItem(SAVED_STORAGE, starredOnly ? "1" : "0");
    } catch {
      /* best-effort */
    }
  }, [starredOnly]);
  const [relevantOnly, setRelevantOnly] = useState(true); // hide off-target (matches your queries)
  const [tab, setTab] = useState<Tab>("all");
  const [grouped, setGrouped] = useState(false);
  const [editingStatus, setEditingStatus] = useState<string | null>(null);
  const [showCols, setShowCols] = useState(false);
  // Default to skill-fit: it's populated for every job (no LLM eval needed), so a new user lands
  // on the roles they best match — fit-first triage. They can still sort by the LLM Fit column.
  const [sort, setSort] = useState<{ key: SortKey; dir: SortDir }>({ key: "skill_fit", dir: "desc" });
  const [visibleCols, setVisibleCols] = useState<Set<ColKey>>(() => {
    const known = new Set(OPTIONAL_COLS.map((c) => c.key));
    try {
      const parsed = JSON.parse(localStorage.getItem(COL_STORAGE) ?? "null") as unknown;
      if (Array.isArray(parsed)) {
        // Keep only known keys, so a stale/edited value can't inflate colSpan.
        const set = new Set(parsed.filter((k): k is ColKey => known.has(k as ColKey)));
        // One-time: surface the new Skill-fit column for users who saved their columns before it
        // existed — otherwise the default skill-fit sort would order by a hidden column with no
        // header/arrow. They can still hide it afterwards (the migration runs once).
        if (!localStorage.getItem(SF_MIGRATED)) {
          set.add("skill_fit");
          try {
            localStorage.setItem(SF_MIGRATED, "1");
          } catch {
            /* best-effort */
          }
        }
        return set;
      }
    } catch {
      /* ignore bad localStorage */
    }
    // Salary is off by default — ATS feeds rarely disclose it, so the column was usually
    // empty and just crowded the table next to the detail panel. Re-enable it via "Columns".
    return new Set<ColKey>(["skill_fit", "role_category", "location"]);
  });

  useEffect(() => {
    try {
      localStorage.setItem(COL_STORAGE, JSON.stringify([...visibleCols]));
    } catch {
      /* ignore */
    }
  }, [visibleCols]);

  // Number keys 1-N select a status tab (ignored while typing in a field).
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
  const splitTags = (s: string) => (s || "").split(",").map((d) => d.trim()).filter(Boolean);
  const domains = useMemo(
    () => ["All", ...Array.from(new Set(jobs.flatMap((j) => splitTags(j.domains)))).sort()],
    [jobs]
  );
  const levels = useMemo(
    () => ["All", ...["PhD", "MS", "BS"].filter((l) => jobs.some((j) => j.level === l))],
    [jobs]
  );
  // After a jobs refresh/prune the available options can shrink — reset a stale domain/degree
  // to "All" so a filter can't strand the table empty with its control hidden.
  useEffect(() => {
    if (role !== "All" && !roles.includes(role)) setRole("All");
    if (domain !== "All" && !domains.includes(domain)) setDomain("All");
    if (level !== "All" && !levels.includes(level)) setLevel("All");
    // Resets are no-ops once the value is valid, so re-listing them can't loop.
  }, [roles, domains, levels, role, domain, level]);

  // Everything except the status tab — so the tab badge counts reflect other filters. The text
  // search runs SERVER-SIDE (App debounces `query` -> /api/jobs?query=…, which matches the full
  // posting incl. the description-keyword index), so `jobs` here is already text-filtered; these
  // are the remaining instant client-side facets.
  const baseFiltered = useMemo(() => {
    return jobs.filter(
      (j) =>
        (role === "All" || j.role_category === role) &&
        (domain === "All" || splitTags(j.domains).includes(domain)) &&
        (level === "All" || j.level === level) &&
        // Relevance hides only LIVE off-target jobs; dead jobs always show (in the Closed tab),
        // so an off-target closed job is never stranded with the toggle hidden. An explicit text
        // search overrides the triage toggle — you asked for these by name, so show them all even
        // if they don't match your configured role queries (the whole point of recall-on-demand).
        // A STAR is the same strength of signal: with the Saved lens on, a starred job must
        // never be relevance-hidden, or the '★ Saved N' label advertises rows the table
        // can't show (worst on reload: persisted lens + default-on relevance = empty table).
        (!relevantOnly || query.trim() !== "" || j.relevant !== false || isDead(j) ||
          (starredOnly && j.starred)) &&
        (!starredOnly || j.starred)
    );
  }, [jobs, query, role, domain, level, relevantOnly, starredOnly]);

  // How many live jobs are off-target (hidden by the relevance toggle) — drives the toggle label.
  const offTargetCount = useMemo(
    () => jobs.filter((j) => j.relevant === false && !isDead(j)).length,
    [jobs]
  );
  // Starred across the jobs the SERVER returned — i.e. the true shortlist size for the
  // current search scope (client-side facets don't affect it, but a text query does:
  // `jobs` is already server-filtered, see the note on the query prop above).
  const savedCount = useMemo(() => jobs.filter((j) => j.starred).length, [jobs]);

  // Tab badge counts in a single pass (avoids O(tabs × rows) per render).
  const tabCounts = useMemo(() => {
    const c: Record<Tab, number> = {
      all: 0, open: 0, evaluated: 0, applied: 0, interviewing: 0, offer: 0, rejected: 0, closed: 0,
    };
    for (const j of baseFiltered) {
      if (isDead(j)) {
        c.closed += 1; // dead jobs only count under "Closed"
        continue;
      }
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
        : { key, dir: key === "fit_score" || key === "skill_fit" ? "desc" : "asc" }
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
          {Number.isFinite(j.fit_score) ? j.fit_score!.toFixed(2) : "—"}
        </span>
      </td>
      <td className="px-3 py-2 font-medium whitespace-nowrap">{j.company}</td>
      <td className="px-3 py-2">
        <div className="line-clamp-2 max-w-[16rem]" title={j.position}>
          {j.position}
        </div>
      </td>
      {colVisible("skill_fit") &&
        (() => {
          const sf = j.skill_fit;
          const total = sf ? sf.have.length + sf.missing.length : 0;
          return (
            <td className="px-3 py-2 whitespace-nowrap">
              {sf && total > 0 ? (
                <span
                  title={`You have: ${sf.have.join(", ") || "none"}${
                    sf.missing.length ? ` · Missing: ${sf.missing.join(", ")}` : ""
                  }`}
                  className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                    sf.score >= 0.75
                      ? "bg-emerald-100 text-emerald-700"
                      : sf.score >= 0.4
                        ? "bg-amber-100 text-amber-700"
                        : "bg-gray-100 text-gray-500"
                  }`}
                >
                  {sf.have.length}/{total}
                </span>
              ) : (
                <span className="text-gray-300">—</span>
              )}
            </td>
          );
        })()}
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
        // below_min_salary is derived server-side from your targets.min_salary. It marks the
        // number, it never hides the row — the floor is a preference, not a fact about the job.
        <td
          className={`px-3 py-2 whitespace-nowrap ${
            j.below_min_salary ? "text-amber-600" : "text-gray-500"
          }`}
          title={j.below_min_salary ? "Below your minimum salary target" : undefined}
        >
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
      {/* Toolbar — ONE wrapping row (search + controls): two stacked full-width bands
          cost ~90px on a pane whose vertical space belongs to the job list. flex-wrap
          is the narrow-width escape hatch — controls wrap, never hide. */}
      <div className="flex flex-wrap items-center gap-1.5 px-2 py-1.5 border-b border-gray-200">
        <input
          className="flex-1 min-w-[9rem] px-2.5 py-1 text-sm border border-gray-300 rounded-md"
          placeholder="Search — company, role, skill, description…"
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
        />
        {/* `|| advancedOpen` keeps the toggle present to CLOSE the panel even if the options
            collapse to one while it's open. */}
        {(roles.length > 1 || domains.length > 1 || levels.length > 1 || advancedOpen) && (
          <button
            onClick={() => setAdvancedOpen((v) => !v)}
            aria-expanded={advancedOpen}
            title="Filter by role / domain / degree"
            className={`px-2 py-1 text-xs rounded-md border ${
              role !== "All" || domain !== "All" || level !== "All"
                ? "border-indigo-400 bg-indigo-50 text-indigo-700"
                : "border-gray-300 text-gray-500"
            }`}
          >
            Filters {advancedOpen ? "▴" : "▾"}
          </button>
        )}
        {offTargetCount > 0 && (
          <button
            onClick={() => setRelevantOnly((v) => !v)}
            title={
              relevantOnly
                ? `Hiding ${offTargetCount} off-target jobs (don't match your scan queries). Click to show all.`
                : "Showing all jobs. Click to hide off-target."
            }
            className={`px-2 py-1 text-xs rounded-md border ${
              relevantOnly
                ? "border-indigo-400 bg-indigo-50 text-indigo-700"
                : "border-gray-300 text-gray-500"
            }`}
          >
            {relevantOnly ? `🎯 ${offTargetCount} hidden` : "🎯 Show all"}
          </button>
        )}
        <button
          onClick={() => setStarredOnly((v) => !v)}
          title={
            starredOnly
              ? "Showing your saved (starred) jobs only. Click to show all."
              : "Show only the jobs you starred"
          }
          className={`px-2 py-1 text-xs rounded-md border ${
            starredOnly ? "border-amber-400 bg-amber-50 text-amber-700" : "border-gray-300 text-gray-500"
          }`}
        >
          {/* Count always shown while the lens is ON — during a text search the server
              scopes `jobs`, and a silently vanishing number reads as a lost shortlist. */}
          {starredOnly ? "★" : "☆"} Saved{starredOnly || savedCount > 0 ? ` ${savedCount}` : ""}
        </button>
        <button
          onClick={() => setGrouped((v) => !v)}
          title="Group by status"
          className={`px-2 py-1 text-xs rounded-md border ${
            grouped ? "border-indigo-400 bg-indigo-50 text-indigo-700" : "border-gray-300 text-gray-500"
          }`}
        >
          Group
        </button>
        <div className="relative">
          <button
            onClick={() => setShowCols((v) => !v)}
            title="Choose columns"
            className="px-2 py-1 text-xs rounded-md border border-gray-300 text-gray-500"
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
      </div>

      {/* Advanced filters — collapsed by default; the list defaults to a skill-fit-ranked,
          relevance-filtered view, so these are power-user tuning, not always on screen. */}
      {advancedOpen && (
        <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b border-gray-100 bg-gray-50">
          <select
            value={role}
            onChange={(e) => setRole(e.target.value)}
            className="px-2 py-1.5 text-sm border border-gray-300 rounded-md bg-white"
            title="Filter by role family"
          >
            {roles.map((r) => (
              <option key={r} value={r}>
                {r === "All" ? "All roles" : r}
              </option>
            ))}
          </select>
          {domains.length > 1 && (
            <select
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
              className="px-2 py-1.5 text-sm border border-gray-300 rounded-md bg-white"
              title="Filter by field / domain"
            >
              {domains.map((d) => (
                <option key={d} value={d}>
                  {d === "All" ? "All domains" : d}
                </option>
              ))}
            </select>
          )}
          {levels.length > 1 && (
            <select
              value={level}
              onChange={(e) => setLevel(e.target.value)}
              className="px-2 py-1.5 text-sm border border-gray-300 rounded-md bg-white"
              title="Filter by required degree"
            >
              {levels.map((l) => (
                <option key={l} value={l}>
                  {l === "All" ? "Any degree" : `🎓 ${l}`}
                </option>
              ))}
            </select>
          )}
          {(role !== "All" || domain !== "All" || level !== "All") && (
            <button
              onClick={() => {
                setRole("All");
                setDomain("All");
                setLevel("All");
              }}
              className="text-xs text-gray-400 hover:text-gray-700"
            >
              clear
            </button>
          )}
        </div>
      )}

      {/* Status tabs */}
      <div className="flex flex-wrap items-center gap-1 px-2 py-1.5 border-b border-gray-200 bg-white">
        {TABS.map((t) => {
          const n = tabCounts[t.key];
          const empty = n === 0 && tab !== t.key; // de-emphasize empty lifecycle tabs (less zero-noise)
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`px-2.5 py-1 text-xs font-medium rounded-full transition-colors ${
                tab === t.key
                  ? "bg-indigo-600 text-white"
                  : empty
                    ? "bg-gray-50 text-gray-400 hover:bg-gray-100"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
              }`}
            >
              {t.label}
              <span
                className={`ml-1 ${tab === t.key ? "text-indigo-100" : empty ? "text-gray-300" : "text-gray-400"}`}
              >
                {n}
              </span>
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
              {colVisible("skill_fit") && sortableTh("skill_fit", "Skill fit")}
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
                  {jobs.length === 0 ? (
                    <>
                      No jobs tracked yet. Click <span className="font-medium text-gray-500">Scan sources</span>{" "}
                      above to fetch from your configured boards, or{" "}
                      <span className="font-medium text-gray-500">Add a job</span> from a URL, pasted text, or a PDF.
                    </>
                  ) : (
                    <>No jobs match. Adjust filters, or ask the assistant to "find jobs matching my CV".</>
                  )}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

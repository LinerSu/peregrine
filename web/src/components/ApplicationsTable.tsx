import { Fragment, useMemo, useState } from "react";
import { api, type Application } from "../api";
import type { AssistantMode } from "../App";
import { salaryRange, statusClass } from "../format";
import JobIngestPanel from "./JobIngestPanel";

const STATUSES = ["applied", "interviewing", "offer", "rejected", "closed"];

type SortKey = "company" | "position" | "status" | "applied_date" | "interview_date";
const SORTABLE: { key: SortKey; label: string }[] = [
  { key: "company", label: "Company" },
  { key: "position", label: "Position" },
  { key: "status", label: "Status" },
  { key: "applied_date", label: "Applied" },
  { key: "interview_date", label: "Interview" },
];

const blankForm = { company: "", position: "", status: "applied", applied_date: "", location: "", url: "" };

// Applications tracker: shows what you applied to and lets you update each one's
// status and details inline. Manual add (for jobs applied to elsewhere), remove,
// filter, and sortable columns.
export default function ApplicationsTable({
  applications,
  mode,
  onChanged,
}: {
  applications: Application[];
  mode: AssistantMode;
  onChanged: () => void;
}) {
  const [savingId, setSavingId] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "applied_date", dir: "desc" });
  const [adding, setAdding] = useState(false);
  const [form, setForm] = useState(blankForm);
  const [addingPostingFor, setAddingPostingFor] = useState<string | null>(null); // orphan id
  const [linkErr, setLinkErr] = useState<string | null>(null);
  const [addingFromPosting, setAddingFromPosting] = useState(false); // add an app from a posting doc
  const [fromPostingErr, setFromPostingErr] = useState<string | null>(null);

  const patch = async (id: string, change: Partial<Application>) => {
    setSavingId(id);
    try {
      await api.updateApplication(id, change);
      onChanged();
    } finally {
      setSavingId(null);
    }
  };

  const remove = async (a: Application) => {
    if (!window.confirm(`Remove ${a.company} — ${a.position} from tracking?`)) return;
    setSavingId(a.id);
    try {
      await api.deleteApplication(a.id);
      onChanged();
    } finally {
      setSavingId(null);
    }
  };

  const save = async () => {
    if (!form.company.trim() || !form.position.trim()) return;
    await api.createApplication(form);
    setForm(blankForm);
    setAdding(false);
    onChanged();
  };

  const rows = useMemo(() => {
    const q = query.toLowerCase();
    const filtered = q
      ? applications.filter((a) =>
          [a.company, a.position, a.status, a.notes].some((v) => (v || "").toLowerCase().includes(q))
        )
      : applications;
    return [...filtered].sort((a, b) => {
      const av = (a[sort.key] || "").toLowerCase();
      const bv = (b[sort.key] || "").toLowerCase();
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sort.dir === "asc" ? cmp : -cmp;
    });
  }, [applications, query, sort]);

  const toggleSort = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, dir: s.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" }));
  const arrow = (key: SortKey) => (sort.key === key ? (sort.dir === "asc" ? " ▲" : " ▼") : "");

  const inp = "px-2 py-1 text-xs border border-gray-300 rounded-md";
  const orphanCount = useMemo(
    () => applications.filter((a) => a.job_tracked === false).length,
    [applications]
  );

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 p-3 border-b border-gray-200">
        <input
          className="flex-1 px-3 py-1.5 text-sm border border-gray-300 rounded-md"
          placeholder="Filter applications…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button
          onClick={() => {
            setAdding((v) => !v);
            setAddingFromPosting(false);
            setAddingPostingFor(null); // all three add UIs are mutually exclusive
          }}
          className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-100 rounded-md hover:bg-indigo-200"
        >
          {adding ? "Cancel" : "+ Add"}
        </button>
        <button
          onClick={() => {
            setAddingFromPosting((v) => !v);
            setAdding(false);
            setAddingPostingFor(null); // one ingest panel at a time (Internal mode shares one marker)
            setFromPostingErr(null);
          }}
          title="Add an application from a job posting you paste, upload (PDF), or link"
          className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md hover:bg-indigo-100"
        >
          {addingFromPosting ? "Cancel" : "+ From posting"}
        </button>
      </div>

      {orphanCount > 0 && (
        <div className="px-3 py-1.5 text-xs text-amber-700 bg-amber-50 border-b border-amber-100">
          {orphanCount} application{orphanCount > 1 ? "s have" : " has"} no linked posting — click{" "}
          <span className="font-medium">⚠ add posting</span> on a row to add it (then you can evaluate it and
          tailor a CV for it).
        </div>
      )}

      {adding && (
        <div className="flex flex-wrap items-center gap-2 p-3 bg-indigo-50 border-b border-gray-200">
          <input className={inp} placeholder="Company *" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} />
          <input className={inp} placeholder="Position *" value={form.position} onChange={(e) => setForm({ ...form, position: e.target.value })} />
          <select className={inp} value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <input className={inp} type="date" value={form.applied_date} onChange={(e) => setForm({ ...form, applied_date: e.target.value })} />
          <input className={inp} placeholder="Location" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
          <input className={`${inp} w-48`} placeholder="Posting URL" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} />
          <button
            onClick={save}
            disabled={!form.company.trim() || !form.position.trim()}
            className="px-3 py-1 text-xs font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            Save
          </button>
        </div>
      )}

      {addingFromPosting && (
        <div className="p-3 bg-indigo-50 border-b border-gray-200">
          <p className="mb-2 text-xs text-gray-600">
            Add a posting you applied to — paste it, upload a PDF, or give a URL. It's parsed into a tracked
            job and logged as an application (status "applied"), so it's never an orphan.
          </p>
          <JobIngestPanel
            mode={mode}
            textPlaceholder="Paste the job posting you applied to (or save the page as PDF and upload it)…"
            onIngested={async (jobId) => {
              try {
                await api.markApplied(jobId);
                setFromPostingErr(null);
                setAddingFromPosting(false);
                onChanged();
              } catch {
                setFromPostingErr(
                  "The job was added, but logging the application failed — refresh and mark it applied."
                );
              }
            }}
          />
          {fromPostingErr && <p className="mt-2 text-xs text-rose-600">{fromPostingErr}</p>}
        </div>
      )}

      <div className="flex-1 overflow-auto">
        {rows.length === 0 ? (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm px-6 text-center">
            {applications.length === 0
              ? 'No applications yet. Mark a job applied, or click "+ Add" to track one you applied to elsewhere.'
              : "No applications match the filter."}
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-gray-50 text-gray-600">
              <tr>
                {SORTABLE.map((c) => (
                  <th
                    key={c.key}
                    onClick={() => toggleSort(c.key)}
                    className="px-3 py-2 text-left font-medium cursor-pointer select-none hover:text-gray-900 whitespace-nowrap"
                  >
                    {c.label}
                    {arrow(c.key)}
                  </th>
                ))}
                <th className="px-3 py-2 text-left font-medium">Salary</th>
                <th className="px-3 py-2 text-left font-medium">Contacts</th>
                <th className="px-3 py-2 text-left font-medium">Notes</th>
                <th className="px-3 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <Fragment key={a.id}>
                <tr className="border-t border-gray-100 align-top">
                  <td className="px-3 py-2 font-medium">
                    {a.company}
                    {a.job_tracked === false && (
                      <button
                        type="button"
                        onClick={() => {
                          setLinkErr(null); // don't carry one row's error to another
                          setAddingFromPosting(false); // all three add UIs are mutually exclusive
                          setAdding(false);
                          setAddingPostingFor((id) => (id === a.id ? null : a.id));
                        }}
                        title="No tracked posting backs this application — click to add the job posting (URL / paste / PDF) and link it"
                        className="ml-1.5 px-1.5 py-0.5 text-[10px] rounded-full bg-amber-100 text-amber-700 hover:bg-amber-200 align-middle"
                      >
                        {addingPostingFor === a.id ? "× cancel" : "⚠ add posting"}
                      </button>
                    )}
                  </td>
                  <td className="px-3 py-2">{a.position}</td>
                  <td className="px-3 py-2">
                    <select
                      value={a.status}
                      disabled={savingId === a.id}
                      onChange={(e) => patch(a.id, { status: e.target.value })}
                      className={`px-2 py-1 text-xs rounded-md border-0 font-medium ${statusClass(a.status)}`}
                    >
                      {STATUSES.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  </td>
                  <td className="px-3 py-2 text-gray-500 whitespace-nowrap">{a.applied_date || "—"}</td>
                  <td className="px-3 py-2">
                    <input
                      type="date"
                      value={a.interview_date || ""}
                      disabled={savingId === a.id}
                      onChange={(e) => patch(a.id, { interview_date: e.target.value })}
                      className={inp}
                    />
                  </td>
                  <td className="px-3 py-2 text-gray-500 whitespace-nowrap">
                    {salaryRange(a.salary_min, a.salary_max, a.currency)}
                  </td>
                  <td className="px-3 py-2">
                    <input
                      defaultValue={a.contacts}
                      placeholder="recruiter…"
                      disabled={savingId === a.id}
                      onBlur={(e) => e.target.value !== a.contacts && patch(a.id, { contacts: e.target.value })}
                      className={`${inp} w-32`}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <input
                      defaultValue={a.notes}
                      placeholder="notes…"
                      disabled={savingId === a.id}
                      onBlur={(e) => e.target.value !== a.notes && patch(a.id, { notes: e.target.value })}
                      className={`${inp} w-44`}
                    />
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    {a.url && (
                      <a href={a.url} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline mr-2">
                        ↗
                      </a>
                    )}
                    <button
                      onClick={() => remove(a)}
                      disabled={savingId === a.id}
                      title="Remove from tracking"
                      className="text-gray-400 hover:text-rose-600 disabled:opacity-50"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
                {addingPostingFor === a.id && (
                  <tr className="bg-amber-50/50">
                    <td colSpan={9} className="px-3 py-3 border-t border-amber-100">
                      <p className="mb-2 text-xs text-gray-600">
                        Add the posting for{" "}
                        <span className="font-medium">{a.company} — {a.position}</span>; it will be
                        parsed into a tracked job and linked here (this row will then show the
                        posting's company &amp; title).
                      </p>
                      {/* Only one ingest panel is mounted at a time — addingPostingFor holds a
                          single id, and AddJobsBar lives on another tab — so the shared Internal
                          ingest marker can't resolve two applications to the same job. */}
                      <JobIngestPanel
                        mode={mode}
                        textPlaceholder={`Paste the ${a.company} job posting (or save the page as PDF and upload it)…`}
                        onIngested={async (jobId) => {
                          try {
                            await api.linkApplication(a.id, jobId);
                            setLinkErr(null);
                            setAddingPostingFor(null);
                            onChanged();
                          } catch {
                            setLinkErr(
                              "The job was added but couldn't be linked to this application — refresh and try the badge again."
                            );
                          }
                        }}
                      />
                      {linkErr && <p className="mt-2 text-xs text-rose-600">{linkErr}</p>}
                    </td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

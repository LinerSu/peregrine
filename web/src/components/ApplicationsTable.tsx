import { Fragment, useMemo, useState } from "react";
import { api, type Application, type Job } from "../api";
import type { AssistantMode } from "../App";
import { safeHttpUrl, salaryRange, statusClass } from "../format";
import JobIngestPanel from "./JobIngestPanel";
import JobPicker from "./JobPicker";
import ContactsEditor from "./ContactsEditor";
import AgentPromptModal from "./AgentPromptModal";
import { APPLICATION_AGENT_PROMPT } from "../prompts";

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
// What a PICKED job doesn't already know: the job supplies company/position/url/location.
const blankPicked = { status: "applied", applied_date: "", notes: "" };

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
  const [picked, setPicked] = useState<Job | null>(null);   // chosen from the tracked jobs
  const [pickedForm, setPickedForm] = useState(blankPicked);
  const [manual, setManual] = useState(false);              // "not in my list" escape hatch
  const [addingPostingFor, setAddingPostingFor] = useState<string | null>(null); // orphan id
  const [linkErr, setLinkErr] = useState<string | null>(null);
  const [addingFromPosting, setAddingFromPosting] = useState(false); // add an app from a posting doc
  const [showAgentPrompt, setShowAgentPrompt] = useState(false);
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

  const closeAdd = () => {
    setAdding(false);
    setPicked(null);
    setPickedForm(blankPicked);
    setManual(false);
    setForm(blankForm);
  };

  const save = async () => {
    if (!form.company.trim() || !form.position.trim()) return;
    await api.createApplication(form);
    closeAdd();
    onChanged();
  };

  // Linked by id: the posting was chosen, so nothing about it has to be matched.
  const savePicked = async () => {
    if (!picked) return;
    await api.createApplication({ job_id: picked.id, ...pickedForm });
    closeAdd();
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
            if (adding) closeAdd();
            else setAdding(true);
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
        <button
          onClick={() => setShowAgentPrompt(true)}
          title="Get a prompt for another AI agent that writes up an application you submitted, in this app's fields"
          className="px-2 py-1.5 text-xs font-medium text-gray-600 border border-gray-300 rounded-md hover:bg-gray-50"
        >
          🤖 Agent prompt
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
        <div className="p-3 space-y-2 bg-indigo-50 border-b border-gray-200">
          {picked ? (
            /* A tracked job was chosen — only the application's own facts are left to fill in. */
            <>
              <div className="flex items-baseline gap-2">
                <span className="text-sm font-medium text-gray-900 truncate">{picked.position}</span>
                <span className="text-xs text-gray-500 truncate">— {picked.company}</span>
                <span className="text-[11px] font-mono text-gray-400">{picked.id}</span>
                <button onClick={() => setPicked(null)} className="ml-auto text-xs text-indigo-700 hover:underline">
                  change job
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <label className="text-xs text-gray-600">Applied</label>
                <input
                  className={inp}
                  type="date"
                  value={pickedForm.applied_date}
                  onChange={(e) => setPickedForm({ ...pickedForm, applied_date: e.target.value })}
                />
                <select
                  className={inp}
                  value={pickedForm.status}
                  onChange={(e) => setPickedForm({ ...pickedForm, status: e.target.value })}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>{s}</option>
                  ))}
                </select>
                <input
                  className={`${inp} flex-1 min-w-[12rem]`}
                  placeholder="Notes — referral, confirmation number, which CV you sent…"
                  value={pickedForm.notes}
                  onChange={(e) => setPickedForm({ ...pickedForm, notes: e.target.value })}
                />
                <button
                  onClick={savePicked}
                  className="px-3 py-1 text-xs font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700"
                >
                  Save
                </button>
              </div>
              <p className="text-[11px] text-gray-500">
                Company, position, location and the posting link come from the tracked job — this application is
                linked to it by id, and the job moves to <b>{pickedForm.status}</b>. Blank date = today.
              </p>
            </>
          ) : manual ? (
            /* Applied somewhere never tracked: describe it. It still links itself later,
               when the posting is added (the job adopts a matching application). */
            <>
              <div className="flex flex-wrap items-center gap-2">
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
              <button onClick={() => setManual(false)} className="text-xs text-indigo-700 hover:underline">
                ← pick from my tracked jobs instead
              </button>
            </>
          ) : (
            <>
              <p className="text-xs text-gray-600">Which job did you apply to?</p>
              <JobPicker
                onPick={setPicked}
                applications={applications}
                emptyHint={
                  <button onClick={() => setManual(true)} className="text-indigo-700 hover:underline">
                    Enter it manually
                  </button>
                }
              />
              <button onClick={() => setManual(true)} className="text-xs text-indigo-700 hover:underline">
                Not in my list — enter it manually
              </button>
            </>
          )}
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
                <th className="px-3 py-2 text-left font-medium">People</th>
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
                  <td className="px-3 py-2">
                    {/* Editable: '+ From posting' stamps TODAY via mark_applied, but the
                        real submission may be older (e.g. agent-recorded) — and
                        applied_date feeds the outcomes/response-window analytics. */}
                    <input
                      type="date"
                      value={a.applied_date || ""}
                      disabled={savingId === a.id}
                      onChange={(e) => patch(a.id, { applied_date: e.target.value })}
                      className={inp}
                    />
                  </td>
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
                  <td className="px-3 py-2 min-w-[16rem]">
                    <ContactsEditor key={`${a.id}:${a.people}`} value={a} onSave={(f) => patch(a.id, f)} />
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
                    {/* never render a non-http(s) scheme as a link — the row's url came
                        from a posting, and React happily emits a javascript: href */}
                    {safeHttpUrl(a.url) && (
                      <a href={safeHttpUrl(a.url)} target="_blank" rel="noopener noreferrer" className="text-indigo-600 hover:underline mr-2">
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

      {showAgentPrompt && (
        <AgentPromptModal
          title="Prompt an agent to write up a submitted application"
          prompt={APPLICATION_AGENT_PROMPT}
          hint='If its output includes the Posting section, use "+ From posting" with that text, then edit the row: set the real Applied date (it defaults to today), interview date, people, and notes. Otherwise use "+ Add" for the basics and edit the rest inline.'
          onClose={() => setShowAgentPrompt(false)}
        />
      )}
    </div>
  );
}

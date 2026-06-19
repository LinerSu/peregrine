import { useState } from "react";
import { api, type Application } from "../api";
import { salaryRange, statusClass } from "../format";

const STATUSES = ["applied", "interviewing", "offer", "rejected", "closed"];

// Applications tracker: one row per job the user has applied to. Status,
// interview date, contacts and notes are editable inline and persisted via
// PATCH /api/applications/{id}.
export default function ApplicationsTable({
  applications,
  onChanged,
}: {
  applications: Application[];
  onChanged: () => void;
}) {
  const [savingId, setSavingId] = useState<string | null>(null);

  const patch = async (id: string, change: Partial<Application>) => {
    setSavingId(id);
    try {
      await api.updateApplication(id, change);
      onChanged();
    } finally {
      setSavingId(null);
    }
  };

  if (applications.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm px-6 text-center">
        No applications yet. Open a job, click <b className="mx-1">Prepare to apply</b>, then
        <b className="mx-1">Mark as applied</b> to start tracking it here.
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-gray-50 text-gray-600">
          <tr>
            <th className="px-3 py-2 text-left font-medium">Company</th>
            <th className="px-3 py-2 text-left font-medium">Position</th>
            <th className="px-3 py-2 text-left font-medium">Status</th>
            <th className="px-3 py-2 text-left font-medium">Applied</th>
            <th className="px-3 py-2 text-left font-medium">Interview</th>
            <th className="px-3 py-2 text-left font-medium">Salary</th>
            <th className="px-3 py-2 text-left font-medium">Contacts</th>
            <th className="px-3 py-2 text-left font-medium">Notes</th>
            <th className="px-3 py-2 text-left font-medium"></th>
          </tr>
        </thead>
        <tbody>
          {applications.map((a) => (
            <tr key={a.id} className="border-t border-gray-100 align-top">
              <td className="px-3 py-2 font-medium">{a.company}</td>
              <td className="px-3 py-2">{a.position}</td>
              <td className="px-3 py-2">
                <select
                  value={a.status}
                  disabled={savingId === a.id}
                  onChange={(e) => patch(a.id, { status: e.target.value })}
                  className={`px-2 py-1 text-xs rounded-md border-0 font-medium ${statusClass(a.status)}`}
                >
                  {STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
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
                  className="px-2 py-1 text-xs border border-gray-200 rounded-md"
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
                  className="w-32 px-2 py-1 text-xs border border-gray-200 rounded-md"
                />
              </td>
              <td className="px-3 py-2">
                <input
                  defaultValue={a.notes}
                  placeholder="notes…"
                  disabled={savingId === a.id}
                  onBlur={(e) => e.target.value !== a.notes && patch(a.id, { notes: e.target.value })}
                  className="w-44 px-2 py-1 text-xs border border-gray-200 rounded-md"
                />
              </td>
              <td className="px-3 py-2">
                {a.url && (
                  <a
                    href={a.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-indigo-600 hover:underline whitespace-nowrap"
                  >
                    posting ↗
                  </a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

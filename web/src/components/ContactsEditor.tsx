import { useState } from "react";

// People you found yourself — USER-ENTERED, never scraped. A flexible LIST so you record only
// what you actually know: often just a recruiter's name + email; the manager may be unknown.
// Reused on the Job detail and the Applications view; the backend keeps a linked job +
// application in sync, so it reads the same wherever you edit it. Stored as JSON in `people`.
export interface Contact {
  name: string;
  role?: string; // recruiter / hiring manager / referral / … (free text, optional)
  link?: string; // email or URL (optional)
}

function parse(people?: string): Contact[] {
  try {
    const v = JSON.parse(people || "[]");
    if (!Array.isArray(v)) return [];
    // Coerce every field to a string (stored JSON could carry non-strings) and keep any entry
    // with content — a contact may be just a name, just a link, or just a role (no required field).
    return v
      .filter((c) => c && typeof c === "object")
      .map((c) => ({ name: String(c.name ?? ""), role: String(c.role ?? ""), link: String(c.link ?? "") }))
      .filter((c) => c.name || c.role || c.link);
  } catch {
    return [];
  }
}

// Only render a link for something that's clearly a URL / email — never a javascript: href.
function safeUrl(u?: string): string | undefined {
  const s = (u || "").trim();
  if (!s) return undefined;
  if (/^(https?:|mailto:)/i.test(s)) return s;
  if (/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s)) return `mailto:${s}`; // bare email
  if (/^[\w.-]+\.[a-z]{2,}(\/\S*)?$/i.test(s)) return `https://${s}`; // bare domain/path
  return undefined;
}

export default function ContactsEditor({
  value,
  onSave,
}: {
  value: { people?: string };
  onSave: (fields: { people: string }) => Promise<void>;
}) {
  const [list, setList] = useState<Contact[]>(parse(value.people));
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Contact[]>([]);
  const [busy, setBusy] = useState(false);

  const startEdit = () => {
    const cur = parse(value.people);
    setDraft(cur.length ? cur : [{ name: "", role: "", link: "" }]);
    setEditing(true);
  };
  const save = async () => {
    setBusy(true);
    try {
      const clean = draft
        .map((c) => ({ name: c.name.trim(), role: (c.role || "").trim(), link: (c.link || "").trim() }))
        .filter((c) => c.name || c.link); // drop empty rows
      await onSave({ people: JSON.stringify(clean) });
      setList(clean);
      setEditing(false);
    } finally {
      setBusy(false);
    }
  };
  const set = (i: number, patch: Partial<Contact>) =>
    setDraft((d) => d.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  const inp = "px-2 py-1 text-xs border border-gray-300 rounded";

  if (!editing) {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {list.map((c, i) => {
          const href = safeUrl(c.link);
          return (
            <span key={i} className="text-xs">
              <span className="text-gray-700">{c.name || "(unnamed)"}</span>
              {c.role && <span className="text-gray-400"> · {c.role}</span>}
              {href && (
                <a href={href} target="_blank" rel="noopener noreferrer" className="ml-1 text-indigo-600 hover:underline">
                  ↗
                </a>
              )}
            </span>
          );
        })}
        <button onClick={startEdit} className="text-xs text-indigo-600 hover:underline">
          {list.length ? "edit" : "+ add people"}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {draft.map((c, i) => (
        <div key={i} className="flex flex-wrap items-center gap-1.5">
          <input
            className={`${inp} flex-1 min-w-[7rem]`}
            placeholder="Name"
            value={c.name}
            onChange={(e) => set(i, { name: e.target.value })}
          />
          <input
            className={`${inp} w-28`}
            placeholder="role (optional)"
            list="contact-roles"
            value={c.role ?? ""}
            onChange={(e) => set(i, { role: e.target.value })}
          />
          <input
            className={`${inp} flex-1 min-w-[8rem]`}
            placeholder="email or LinkedIn (optional)"
            value={c.link ?? ""}
            onChange={(e) => set(i, { link: e.target.value })}
          />
          <button
            onClick={() => setDraft((d) => d.filter((_, j) => j !== i))}
            title="Remove"
            className="text-xs text-gray-400 hover:text-red-600"
          >
            ✕
          </button>
        </div>
      ))}
      <datalist id="contact-roles">
        <option value="Recruiter" />
        <option value="Hiring manager" />
        <option value="Referral" />
      </datalist>
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setDraft((d) => [...d, { name: "", role: "", link: "" }])}
          className="text-xs text-indigo-600 hover:underline"
        >
          + add another
        </button>
        <span className="flex-1" />
        <button
          onClick={save}
          disabled={busy}
          className="px-2.5 py-1 text-xs font-medium text-white bg-indigo-600 rounded hover:bg-indigo-700 disabled:opacity-50"
        >
          {busy ? "Saving…" : "Save"}
        </button>
        <button onClick={() => setEditing(false)} className="text-xs text-gray-400 hover:text-gray-700">
          cancel
        </button>
      </div>
      <p className="text-[10px] text-gray-400">You enter these — never scraped. Add only what you know.</p>
    </div>
  );
}

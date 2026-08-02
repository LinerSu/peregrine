import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api";

type Coverage = Awaited<ReturnType<typeof api.coverage>>;
type EvidenceFile = { name: string; bytes: number; passages: number };

const LEVEL_STYLE: Record<Coverage["level"], string> = {
  empty: "border-rose-200 bg-rose-50 text-rose-800",
  thin: "border-amber-200 bg-amber-50 text-amber-800",
  ok: "border-sky-200 bg-sky-50 text-sky-800",
  rich: "border-emerald-200 bg-emerald-50 text-emerald-800",
};

// Everything the app generates is bounded by how much of you it holds, and until now the
// only way to give it more was to copy files into data/evidence/ by hand and hand-edit a
// line of YAML. That's fine if you already know the layout; it's an invisible feature to
// everyone else — and the nudge on the job page pointed at something the UI couldn't do.
export default function BackgroundPanel() {
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [files, setFiles] = useState<EvidenceFile[]>([]);
  const [goal, setGoal] = useState("");
  const [savedGoal, setSavedGoal] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    const [ev, prefs] = await Promise.all([
      api.listEvidence().catch(() => null),
      api.getPreferences().catch(() => null),
    ]);
    if (ev) {
      setFiles(ev.files);
      setCoverage(ev.coverage);
    }
    const g = ((prefs as Record<string, unknown> | null)?.goal as string) || "";
    setGoal(g);
    setSavedGoal(g);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const upload = async (list: FileList | null) => {
    if (!list?.length) return;
    setBusy(true);
    setMsg("");
    try {
      const results = [];
      for (const f of Array.from(list)) {
        try {
          results.push(await api.uploadEvidence(f));
        } catch (e) {
          results.push({ name: f.name, error: e instanceof Error ? e.message : "failed" });
        }
      }
      // Passage count, not file count: a slide deck with six words a page uploads fine and
      // contributes nothing, and saying "added 1 file" would hide that.
      const ok = results.filter((r) => !("error" in r));
      const empty = ok.filter((r) => "passages" in r && !r.passages).length;
      const failed = results.find((r) => "error" in r) as { error: string } | undefined;
      setMsg(
        failed
          ? failed.error
          : `Added ${ok.length} file${ok.length > 1 ? "s" : ""}.` +
            (empty ? ` ${empty} had no readable text — mostly images or slides?` : "")
      );
      await load();
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const remove = async (name: string) => {
    if (!window.confirm(`Remove ${name} from your evidence library?`)) return;
    setBusy(true);
    try {
      await api.deleteEvidence(name);
      await load();
    } finally {
      setBusy(false);
    }
  };

  const saveGoal = async () => {
    setBusy(true);
    try {
      const prefs = (await api.getPreferences().catch(() => ({}))) as Record<string, unknown>;
      await api.savePreferences({ ...prefs, goal: goal.trim() } as never);
      setSavedGoal(goal.trim());
      setMsg("Goal saved.");
      await load();
    } finally {
      setBusy(false);
    }
  };

  const kb = (n: number) => (n < 1024 ? `${n} B` : `${Math.round(n / 1024)} KB`);

  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-gray-800">What Peregrine knows about you</h3>
        <p className="text-xs text-gray-500">
          Fit scores, letters and tailored CVs can only use what's here. A CV alone lets them
          restate your résumé; your own writing is what makes them specific.
        </p>
      </div>

      {coverage && (
        <p className={`rounded-md border px-3 py-2 text-xs ${LEVEL_STYLE[coverage.level]}`}>
          {coverage.message}
        </p>
      )}

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          Your evidence — project write-ups, papers, talk notes, design docs
        </label>
        <input
          ref={fileRef}
          type="file"
          multiple
          accept=".md,.markdown,.txt,.tex,.pdf"
          disabled={busy}
          onChange={(e) => upload(e.target.files)}
          className="block w-full text-xs text-gray-600 file:mr-3 file:rounded-md file:border-0 file:bg-indigo-50 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-indigo-700 hover:file:bg-indigo-100"
        />
        <p className="mt-1 text-[11px] text-gray-400">
          Stored in <code>data/evidence/</code> on your machine — gitignored, never uploaded
          anywhere. You can also just copy files there directly.
        </p>
      </div>

      {files.length > 0 && (
        <ul className="rounded-md border border-gray-200 divide-y divide-gray-100">
          {files.map((f) => (
            <li key={f.name} className="flex items-center gap-2 px-3 py-1.5 text-xs">
              <span className="flex-1 truncate text-gray-800">{f.name}</span>
              <span className={f.passages ? "text-gray-500" : "text-amber-700"}>
                {f.passages ? `${f.passages} passage${f.passages > 1 ? "s" : ""}` : "no readable text"}
              </span>
              <span className="text-gray-400">{kb(f.bytes)}</span>
              <button
                onClick={() => remove(f.name)}
                disabled={busy}
                className="text-gray-400 hover:text-rose-600 disabled:opacity-50"
                aria-label={`Remove ${f.name}`}
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}

      <div>
        <label className="block text-xs font-medium text-gray-600 mb-1">
          What you want next — the one thing no CV contains
        </label>
        <textarea
          className="w-full h-16 px-3 py-2 text-sm border border-gray-300 rounded-md resize-y"
          placeholder="e.g. Move from research prototypes into tooling that ships to other engineers — I want the analysis I build to run in someone's CI, not just in a paper."
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
        />
        <div className="mt-1 flex items-center gap-2">
          <button
            onClick={saveGoal}
            disabled={busy || goal.trim() === savedGoal}
            className="px-3 py-1 text-xs font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            Save goal
          </button>
          <span className="text-[11px] text-gray-400">
            Used for the forward-looking paragraph in cover letters.
          </span>
        </div>
      </div>

      {msg && <p className="text-xs text-gray-500">{msg}</p>}
    </section>
  );
}

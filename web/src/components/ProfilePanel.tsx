import { useEffect, useRef, useState } from "react";
import { api, type Profile } from "../api";
import type { AssistantMode } from "../App";

// Profile / CV tab. CV intake is mode-aware:
//   External — POST /api/cv (LLM parses the CV into the profile).
//   Internal — the raw CV is stashed (store-only), then you run one line in the
//   Claude terminal; this panel polls the profile and reflects Claude's save.
export default function ProfilePanel({
  onChanged,
  mode,
}: {
  onChanged: () => void;
  mode: AssistantMode;
}) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [cv, setCv] = useState("");
  const [busy, setBusy] = useState(false);
  const [cvPrompt, setCvPrompt] = useState(""); // Internal: the line to run
  const [waiting, setWaiting] = useState(false); // Internal: polling for Claude's save
  const [copied, setCopied] = useState(false);
  const baseline = useRef(""); // serialized profile before the parse
  const modeRef = useRef(mode); // current mode, for async guards (closures go stale)
  modeRef.current = mode;

  const load = async () => setProfile(await api.getProfile());

  useEffect(() => {
    load();
  }, []);

  // Internal: poll until the profile changes (Claude saved it).
  useEffect(() => {
    if (!waiting) return;
    const started = Date.now();
    let inFlight = false;
    let live = true;
    const id = setInterval(async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const p = await api.getProfile().catch(() => null);
        if (!live) return;
        if (p && JSON.stringify(p) !== baseline.current) {
          setProfile(p);
          onChanged();
          setWaiting(false);
        } else if (Date.now() - started > 180_000) {
          setWaiting(false);
        }
      } finally {
        inFlight = false;
      }
    }, 3000);
    return () => {
      live = false;
      clearInterval(id);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [waiting]);

  // Switching the global mode mid-wait must not leave a dangling poll/prompt
  // (which would disable the External button with no explanation).
  useEffect(() => {
    setWaiting(false);
    setCvPrompt("");
  }, [mode]);

  // Internal: after stashing the raw CV, show the guided prompt and start polling.
  // Capture the baseline from a FRESH server read (not React state, which may not
  // have loaded yet) so the poll can't resolve instantly without Claude saving.
  const startInternal = async () => {
    const p = await api.getProfile().catch(() => profile ?? {});
    if (modeRef.current !== "internal") return; // user flipped to External mid-stash
    baseline.current = JSON.stringify(p ?? {});
    setCvPrompt("parse my cv");
    setCopied(false);
    setWaiting(true);
  };

  const submit = async () => {
    if (!cv.trim() || busy || waiting) return;
    if (mode === "internal") {
      setBusy(true);
      try {
        await api.saveCvSource(cv);
      } finally {
        setBusy(false);
      }
      await startInternal();
      return;
    }
    setBusy(true);
    try {
      await api.submitCv(cv);
      setCv("");
      await load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file || busy || waiting) return;
    if (mode === "internal") {
      setBusy(true);
      try {
        await api.uploadCvSource(file);
      } finally {
        setBusy(false);
      }
      await startInternal();
      return;
    }
    setBusy(true);
    try {
      await api.uploadCv(file);
      await load();
      onChanged();
    } finally {
      setBusy(false);
    }
  };

  const skills = profile?.skills ?? [];

  return (
    <div className="h-full overflow-auto p-5 space-y-6">
      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Profile</h3>
        {profile && (profile.name || skills.length > 0) ? (
          <div className="space-y-3">
            <div>
              <div className="text-lg font-semibold">{profile.name || "—"}</div>
              {profile.headline && <div className="text-sm text-gray-600">{profile.headline}</div>}
              {profile.location && <div className="text-xs text-gray-400">{profile.location}</div>}
            </div>
            {skills.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {skills.map((s, i) => (
                  <span
                    key={i}
                    title={s.evidence}
                    className="px-2 py-0.5 text-xs rounded-full bg-indigo-50 text-indigo-700"
                  >
                    {s.name}
                    {s.level ? ` · ${s.level}` : ""}
                  </span>
                ))}
              </div>
            )}
          </div>
        ) : (
          <p className="text-sm text-gray-400">No profile yet — paste your CV below to build one.</p>
        )}
      </section>

      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Upload CV</h3>
        <label className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md cursor-pointer hover:bg-indigo-100">
          {busy ? "Working…" : waiting ? "Waiting…" : "Choose file (PDF, .txt, .md)"}
          <input
            type="file"
            accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
            className="hidden"
            disabled={busy || waiting}
            onChange={(e) => upload(e.target.files?.[0])}
          />
        </label>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">…or paste CV</h3>
        <textarea
          className="w-full h-48 px-3 py-2 text-sm border border-gray-300 rounded-md resize-y font-mono"
          placeholder="Paste your CV / resume text here…"
          value={cv}
          onChange={(e) => setCv(e.target.value)}
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={submit}
            disabled={busy || waiting || !cv.trim()}
            className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Saving…" : waiting ? "Waiting…" : mode === "internal" ? "Parse CV (Claude)" : "Parse CV → profile"}
          </button>
          <span className="text-xs text-gray-400">
            Stored locally in <code>config/profile.yml</code>. Used to score fit.
          </span>
        </div>
      </section>

      {/* Internal mode: the guided prompt to run in the Claude terminal. */}
      {mode === "internal" && cvPrompt && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm">
          <p className="text-emerald-900 font-medium">Run this in the Internal (Claude) terminal:</p>
          <div className="mt-1.5 flex items-center gap-2">
            <code className="flex-1 px-2 py-1 rounded bg-white border border-emerald-200 text-gray-800">
              {cvPrompt}
            </code>
            <button
              onClick={() =>
                navigator.clipboard
                  ?.writeText(cvPrompt)
                  .then(() => setCopied(true))
                  .catch(() => {})
              }
              className="px-2 py-1 text-xs font-medium text-emerald-700 bg-white border border-emerald-300 rounded hover:bg-emerald-100"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-emerald-700">
            {waiting
              ? "Waiting for Claude to parse your CV and save the profile…"
              : "Your CV was saved locally; switch the assistant to Internal (Claude) and run it."}
          </p>
        </div>
      )}

      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">External resources</h3>
        <ul className="text-sm text-indigo-600 space-y-1">
          <li>
            <a className="hover:underline" href="https://www.overleaf.com/gallery/tagged/cv" target="_blank" rel="noopener noreferrer">
              Resume / CV templates (Overleaf) ↗
            </a>
          </li>
          <li>
            <a className="hover:underline" href="https://www.techinterviewhandbook.org/" target="_blank" rel="noopener noreferrer">
              Tech Interview Handbook ↗
            </a>
          </li>
        </ul>
      </section>
    </div>
  );
}

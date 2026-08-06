import { useEffect, useMemo, useRef, useState } from "react";
import { api, type Profile } from "../api";
import { failureMessage } from "../format";
import type { AssistantMode } from "../App";
import { LinkIcon } from "./icons";
import BackgroundPanel from "./BackgroundPanel";

// Display order for the structured skill groups (anything else falls under "Other").
const SKILL_ORDER = ["Languages", "Frameworks & Libraries", "Tools", "Domains", "Soft skills"];

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
  const [resumeMsg, setResumeMsg] = useState(""); // result of "import from resume/"
  // Paste / upload failures. CV parsing can now refuse (a truncated or failed
  // completion is no longer written off as "mock mode"), and these two paths had
  // no catch at all: the spinner stopped and nothing else happened.
  const [cvError, setCvError] = useState("");
  const [expanded, setExpanded] = useState<Set<number>>(new Set()); // which résumé sections are open
  // Re-fold whenever the profile (re)loads, so a re-parse can't leave a stale index open.
  useEffect(() => setExpanded(new Set()), [profile]);
  const baseline = useRef<string | null>(null); // serialized profile before parse; null = not yet established
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
        if (p) {
          const snap = JSON.stringify(p);
          if (baseline.current === null) {
            baseline.current = snap; // first good read establishes the baseline (don't complete yet)
          } else if (snap !== baseline.current) {
            setProfile(p);
            onChanged();
            setWaiting(false);
            setCvPrompt(""); // parse done — hide the guided-prompt box
            setCopied(false);
            return;
          }
        }
        if (Date.now() - started > 180_000) setWaiting(false);
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
    const p = await api.getProfile().catch(() => null);
    if (modeRef.current !== "internal") return; // user flipped to External mid-stash
    // null sentinel when the read failed → the poll establishes the baseline on its
    // first successful read instead of false-completing against an empty {}.
    baseline.current = p ? JSON.stringify(p) : null;
    setCvPrompt("parse my cv");
    setCopied(false);
    setWaiting(true);
  };

  const submit = async () => {
    if (!cv.trim() || busy || waiting) return;
    if (mode === "internal") {
      setBusy(true);
      setCvError("");
      let ok = true;
      try {
        await api.saveCvSource(cv);
      } catch (e) {
        ok = false;
        setCvError(failureMessage(e, "Couldn't save the CV text."));
      } finally {
        setBusy(false);
      }
      if (ok) await startInternal();
      return;
    }
    setBusy(true);
    setCvError("");
    try {
      await api.submitCv(cv);
      setCv("");
      await load();
      onChanged();
    } catch (e) {
      setCvError(failureMessage(e, "Couldn't parse that CV."));
    } finally {
      setBusy(false);
    }
  };

  const upload = async (file: File | undefined) => {
    if (!file || busy || waiting) return;
    if (mode === "internal") {
      setBusy(true);
      setCvError("");
      let ok = true;
      try {
        await api.uploadCvSource(file);
      } catch (e) {
        ok = false;
        setCvError(failureMessage(e, "Couldn't read / save that file."));
      } finally {
        setBusy(false);
      }
      if (ok) await startInternal();
      return;
    }
    setBusy(true);
    setCvError("");
    try {
      await api.uploadCv(file);
      await load();
      onChanged();
    } catch (e) {
      setCvError(failureMessage(e, "Couldn't read / parse that file."));
    } finally {
      setBusy(false);
    }
  };

  // Import the résumé already sitting in the resume/ folder (no upload needed).
  const importFromResume = async () => {
    if (busy || waiting) return;
    setResumeMsg("");
    const noResume = (e: unknown) => (e as Error).message.includes("404");
    if (mode === "internal") {
      setBusy(true);
      let ok = true;
      try {
        await api.cvSourceFromResume();
      } catch (e) {
        ok = false;
        setResumeMsg(noResume(e) ? "No résumé found — add a file under resume/ first." : "Couldn't read the résumé.");
      } finally {
        setBusy(false);
      }
      if (ok) await startInternal();
      return;
    }
    setBusy(true);
    try {
      await api.cvFromResume();
      await load();
      onChanged();
      setResumeMsg("Imported your résumé from resume/.");
    } catch (e) {
      setResumeMsg(noResume(e) ? "No résumé found — add a file under resume/ first." : "Couldn't parse the résumé.");
    } finally {
      setBusy(false);
    }
  };

  const skills = profile?.skills ?? [];
  const skillGroups = useMemo(() => {
    const g: Record<string, typeof skills> = {};
    for (const s of skills) {
      const cat = SKILL_ORDER.includes(s.category || "") ? (s.category as string) : "Other";
      (g[cat] ||= []).push(s);
    }
    return [...SKILL_ORDER, "Other"].filter((c) => g[c]?.length).map((c) => ({ cat: c, items: g[c] }));
  }, [skills]);
  const links = Object.entries(profile?.links ?? {}).filter(([, url]) => url);
  const sections = profile?.sections ?? [];
  const hasContent = !!(profile?.name || skills.length || links.length || sections.length);
  const toggle = (i: number) =>
    setExpanded((s) => {
      const n = new Set(s);
      n.has(i) ? n.delete(i) : n.add(i);
      return n;
    });
  const hrefFor = (kind: string, url: string) =>
    kind === "email" || /^[^/\s@]+@[^/\s@]+$/.test(url) ? (url.startsWith("mailto:") ? url : `mailto:${url}`) : url;
  const hostOf = (url?: string) => {
    if (url?.toLowerCase().startsWith("mailto:")) return url.slice(7); // show the address
    try {
      return new URL(url!).hostname.replace(/^www\./, "") || url || "link";
    } catch {
      return url || "link";
    }
  };
  // Only allow http(s)/mailto hrefs — never render a javascript: URL from parsed CV text.
  const safeUrl = (url?: string) => (url && /^(https?|mailto):/i.test(url) ? url : undefined);

  return (
    <div className="h-full overflow-auto p-5 space-y-6">
      <section>
        {profile && hasContent ? (
          <div className="space-y-4">
            {/* Header — name, headline, location + link icons */}
            <div>
              <div className="text-xl font-bold text-gray-900">{profile.name || "—"}</div>
              {profile.headline && <div className="text-sm text-gray-600">{profile.headline}</div>}
              <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
                {profile.location && <span className="text-gray-400">{profile.location}</span>}
                {links.map(([kind, url]) => {
                  const href = safeUrl(hrefFor(kind, url));
                  if (!href) return null;
                  return (
                    <a
                      key={kind}
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      title={url}
                      className="inline-flex items-center gap-1 text-gray-500 hover:text-indigo-600"
                    >
                      <LinkIcon kind={kind} url={url} className="w-4 h-4" />
                      <span className="capitalize">{kind}</span>
                    </a>
                  );
                })}
              </div>
            </div>

            {/* Skills — grouped by category (Languages / Tools / Domains / …) */}
            {skills.length > 0 && (
              <div className="space-y-2">
                {skillGroups.map(({ cat, items }) => (
                  <div key={cat}>
                    <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-1">
                      {cat}
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {items.map((s, i) => (
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
                  </div>
                ))}
              </div>
            )}

            {/* Résumé sections — folded by default, click to expand */}
            {sections.map((sec, i) => {
              const open = expanded.has(i);
              const items = sec.items ?? [];
              return (
                <div key={i} className="rounded-lg border border-gray-200">
                  <button
                    type="button"
                    onClick={() => toggle(i)}
                    aria-expanded={open}
                    className="w-full flex items-start gap-2 px-3 py-2.5 text-left hover:bg-gray-50"
                  >
                    <span className="mt-0.5 text-gray-400 select-none">{open ? "▾" : "▸"}</span>
                    <span className="flex-1 min-w-0">
                      <span className="text-sm font-semibold text-gray-700">{sec.title || sec.id || "Section"}</span>
                      {sec.summary && <span className="block text-xs text-gray-500 mt-0.5">{sec.summary}</span>}
                    </span>
                  </button>
                  {open && items.length > 0 && (
                    <div className="px-3 pb-3 border-t border-gray-100 divide-y divide-gray-50">
                      {items.map((it, j) => (
                        <div key={j} className="py-3">
                          {it.heading && <div className="text-sm font-medium text-gray-800">{it.heading}</div>}
                          {it.subhead && <div className="text-xs text-gray-400">{it.subhead}</div>}
                          {it.detail && <p className="mt-1 text-sm text-gray-600 whitespace-pre-line">{it.detail}</p>}
                          {(it.links?.length ?? 0) > 0 && (
                            <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1">
                              {it.links!.map((l, k) => {
                                const href = safeUrl(l.url);
                                if (!href) return null;
                                return (
                                  <a
                                    key={k}
                                    href={href}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 text-xs text-indigo-600 hover:underline"
                                  >
                                    <LinkIcon url={l.url} className="w-3.5 h-3.5" />
                                    {l.label || hostOf(l.url)}
                                  </a>
                                );
                              })}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-sm text-gray-400">
            No profile yet — paste your CV below, upload a file, or import from <code>resume/</code>.
          </p>
        )}
      </section>

      <section>
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Upload CV</h3>
        <div className="flex flex-wrap items-center gap-2">
          <label className="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md cursor-pointer hover:bg-indigo-100">
            {busy ? "Working…" : waiting ? "Waiting…" : "Choose file (PDF, DOCX, .txt, .md)"}
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown"
              className="hidden"
              disabled={busy || waiting}
              onChange={(e) => upload(e.target.files?.[0])}
            />
          </label>
          <button
            type="button"
            onClick={importFromResume}
            disabled={busy || waiting}
            title="Use the résumé already saved in the resume/ folder"
            className="px-3 py-1.5 text-sm font-medium text-indigo-700 bg-indigo-50 rounded-md hover:bg-indigo-100 disabled:opacity-50"
          >
            Import from <code className="text-xs">resume/</code> folder
          </button>
        </div>
        {resumeMsg && <p className="mt-2 text-xs text-gray-500">{resumeMsg}</p>}
        {cvError && <p className="mt-2 text-sm text-rose-600">{cvError}</p>}
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
              : "Your CV is saved — run it in the Claude terminal; the profile updates below."}
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

      <div className="rounded-lg border border-gray-200 p-4">
        <BackgroundPanel />
      </div>
    </div>
  );
}

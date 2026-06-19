import { useEffect, useState } from "react";
import { api, type Profile } from "../api";

// Profile / CV tab: shows the parsed profile (config/profile.yml) and lets the
// user paste CV text to (re)build it via the cv-intake skill.
export default function ProfilePanel({ onChanged }: { onChanged: () => void }) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [cv, setCv] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async () => setProfile(await api.getProfile());

  useEffect(() => {
    load();
  }, []);

  const submit = async () => {
    if (!cv.trim() || busy) return;
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
        <h3 className="text-sm font-semibold text-gray-700 mb-2">Paste CV</h3>
        <textarea
          className="w-full h-48 px-3 py-2 text-sm border border-gray-300 rounded-md resize-y font-mono"
          placeholder="Paste your CV / resume text here…"
          value={cv}
          onChange={(e) => setCv(e.target.value)}
        />
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={submit}
            disabled={busy || !cv.trim()}
            className="px-3 py-1.5 text-sm font-medium text-white bg-indigo-600 rounded-md hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? "Parsing…" : "Parse CV → profile"}
          </button>
          <span className="text-xs text-gray-400">
            Stored locally in <code>config/profile.yml</code>. Used to score fit.
          </span>
        </div>
      </section>

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

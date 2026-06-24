// Tiny API client. Uses VITE_API_BASE when set, otherwise relative paths so the
// nginx reverse-proxy (/api -> api:8000) handles routing in Docker.
const BASE = import.meta.env.VITE_API_BASE ?? "";

export interface Job {
  id: string;
  company: string;
  company_job_id: string;
  position: string;
  status: string;
  location: string;
  flexibility: string;
  salary_min: number | null;
  salary_max: number | null;
  currency: string;
  posted_date: string;
  url: string;
  fit_score: number | null;
  detail_md: string;
  role_category: string;
  starred: boolean;
}

export interface Application extends Job {
  applied_date: string;
  interview_date: string;
  contacts: string;
  notes: string;
  job_tracked?: boolean; // does a tracked job posting back this application?
}

export interface ProfileLink {
  label?: string;
  url?: string;
}
export interface ProfileItem {
  heading?: string;
  subhead?: string;
  detail?: string;
  links?: ProfileLink[];
}
export interface ProfileSection {
  id?: string;
  title?: string;
  summary?: string;
  items?: ProfileItem[];
}
export interface Profile {
  name?: string;
  headline?: string;
  location?: string;
  skills?: { name: string; level?: string; evidence?: string; category?: string }[];
  links?: Record<string, string>; // named profile links: github/website/linkedin/scholar/email…
  sections?: ProfileSection[];
  [key: string]: unknown;
}

export interface Targets {
  roles?: string[];
  locations?: string[];
  work_mode?: string;
  min_salary?: number | null;
  include_keywords?: string[];
  exclude_keywords?: string[];
}

export interface ChatAction {
  tool?: string;
  result?: unknown;
}

export interface Insights {
  funnel: { stage: string; count: number; rate: number }[];
  score_distribution: { range: string; count: number }[];
  by_status: Record<string, number>;
  activity: { week: string; added: number; applied: number }[];
  totals: { jobs: number; applications: number; evaluated: number };
}

interface OutcomeGroup {
  applied: number;
  advanced: number;
  offer: number;
  rejected: number;
  advance_rate: number;
}
export interface Outcomes {
  conversion: { label: string; n: number; d: number; rate: number }[];
  by_fit_band: (OutcomeGroup & { band: string })[];
  by_role: (OutcomeGroup & { role: string })[];
  calibration: {
    advanced_avg_fit: number | null;
    advanced_n: number;
    rejected_avg_fit: number | null;
    rejected_n: number;
  };
  follow_ups: { id: string; company: string; position: string; applied_date: string; days: number }[];
  stale_days: number;
}

// LLM narrative over the outcomes ({} when none yet). External generates; Internal saves.
export interface PatternInsights {
  summary?: string;
  wins?: string[];
  risks?: string[];
  actions?: string[];
}

// Structured fit evaluation (v2). Empty object ({}) when a job has none yet.
export interface Evaluation {
  job_id?: string;
  fit_score?: number;
  recommendation?: "apply" | "hold" | "skip";
  strengths?: string[];
  weaknesses?: string[];
  materials?: string[];
  legitimacy_score?: number | null;
  legitimacy_flags?: string[];
  archetype?: string;
}

export interface DocMeta {
  slug: string;
  title: string;
}
export interface DocSection {
  title: string;
  pages: DocMeta[];
}

async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const api = {
  chat: (message: string, history: { role: string; content: string }[]) =>
    http<{ reply: string; actions: ChatAction[] }>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    }),
  listJobs: (query = "") =>
    http<{ count: number; jobs: Job[] }>(`/api/jobs?query=${encodeURIComponent(query)}`),
  // Scan configured sources. Pass company names to restrict the scan; omit to scan all.
  scan: (companies?: string[]) =>
    http<{ new: number; duplicates: number; filtered: number; capped: boolean; dead: number }>("/api/jobs/scan", {
      method: "POST",
      body: JSON.stringify(companies && companies.length ? { companies } : {}),
    }),
  // Configured scan sources, for the per-company scan selector.
  sources: () => http<{ companies: { name: string; provider: string }[] }>("/api/jobs/sources"),
  // The in-app User Manual, for the /docs page (grouped into sections).
  docs: () => http<{ sections: DocSection[] }>("/api/docs"),
  doc: (slug: string) => http<DocMeta & { markdown: string }>(`/api/docs/${encodeURIComponent(slug)}`),
  // Add a job from content you provide (no scraping). URL fetch, or paste/upload.
  ingestUrl: (url: string) =>
    http<{ job?: Job; created?: boolean }>("/api/jobs/ingest", { method: "POST", body: JSON.stringify({ url }) }),
  ingestJobDoc: (text: string) =>
    http<{ job?: Job; created?: boolean }>("/api/jobs/ingest-doc", { method: "POST", body: JSON.stringify({ text }) }),
  uploadJobDoc: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/api/jobs/ingest-doc/upload`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json() as Promise<{ job?: Job; created?: boolean }>;
  },
  // Internal mode: stash the raw posting (paste or file) for local Claude to parse.
  saveJobSource: (text: string) =>
    http<{ chars: number }>("/api/jobs/ingest-source", { method: "PUT", body: JSON.stringify({ text }) }),
  uploadJobSource: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/api/jobs/ingest-source/upload`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json() as Promise<{ chars: number }>;
  },
  // Marker the Internal-mode add-job poll watches (bumps on every ingest, even dedup).
  getIngestResult: () =>
    http<{ seq: number; job_id?: string; created?: boolean; position?: string }>("/api/jobs/ingest-result"),
  getJob: (id: string) => http<{ job: Job; markdown: string }>(`/api/jobs/${id}`),
  updateJob: (id: string, patch: Partial<Job>) =>
    http<{ job: Job }>(`/api/jobs/${id}`, { method: "PATCH", body: JSON.stringify(patch) }),
  evaluate: (id: string) => http<Record<string, unknown>>(`/api/jobs/${id}/evaluate`, { method: "POST" }),
  prepare: (id: string) =>
    http<{ apply_url: string; detail_md: string; note: string }>(`/api/jobs/${id}/prepare`, {
      method: "POST",
    }),
  submitCv: (cv_text: string) =>
    http<Record<string, unknown>>("/api/cv", { method: "POST", body: JSON.stringify({ cv_text }) }),
  uploadCv: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/api/cv/upload`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json() as Promise<Record<string, unknown>>;
  },
  // Internal mode: store the raw CV (paste or file) so local Claude can parse it.
  saveCvSource: (text: string) =>
    http<{ chars: number }>("/api/cv/source", { method: "PUT", body: JSON.stringify({ text }) }),
  uploadCvSource: async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${BASE}/api/cv/source/upload`, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json() as Promise<{ chars: number }>;
  },
  // Import the résumé already in the resume/ folder — External parses it into the
  // profile; Internal stashes it for local Claude (then poll the profile).
  cvFromResume: () =>
    http<{ updated?: boolean; profile?: Profile; resume_path: string }>("/api/cv/from-resume", { method: "POST" }),
  cvSourceFromResume: () =>
    http<{ chars: number; resume_path: string }>("/api/cv/source/from-resume", { method: "POST" }),
  listApplications: () =>
    http<{ count: number; applications: Application[] }>("/api/applications"),
  markApplied: (id: string, applied_date?: string) =>
    http<{ application: Application; created: boolean }>(`/api/jobs/${id}/apply`, {
      method: "POST",
      body: JSON.stringify(applied_date ? { applied_date } : {}),
    }),
  updateApplication: (id: string, patch: Partial<Application>) =>
    http<{ application: Application }>(`/api/applications/${id}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    }),
  createApplication: (payload: Partial<Application>) =>
    http<{ application: Application; job_tracked: boolean }>("/api/applications", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  // Link an orphan application to a (just-ingested) job posting — re-keys it to the
  // job, carries the job's fields, keeps the orphan's tracker fields. Deterministic.
  linkApplication: (id: string, job_id: string) =>
    http<{ application: Application; job_tracked: boolean }>(`/api/applications/${id}/link`, {
      method: "POST",
      body: JSON.stringify({ job_id }),
    }),
  deleteApplication: (id: string) =>
    http<{ deleted: string }>(`/api/applications/${id}`, { method: "DELETE" }),
  // Whether External-mode LLM calls are real or mock placeholders (no key). The UI
  // warns in External mode when mock so results aren't mistaken for real analysis.
  getLlmStatus: () => http<{ mock: boolean; provider: string }>("/api/llm-status"),
  getStats: () => http<Insights>("/api/stats"),
  getOutcomes: () => http<Outcomes>("/api/stats/outcomes"),
  // Pattern insights: External generates the narrative via the LLM; Internal polls the
  // store after local Claude saves it (PUT is done by the skill, not the web).
  analyzePatterns: () => http<PatternInsights>("/api/stats/patterns", { method: "POST" }),
  getPatterns: () => http<PatternInsights>("/api/stats/patterns"),
  getProfile: () => http<Profile>("/api/profile"),
  getPreferences: () => http<Targets>("/api/preferences"),
  savePreferences: (t: Targets) =>
    http<Targets>("/api/preferences", { method: "PUT", body: JSON.stringify(t) }),
  upskilling: (id: string) =>
    http<{
      job_id: string;
      summary: string;
      missing_skills: { skill: string; why: string; how_to_close: string }[];
    }>(`/api/jobs/${id}/upskilling`, { method: "POST" }),
  // Read the last saved skill-gap analysis ({} if none). Used to poll for the
  // result after local Claude saves it in Internal mode.
  getUpskilling: (id: string) =>
    http<{
      summary?: string;
      missing_skills?: { skill: string; why: string; how_to_close: string }[];
    }>(`/api/jobs/${id}/upskilling`),
  // Read the last saved structured evaluation ({} if none). Used to render the
  // legitimacy/archetype blocks and to poll after a save in Internal mode.
  getEvaluation: (id: string) => http<Evaluation>(`/api/jobs/${id}/evaluation`),
  // Cover letter: External generates via the LLM; Internal saves Claude's draft.
  generateCoverLetter: (id: string) =>
    http<{ job_id: string; content: string }>(`/api/jobs/${id}/cover-letter`, { method: "POST" }),
  getCoverLetter: (id: string) =>
    http<{ job_id?: string; content?: string }>(`/api/jobs/${id}/cover-letter`),
  // Tailored CV: External generates LaTeX (+ PDF); Internal saves Claude's .tex.
  generateCv: (id: string) =>
    http<{ job_id: string; tex: string; pdf_available: boolean }>(`/api/jobs/${id}/cv`, { method: "POST" }),
  getCv: (id: string) =>
    http<{ job_id?: string; tex?: string; pdf_available?: boolean }>(`/api/jobs/${id}/cv`),
  cvPdfUrl: (id: string) => `${BASE}/api/jobs/${id}/cv.pdf`,
};

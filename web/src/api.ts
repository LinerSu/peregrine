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
  url: string;
  fit_score: number | null;
  detail_md: string;
}

export interface ChatAction {
  tool?: string;
  result?: unknown;
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
  scan: () => http<{ new: number; duplicates: number; filtered: number }>("/api/jobs/scan", { method: "POST" }),
  getJob: (id: string) => http<{ job: Job; markdown: string }>(`/api/jobs/${id}`),
  evaluate: (id: string) => http<Record<string, unknown>>(`/api/jobs/${id}/evaluate`, { method: "POST" }),
  prepare: (id: string) =>
    http<{ apply_url: string; detail_md: string; note: string }>(`/api/jobs/${id}/prepare`, {
      method: "POST",
    }),
  submitCv: (cv_text: string) =>
    http<Record<string, unknown>>("/api/cv", { method: "POST", body: JSON.stringify({ cv_text }) }),
};

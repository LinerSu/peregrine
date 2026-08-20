// Shared display formatting for jobs/applications tables.

// "today" / "3d ago" / "2w ago" / "5mo ago" / "2y ago" for a YYYY-MM-DD date;
// "" for empty/invalid input so callers can simply omit the segment.
export function relativeTime(dateStr: string): string {
  if (!dateStr) return "";
  const d = new Date(`${dateStr}T00:00:00`);
  if (isNaN(d.getTime())) return "";
  // Diff LOCAL MIDNIGHTS and round: subtracting the date from raw `now` drifts
  // ±1h across a DST boundary, which floor() turns into an off-by-one day.
  const days = Math.round((new Date().setHours(0, 0, 0, 0) - d.getTime()) / 86_400_000);
  if (days < 0) return dateStr; // future "posted" date — show it verbatim
  if (days === 0) return "today";
  if (days < 7) return `${days}d ago`;
  if (days < 30) return `${Math.floor(days / 7)}w ago`;
  if (days < 365) return `${Math.floor(days / 30)}mo ago`;
  return `${Math.floor(days / 365)}y ago`;
}

// Only http(s) URLs may be rendered as links — job.url comes from scraped or
// LLM-extracted posting fields, so a javascript:/data: scheme must never reach
// an href. undefined (not "") so callers can gate rendering on it.
export function safeHttpUrl(u?: string): string | undefined {
  const t = (u || "").trim();
  return /^https?:\/\//i.test(t) ? t : undefined;
}

export function salaryRange(
  min: number | null,
  max: number | null,
  currency = "USD"
): string {
  if (min == null && max == null) return "—";
  const fmt = (n: number) =>
    new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: currency || "USD",
      maximumFractionDigits: 0,
    }).format(n);
  if (min != null && max != null) return `${fmt(min)}–${fmt(max)}`;
  return fmt((min ?? max) as number);
}

const STATUS_STYLES: Record<string, string> = {
  open: "bg-green-100 text-green-700",
  applied: "bg-blue-100 text-blue-700",
  interviewing: "bg-amber-100 text-amber-700",
  offer: "bg-emerald-100 text-emerald-700",
  rejected: "bg-rose-100 text-rose-700",
  closed: "bg-gray-100 text-gray-600",
  removed: "bg-gray-100 text-gray-600",
};

export function statusClass(status: string): string {
  return STATUS_STYLES[status] ?? "bg-gray-100 text-gray-600";
}

// Color a fit score: green ≥0.70, amber 0.40–0.69, red <0.40, gray when unscored
// (null) or non-finite (NaN/inf — treated as unscored).
export function fitClass(score: number | null | undefined): string {
  if (score == null || !Number.isFinite(score)) return "bg-gray-100 text-gray-500";
  if (score >= 0.7) return "bg-green-100 text-green-700";
  if (score >= 0.4) return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

// Color a legitimacy (ghost-job risk) score: green ≥0.80 (looks legit),
// amber 0.50–0.79, red <0.50; gray when unscored/non-finite.
export function legitimacyClass(score: number | null | undefined): string {
  if (score == null || !Number.isFinite(score)) return "bg-gray-100 text-gray-500";
  if (score >= 0.8) return "bg-green-100 text-green-700";
  if (score >= 0.5) return "bg-amber-100 text-amber-700";
  return "bg-rose-100 text-rose-700";
}

// What to show when an action fails. The API now explains LLM failures in `detail`
// ("hit its output cap", "the provider failed…") and api.ts throws that as the Error
// message — surfacing it is the point of making those failures loud, since a generic
// "couldn't do it" reads exactly like the placeholder output it replaced. The
// cross-mode escape hatch stays on the end either way: Internal mode runs the same
// work locally, which is the one action that always helps.
export function failureMessage(e: unknown, fallback: string): string {
  const reason = (e instanceof Error && e.message ? e.message : fallback).trim();
  // The API's own messages end with their advice ("Try again, or shorten the input.").
  // Appending ours would give the user two "try again"s in one line, so the hint is a
  // default, not a suffix — and the sentence gets a full stop either way.
  const text = /[.!?]$/.test(reason) ? reason : `${reason}.`;
  return /try again/i.test(text) ? text : `${text} Try again, or use Internal mode.`;
}

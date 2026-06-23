// Minimal inline-SVG icons for profile links — no dependency. Brand marks
// (GitHub/LinkedIn) use fill; the rest are simple stroked glyphs.

type IconProps = { className?: string };
const base = "w-4 h-4";

export function GithubIcon({ className = base }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M12 .5C5.7.5.5 5.8.5 12.3c0 5.2 3.3 9.6 8 11.1.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.5-1.4-1.3-1.7-1.3-1.7-1.1-.8.1-.8.1-.8 1.2.1 1.8 1.3 1.8 1.3 1.1 1.9 2.9 1.3 3.6 1 .1-.8.4-1.3.8-1.6-2.7-.3-5.5-1.4-5.5-6 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.6.1-3.2 0 0 1-.3 3.3 1.2a11.4 11.4 0 0 1 6 0C17 4.6 18 5 18 5c.6 1.6.2 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6 4.6-1.5 7.9-5.9 7.9-11.1C23.5 5.8 18.3.5 12 .5z" />
    </svg>
  );
}

export function LinkedinIcon({ className = base }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="currentColor" aria-hidden="true">
      <path d="M20.4 20.4h-3.6v-5.6c0-1.3 0-3-1.9-3s-2.1 1.4-2.1 2.9v5.7H9.2V9h3.4v1.6h.1c.5-.9 1.7-1.9 3.4-1.9 3.6 0 4.3 2.4 4.3 5.5v6.2zM5.3 7.4a2.1 2.1 0 1 1 0-4.2 2.1 2.1 0 0 1 0 4.2zM7.1 20.4H3.5V9h3.6v11.4zM22.2 0H1.8C.8 0 0 .8 0 1.7v20.6c0 .9.8 1.7 1.8 1.7h20.4c1 0 1.8-.8 1.8-1.7V1.7C24 .8 23.2 0 22.2 0z" />
    </svg>
  );
}

function stroked(path: string) {
  return function Icon({ className = base }: IconProps) {
    return (
      <svg viewBox="0 0 24 24" className={className} fill="none" stroke="currentColor"
        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {path.split("|").map((d, i) => <path key={i} d={d} />)}
      </svg>
    );
  };
}

export const GlobeIcon = stroked("M12 3a9 9 0 100 18 9 9 0 000-18|M3 12h18|M12 3c2.5 2.4 3.9 5.6 4 9-.1 3.4-1.5 6.6-4 9-2.5-2.4-3.9-5.6-4-9 .1-3.4 1.5-6.6 4-9");
export const MailIcon = stroked("M4 5h16v14H4z|M4 6l8 6 8-6");
export const ExternalLinkIcon = stroked("M14 4h6v6|M20 4l-9 9|M19 14v5a1 1 0 01-1 1H5a1 1 0 01-1-1V6a1 1 0 011-1h5");
export const ScholarIcon = stroked("M12 4L2 9l10 5 10-5-10-5z|M6 11v5c0 1 2.7 2.5 6 2.5s6-1.5 6-2.5v-5");

export function LinkIcon({ kind, url, className }: { kind?: string; url?: string; className?: string }) {
  switch (pickKind(kind, url)) {
    case "github":
      return <GithubIcon className={className} />;
    case "linkedin":
      return <LinkedinIcon className={className} />;
    case "scholar":
      return <ScholarIcon className={className} />;
    case "email":
      return <MailIcon className={className} />;
    case "website":
      return <GlobeIcon className={className} />;
    default:
      return <ExternalLinkIcon className={className} />;
  }
}

// Choose an icon from the link's key (e.g. "github") or its URL host.
function pickKind(kind?: string, url?: string): string {
  const k = (kind || "").toLowerCase();
  if (["github", "linkedin", "scholar", "email", "website"].includes(k)) return k;
  if (k === "twitter" || k === "x" || k === "site" || k === "homepage") return "website";
  const u = (url || "").toLowerCase();
  if (u.startsWith("mailto:") || (u.includes("@") && !u.includes("/"))) return "email";
  if (u.includes("github.com")) return "github";
  if (u.includes("linkedin.com")) return "linkedin";
  if (u.includes("scholar.google")) return "scholar";
  if (u) return "website";
  return "link";
}

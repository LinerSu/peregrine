// Lightweight renderer that turns a job's snapshot Markdown into structured
// cards (Posting / Strengths / Weaknesses / Materials / …) instead of a raw
// <pre> block. No markdown dependency — we only need headings, bullets, and
// **bold** inline, which is all the data store writes.

interface Section {
  level: number;
  title: string;
  lines: string[];
}

function parseSections(md: string): Section[] {
  const out: Section[] = [];
  let cur: Section | null = null;
  for (const raw of md.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    if (h) {
      cur = { level: h[1].length, title: h[2], lines: [] };
      out.push(cur);
    } else if (line.trim() === "---") {
      continue;
    } else {
      if (!cur) {
        cur = { level: 0, title: "", lines: [] };
        out.push(cur);
      }
      cur.lines.push(line);
    }
  }
  return out.map((s) => ({ ...s, lines: trimBlank(s.lines) })).filter((s) => s.title || s.lines.length);
}

function trimBlank(lines: string[]): string[] {
  let a = 0;
  let b = lines.length;
  while (a < b && !lines[a].trim()) a++;
  while (b > a && !lines[b - 1].trim()) b--;
  return lines.slice(a, b);
}

// The facts a reader scans a posting for: pay, years of experience, and degree. Highlight
// them inline so they pop out of the prose (comp = green, the gating requirements = amber).
function Highlighted({ text }: { text: string }) {
  const re =
    /(\$\s?\d[\d,]*(?:\.\d+)?(?:\s?[KkMm])?(?:\s*(?:[-–—]|to)\s*\$?\s?\d[\d,]*(?:\.\d+)?(?:\s?[KkMm])?)?)|(\b\d{1,2}\+?\s*(?:[-–]\s*\d{1,2}\s*)?years?\b)|(Ph\.?\s?D\.?|Doctorate|Master['’]?s|Bachelor['’]?s|\bMBA\b)/gi;
  const nodes: (JSX.Element | string)[] = [];
  let last = 0;
  let key = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const cls = m[1]
      ? "rounded bg-emerald-50 px-1 font-medium text-emerald-700" // compensation
      : "rounded bg-amber-50 px-1 font-medium text-amber-800"; // years / degree — gating reqs
    nodes.push(
      <mark key={`m${key++}`} className={cls}>
        {m[0]}
      </mark>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return <>{nodes}</>;
}

function Inline({ text }: { text: string }) {
  // split on **bold**: odd-indexed parts are bold; both sides still get fact highlighting
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((p, i) =>
        i % 2 ? (
          <strong key={i}>
            <Highlighted text={p} />
          </strong>
        ) : (
          <Highlighted key={i} text={p} />
        )
      )}
    </>
  );
}

// Words ignored when deciding if a line is "title case" (a header) vs a sentence (only its
// first word capitalized).
const STOP = new Set([
  "the", "of", "and", "a", "an", "to", "for", "in", "on", "with", "or", "your",
  "you", "we", "our", "&", "at", "by", "as", "is", "are", "from",
]);
// Common job-posting section names — so a Title-Case header (e.g. "About the Role",
// "Responsibilities", "Preferred Qualifications") is recognized even when the source feed
// didn't shout it in ALL CAPS.
const SECTION_KEYWORDS =
  /^(about\b|who we are|the (team|role|opportunity|company)|in this role|what (you|we|the)|your (role|impact|team)|how you|why\b|responsibilities|key responsibilities|duties|requirements?|((minimum|basic|preferred|required|key|desired|core)\s+)?qualifications|skills|experience|education|nice to have|bonus( points)?|benefits|perks|compensation|salary|pay|what we offer|our (team|mission|culture|values)|note|role overview|overview|location)\b/i;

// A posting's section headers arrive flattened: either ALL CAPS ("ABOUT THE TEAM"), Title
// Case ("About the Role"), or — once the scraper preserves structure — as `## h` / `**bold**`.
// Recognize all of those so each posting renders with clear section dividers. Returns the
// header text, or null for ordinary body lines.
function asHeading(raw: string): string | null {
  let t = raw.trim();
  // `#{1,3}` headings are consumed upstream by parseSections() as their own cards, so only
  // `####`+ reach Body — reserved for when _strip_html preserves the feed's heading structure
  // (it would demote a description's headings to `####` to keep them inside the Posting body).
  const hx = /^#{4,6}\s+(.+)$/.exec(t);
  if (hx) t = hx[1].trim();
  let bold = /^\*\*(.+?)\*\*:?$/.exec(t); // a whole line wrapped in **bold**
  if (bold && bold[1].includes("**")) bold = null; // two separate spans, not one header
  if (bold) t = bold[1].trim();
  const core = t.replace(/:+$/, "").trim();
  if (!core || core.length > 70) return null;
  if (hx || bold) return core || null; // an explicit marker — trust it
  if (/[.!?,;]$/.test(core)) return null; // ends like a sentence -> body text
  const letters = core.replace(/[^A-Za-z]/g, "");
  if (letters.length < 3) return null;
  if (core === core.toUpperCase()) return core; // ALL CAPS (e.g. OpenAI feeds)
  if (SECTION_KEYWORDS.test(core)) return core; // a known section name (Title Case)
  const words = core.split(/\s+/).filter(Boolean);
  if (words.length > 7) return null; // headers are short
  // Title Case: every significant (non-stopword) word is capitalized — unlike a sentence,
  // where only the first word is. Catches sub-headers like "Cross-Functional Coordination".
  const sig = words.filter((w) => !STOP.has(w.toLowerCase()));
  const capped = sig.filter((w) => /^[A-Z0-9(]/.test(w)).length;
  if (sig.length && capped === sig.length) {
    if (t.endsWith(":") || words.length >= 2 || letters.length >= 6) return core;
  }
  return null;
}

// Colour a section title by what it is, so the eye lands on the part it wants: the role's
// duties, the bar you must clear, the upside. (Check "preferred" before "required" so
// "Preferred Qualifications" reads as a softer bonus, not a hard requirement.)
function headingColor(title: string): string {
  const t = title.toLowerCase();
  // Context first, so "About the Role" reads as overview (gray), not duties (it contains
  // "the role"). Then bonus before required, so "Preferred Qualifications" stays a soft bonus.
  if (/(^about|who we are|the (team|company|mission)|our (team|mission|culture|values|company)|overview|company|opportunity)/.test(t))
    return "text-gray-500"; // about / team / context
  if (/(nice to have|preferred|bonus|desired|good to have|a plus)/.test(t))
    return "text-violet-600"; // bonus / nice-to-have
  if (/(qualif|require|minimum|basic|skills|experience|education|who you are|what we.re looking|you (have|bring|are)|must have)/.test(t))
    return "text-amber-700"; // the bar you must clear
  if (/(benefit|perk|compensation|salary|\bpay\b|what we offer|why )/.test(t))
    return "text-emerald-600"; // the upside
  if (/(responsibilit|what you('|’| wi)ll do|duties|in this role|the role|your (role|impact)|day.to.day)/.test(t))
    return "text-indigo-600"; // what you'll do
  return "text-gray-500"; // default context
}

function Body({ lines }: { lines: string[] }) {
  const blocks: JSX.Element[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length) {
      blocks.push(
        <ul key={`u${blocks.length}`} className="list-disc pl-5 space-y-0.5">
          {bullets.map((b, i) => (
            <li key={i}>
              <Inline text={b} />
            </li>
          ))}
        </ul>
      );
      bullets = [];
    }
  };
  for (const line of lines) {
    const m = /^\s*[-*]\s+(.*)$/.exec(line);
    const head = m ? null : asHeading(line);
    if (m) {
      bullets.push(m[1]);
    } else if (head) {
      flush();
      const first = blocks.length === 0; // no divider above the very first header
      blocks.push(
        <p
          key={`h${blocks.length}`}
          className={`text-xs font-semibold uppercase tracking-wide ${headingColor(head)} ${
            first ? "" : "mt-3 border-t border-gray-200 pt-2.5"
          }`}
        >
          {head}
        </p>
      );
    } else if (line.trim()) {
      flush();
      blocks.push(
        <p key={`p${blocks.length}`}>
          <Inline text={line} />
        </p>
      );
    }
  }
  flush();
  return <div className="space-y-2">{blocks}</div>;
}

function accent(title: string): string {
  const t = title.toLowerCase();
  if (t.includes("strength")) return "border-l-green-400";
  if (t.includes("weak") || t.includes("gap")) return "border-l-amber-400";
  if (t.includes("material")) return "border-l-indigo-400";
  if (t.includes("evaluation")) return "border-l-gray-300";
  return "border-l-gray-200";
}

export default function JobMarkdown({
  md,
  hideSections = [],
}: {
  md: string;
  // Section titles to suppress (case-insensitive substring) — e.g. "Agent evaluation"
  // when the stored evaluation predates the current CV and must not read as current.
  hideSections?: string[];
}) {
  if (!md.trim()) return <p className="text-sm text-gray-400">No snapshot yet.</p>;
  const hidden = hideSections.map((h) => h.toLowerCase());
  const sections = parseSections(md)
    .filter((s) => s.level !== 1) // header already shows the title
    .filter((s) => !hidden.some((h) => s.title.toLowerCase().includes(h)));

  return (
    <div className="space-y-3">
      {sections.map((s, i) =>
        s.level === 0 ? (
          <div key={i} className="text-xs text-gray-500 space-y-0.5">
            <Body lines={s.lines} />
          </div>
        ) : (
          <div
            key={i}
            className={`rounded-md border border-gray-200 border-l-4 ${accent(s.title)} bg-white p-3 shadow-sm`}
          >
            <h3 className="text-sm font-semibold text-gray-800 mb-1.5">{s.title}</h3>
            <div className="text-sm text-gray-700">
              <Body lines={s.lines} />
            </div>
          </div>
        )
      )}
    </div>
  );
}

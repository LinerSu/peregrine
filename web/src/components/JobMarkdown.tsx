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

function Inline({ text }: { text: string }) {
  // split on **bold**: odd-indexed parts are bold
  const parts = text.split(/\*\*(.+?)\*\*/g);
  return (
    <>
      {parts.map((p, i) => (i % 2 ? <strong key={i}>{p}</strong> : <span key={i}>{p}</span>))}
    </>
  );
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
    if (m) {
      bullets.push(m[1]);
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

export default function JobMarkdown({ md }: { md: string }) {
  if (!md.trim()) return <p className="text-sm text-gray-400">No snapshot yet.</p>;
  const sections = parseSections(md).filter((s) => s.level !== 1); // header already shows the title

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

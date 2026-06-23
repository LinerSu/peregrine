import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSlug from "rehype-slug";
import { api, type DocSection } from "./api";

// The slug from /docs/<slug> (empty on bare /docs -> default to the first page).
function slugFromPath(): string {
  const m = window.location.pathname.match(/^\/docs\/([^/?#]+)/);
  if (!m) return "";
  try {
    return decodeURIComponent(m[1]).toLowerCase();
  } catch {
    return ""; // malformed %-encoding -> default page, don't crash
  }
}

// A relative in-doc link to another manual page -> our /docs slug (so cross-links navigate
// within the viewer). Scheme/anchor/protocol-relative links are left alone.
function internalDocHref(href: string): string | null {
  if (!href || /^[a-z]+:/i.test(href) || href.startsWith("#") || href.startsWith("//")) return null;
  const m = href.match(/([^/]+)\.md([?#].*)?$/i);
  return m ? `/docs/${m[1].toLowerCase()}${m[2] || ""}` : null;
}

const components: Components = {
  a({ href, children, ...rest }) {
    const h = href || "";
    const internal = internalDocHref(h);
    if (internal) return <a href={internal} {...rest}>{children}</a>;
    if (/^(https?:|mailto:|\/\/)/i.test(h)) {
      return <a href={h} target="_blank" rel="noopener noreferrer" {...rest}>{children}</a>;
    }
    return <a href={h} {...rest}>{children}</a>;
  },
};

type TocItem = { id: string; text: string; level: number };

export default function Docs() {
  const [sections, setSections] = useState<DocSection[]>([]);
  const [slug, setSlug] = useState<string>(slugFromPath());
  const [markdown, setMarkdown] = useState<string>("");
  const [err, setErr] = useState<string>("");
  const [query, setQuery] = useState<string>("");
  const [toc, setToc] = useState<TocItem[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [loaded, setLoaded] = useState(false); // has the /api/docs nav resolved yet?

  useEffect(() => {
    api
      .docs()
      .then((r) => {
        setSections(r.sections);
        setSlug((cur) => cur || r.sections[0]?.pages[0]?.slug || "");
      })
      .catch(() => setErr("Couldn't load the docs — is the API running?"))
      .finally(() => setLoaded(true));
  }, []);

  useEffect(() => {
    const onPop = () => setSlug(slugFromPath());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  useEffect(() => {
    if (!slug) return;
    setErr("");
    api
      .doc(slug)
      .then((d) => {
        setMarkdown(d.markdown);
        document.title = `${d.title} — Peregrine docs`;
      })
      .catch(() => {
        setMarkdown("");
        setErr(`Couldn't load "${slug}".`);
      });
  }, [slug]);

  // Build the "On this page" TOC from rendered headings + highlight the one in view.
  useEffect(() => {
    const root = document.getElementById("doc-content");
    if (!root) return;
    const timer = window.setTimeout(() => {
      root.scrollTo?.(0, 0);
      const hs = Array.from(root.querySelectorAll("h2, h3")) as HTMLElement[];
      setToc(hs.filter((h) => h.id).map((h) => ({
        id: h.id, text: h.textContent || "", level: h.tagName === "H3" ? 3 : 2,
      })));
      const obs = new IntersectionObserver(
        (entries) => {
          const vis = entries
            .filter((e) => e.isIntersecting)
            .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
          if (vis[0]) setActiveId((vis[0].target as HTMLElement).id);
        },
        { rootMargin: "0px 0px -70% 0px" }
      );
      hs.forEach((h) => h.id && obs.observe(h));
      (root as unknown as { _obs?: IntersectionObserver })._obs = obs;
    }, 60);
    return () => {
      window.clearTimeout(timer);
      const r = document.getElementById("doc-content") as unknown as { _obs?: IntersectionObserver } | null;
      r?._obs?.disconnect();
    };
  }, [markdown]);

  const open = (s: string) => {
    if (s === slug) return;
    window.history.pushState(null, "", `/docs/${s}`);
    setSlug(s);
    setCopied(false);
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — ignore */
    }
  };

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sections;
    return sections
      .map((sec) => ({ ...sec, pages: sec.pages.filter((p) => p.title.toLowerCase().includes(q)) }))
      .filter((sec) => sec.pages.length);
  }, [sections, query]);

  return (
    <div className="flex h-screen bg-white text-gray-900">
      {/* Left: navigation */}
      <aside className="w-64 shrink-0 border-r border-gray-200 flex flex-col">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center gap-2">
          <a href="/" className="flex items-center gap-2 font-semibold hover:text-indigo-700">
            <img
              src="/peregrine-icon.png"
              alt=""
              className="w-6 h-6 rounded"
              onError={(e) => { e.currentTarget.style.display = "none"; }}
            />
            Peregrine
          </a>
          <span className="ml-auto text-xs text-gray-400">docs</span>
        </div>
        <div className="px-3 py-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search docs…"
            className="w-full px-2.5 py-1.5 text-sm border border-gray-300 rounded-md"
          />
        </div>
        <nav className="flex-1 overflow-y-auto px-2 pb-4">
          {filtered.map((sec) => (
            <div key={sec.title} className="mb-3">
              <div className="px-2 pt-2 pb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-400">
                {sec.title}
              </div>
              {sec.pages.map((p) => (
                <button
                  key={p.slug}
                  onClick={() => open(p.slug)}
                  className={`block w-full text-left px-2 py-1.5 text-sm rounded-md border-l-2 ${
                    p.slug === slug
                      ? "border-indigo-500 bg-indigo-50 text-indigo-800 font-medium"
                      : "border-transparent text-gray-700 hover:bg-gray-100"
                  }`}
                >
                  {p.title}
                </button>
              ))}
            </div>
          ))}
          {!filtered.length && (
            <p className="px-2 text-sm text-gray-400">{loaded ? "No matches." : "Loading…"}</p>
          )}
        </nav>
        <div className="px-4 py-2 border-t border-gray-200 flex items-center text-xs text-gray-400">
          <a href="https://github.com/LinerSu/peregrine" target="_blank" rel="noopener noreferrer" className="hover:text-gray-700">
            GitHub ↗
          </a>
          <a href="/" className="ml-auto hover:text-gray-700">← Back to app</a>
        </div>
      </aside>

      {/* Center: content */}
      <main id="doc-content" className="flex-1 overflow-y-auto px-8 py-6">
        <div className="max-w-3xl mx-auto">
          <div className="flex justify-end mb-2">
            {markdown && (
              <button
                onClick={copy}
                className="px-2.5 py-1 text-xs border border-gray-300 rounded-md hover:bg-gray-50"
                title="Copy this page as Markdown"
              >
                {copied ? "Copied ✓" : "Copy"}
              </button>
            )}
          </div>
          {err && <p className="text-rose-600 text-sm">{err}</p>}
          <div className="md">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSlug]} components={components}>
              {markdown}
            </ReactMarkdown>
          </div>
        </div>
      </main>

      {/* Right: on this page */}
      <aside className="hidden xl:block w-56 shrink-0 border-l border-gray-200 overflow-y-auto px-4 py-6">
        {toc.length > 0 && (
          <>
            <div className="text-[11px] font-semibold uppercase tracking-wide text-gray-400 mb-2">On this page</div>
            <ul className="space-y-1 text-sm">
              {toc.map((t) => (
                <li key={t.id} className={t.level === 3 ? "pl-3" : ""}>
                  <a
                    href={`#${t.id}`}
                    className={`block py-0.5 ${
                      activeId === t.id ? "text-indigo-700 font-medium" : "text-gray-500 hover:text-gray-800"
                    }`}
                  >
                    {t.text}
                  </a>
                </li>
              ))}
            </ul>
          </>
        )}
      </aside>
    </div>
  );
}

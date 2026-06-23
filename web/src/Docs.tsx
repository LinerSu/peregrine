import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, type DocMeta } from "./api";

// The slug from /docs/<slug> (empty on bare /docs -> default to the first doc).
function slugFromPath(): string {
  const m = window.location.pathname.match(/^\/docs\/([^/?#]+)/);
  if (!m) return "";
  try {
    return decodeURIComponent(m[1]).toLowerCase();
  } catch {
    return ""; // malformed %-encoding -> fall back to the default doc, don't crash render
  }
}

// A relative in-doc link to another markdown file -> our /docs slug (preserving any
// #anchor/?query), so cross-links navigate within the viewer. Scheme/anchor/protocol-relative
// links are left alone.
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
    // Real external links open in a new tab with rel; anchors (#…) and other relative links
    // navigate normally in the same tab.
    if (/^(https?:|mailto:|\/\/)/i.test(h)) {
      return (
        <a href={h} target="_blank" rel="noopener noreferrer" {...rest}>
          {children}
        </a>
      );
    }
    return <a href={h} {...rest}>{children}</a>;
  },
};

export default function Docs() {
  const [list, setList] = useState<DocMeta[]>([]);
  const [slug, setSlug] = useState<string>(slugFromPath());
  const [markdown, setMarkdown] = useState<string>("");
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    api
      .docs()
      .then((r) => {
        setList(r.docs);
        setSlug((cur) => cur || r.docs[0]?.slug || "");
      })
      .catch(() => setErr("Couldn't load the docs list — is the API running?"));
  }, []);

  // Back/forward buttons.
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
      .then((d) => setMarkdown(d.markdown))
      .catch(() => {
        setMarkdown("");
        setErr(`Couldn't load "${slug}".`);
      });
  }, [slug]);

  const open = (s: string) => {
    if (s === slug) return;
    window.history.pushState(null, "", `/docs/${s}`);
    setSlug(s);
  };

  return (
    <div className="flex flex-col h-screen bg-white text-gray-900">
      <header className="px-4 py-3 border-b border-gray-200 flex items-center gap-3">
        <a href="/" className="text-sm font-medium text-indigo-700 hover:underline">← Peregrine</a>
        <span className="text-gray-300">/</span>
        <h1 className="text-lg font-semibold">Docs</h1>
      </header>
      <div className="flex flex-1 overflow-hidden">
        <nav className="w-60 shrink-0 border-r border-gray-200 overflow-y-auto p-3 space-y-0.5">
          {list.map((d) => (
            <button
              key={d.slug}
              onClick={() => open(d.slug)}
              className={`block w-full text-left px-2 py-1.5 text-sm rounded-md ${
                d.slug === slug
                  ? "bg-indigo-100 text-indigo-800 font-medium"
                  : "text-gray-700 hover:bg-gray-100"
              }`}
            >
              {d.title}
            </button>
          ))}
          {!list.length && !err && <p className="px-2 text-sm text-gray-400">Loading…</p>}
        </nav>
        <main className="flex-1 overflow-y-auto px-6 py-5">
          <div className="md max-w-3xl mx-auto">
            {err && <p className="text-rose-600 text-sm">{err}</p>}
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
              {markdown}
            </ReactMarkdown>
          </div>
        </main>
      </div>
    </div>
  );
}

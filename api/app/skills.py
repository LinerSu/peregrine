"""Deterministic skill categorizer — groups a skill name into one coarse category so the
profile can show structured tags (Languages / Frameworks & Libraries / Tools / Domains /
Soft skills) instead of a flat cloud. Keyword-based, no LLM. Mirrors roles.classify_role.

First match wins; the name is space-padded so single-word keywords (" go ", " r ", " ml ")
match as whole words, not inside larger names (e.g. "Django" must not match "go").
"""
from __future__ import annotations

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Languages", (
        "python", "javascript", "typescript", " java", "c++", "c#", " c ", " go ", "golang",
        "rust", "ruby", "php", "swift", "kotlin", "scala", "ocaml", "haskell", "rocq", "coq",
        "lean", "matlab", "sql", "bash", "shell", "perl", "julia", "objective-c", "dart",
        "elixir", "clojure", "erlang", "f#", "assembly", "solidity", "verilog", "vhdl", " r ",
        "html", "css",
    )),
    ("Frameworks & Libraries", (
        "react", "vue", "angular", "svelte", "next.js", "nextjs", "node", "django", "flask",
        "fastapi", "spring", "rails", "pytorch", "tensorflow", "keras", "jax", "numpy",
        "pandas", "scikit", "express", ".net", "laravel", "redux", "graphql", "opengl",
        "three.js", "langchain", "hugging face", "huggingface", "transformers", "tailwind",
    )),
    ("Tools", (
        "docker", "kubernetes", "k8s", " git ", "github", "gitlab", "terraform", "ansible",
        "jenkins", "aws", "gcp", "azure", "linux", "postgres", "mysql", "mongodb", "redis",
        "kafka", "spark", "hadoop", "airflow", "jira", "figma", "sketch", "photoshop", "latex",
        "vscode", "ci/cd", "datadog", "grafana", "prometheus", "bazel", "blender",
        # creative / design tools
        "adobe", "creative suite", "illustrator", "indesign", "after effects", "premiere",
        "invision", "solidworks", "creo", "cinema 4d", "fusion 360", "autocad", "miro",
    )),
    ("Domains", (
        "machine learning", " ml ", "deep learning", "nlp", "computer vision", " cv ",
        "compiler", "distributed systems", "security", "cryptography", "robotics", "ui/ux",
        " ux", " ui ", " 3d", "graphics", "data science", "back end", "backend", "front end",
        "frontend", "devops", "cloud", "embedded", "networking", "databases", "algorithms",
        "blockchain", "reinforcement learning", "formal verification", "type theory",
        "operating systems",
        # design / creative domains
        "design", "branding", "prototyping", "photography", "videography", "typography",
        "animation", "motion graphics", "illustration", "industrial design",
    )),
    ("Soft skills", (
        "leadership", "communication", "teamwork", "mentoring", "mentorship", "collaboration",
        "project management", "public speaking", "presentation", "agile", "scrum", "writing",
        "stakeholder",
    )),
]


CATEGORIES = [label for label, _ in _RULES]  # the canonical category set
_CANON = {c.lower(): c for c in CATEGORIES}


def classify_skill(name: str) -> str:
    """Coarse category for a skill name, or "" if unknown (the UI groups those under Other)."""
    n = f" {(name or '').lower().strip()} "
    for label, keywords in _RULES:
        if any(k in n for k in keywords):
            return label
    return ""


def normalize_category(raw: str, name: str = "") -> str:
    """Clamp a category to the canonical set (case-insensitively, so an LLM's "Soft Skills"
    maps to "Soft skills"); anything else falls back to classifying the name."""
    return _CANON.get((raw or "").strip().lower()) or classify_skill(name)

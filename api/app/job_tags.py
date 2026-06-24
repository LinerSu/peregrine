"""Deterministic per-job tags pulled from a posting (no LLM): the required degree level, the
concrete skills/languages it asks for, and the finer domains/fields it touches. Regex,
**word-bounded where the token allows** (`\\b` on alphanumeric names, so "Scala"∉"scalable",
"SQL"∉"MySQL", "ML"∉"HTML") — special tokens like C++/C# and multi-word phrases are matched
literally. Precision over recall — only unambiguous tokens, so a posting isn't mis-tagged.
"""
from __future__ import annotations

import re

# Canonical skill name -> a word-boundary regex (matched against the lowercased text).
_SKILLS: dict[str, str] = {
    "Python": r"\bpython\b", "JavaScript": r"\bjavascript\b", "TypeScript": r"\btypescript\b",
    "Java": r"\bjava\b", "C++": r"c\+\+", "C#": r"c#", "Golang": r"\bgolang\b",
    "Rust": r"\brust\b", "Ruby": r"\bruby\b", "PHP": r"\bphp\b", "Swift": r"\bswift\b",
    "Kotlin": r"\bkotlin\b", "Scala": r"\bscala\b", "OCaml": r"\bocaml\b", "Haskell": r"\bhaskell\b",
    "Rocq/Coq": r"\brocq\b|\bcoq\b", "SQL": r"\bsql\b", "MATLAB": r"\bmatlab\b", "Perl": r"\bperl\b",
    "Julia": r"\bjulia\b", "Solidity": r"\bsolidity\b", "Verilog": r"\bverilog\b", "VHDL": r"\bvhdl\b",
    "HTML/CSS": r"\bhtml\b|\bcss\b", "React": r"\breact\b", "Vue": r"\bvue\b", "Angular": r"\bangular\b",
    "Node.js": r"\bnode\.?js\b", "Django": r"\bdjango\b", "Flask": r"\bflask\b", "FastAPI": r"\bfastapi\b",
    "Spring": r"\bspring boot\b|\bspring framework\b", "PyTorch": r"\bpytorch\b",
    "TensorFlow": r"\btensorflow\b", "JAX": r"\bjax\b", "Keras": r"\bkeras\b", "Docker": r"\bdocker\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b", "Git": r"\bgit\b|\bgithub\b|\bgitlab\b",
    "Terraform": r"\bterraform\b", "AWS": r"\baws\b|amazon web services", "GCP": r"\bgcp\b|google cloud",
    "Azure": r"\bazure\b", "Linux": r"\blinux\b", "PostgreSQL": r"\bpostgres", "MySQL": r"\bmysql\b",
    "MongoDB": r"\bmongodb\b", "Redis": r"\bredis\b", "Kafka": r"\bkafka\b",
    "Spark": r"\b(?:apache spark|spark streaming|spark sql|pyspark)\b",
    "Figma": r"\bfigma\b",
}

# Canonical domain/field -> a word-boundary regex.
_DOMAINS: dict[str, str] = {
    "Machine Learning": r"machine learning|\bml\b|deep learning|neural network",
    "NLP": r"\bnlp\b|natural language processing", "Computer Vision": r"computer vision",
    "Compilers": r"\bcompiler", "Distributed Systems": r"distributed systems",
    "Security": r"\bsecurity\b|cryptograph", "Robotics": r"\brobotics\b",
    "UI/UX": r"ui/ux|ux design|user experience|user interface",
    "3D/Graphics": r"\b3d\b|computer graphics|\brendering\b", "Data Science": r"data science",
    "Backend": r"back ?-?end", "Frontend": r"front ?-?end",
    "DevOps/Infra": r"\bdevops\b|infrastructure|site reliability|\bsre\b",
    "Cloud": r"\bcloud\b",
    "Embedded": r"\bembedded\b(?=\s*(?:systems?|software|firmware|device|hardware|linux|programming|engineer|developer))",
    "Databases": r"\bdatabase",
    "Blockchain": r"\bblockchain\b", "Formal Verification": r"formal verification|theorem prov",
}

_SKILL_RE = {name: re.compile(pat) for name, pat in _SKILLS.items()}
_DOMAIN_RE = {name: re.compile(pat) for name, pat in _DOMAINS.items()}


def extract_level(text: str) -> str:
    """Highest degree the posting asks for (PhD > MS > BS), or "" if none mentioned."""
    t = (text or "").lower()
    if re.search(r"ph\.?\s?d|doctoral|doctorate", t):
        return "PhD"
    if re.search(
        r"master'?s|\bm\.?sc\b|m\.eng"
        r"|\bm\.?s\.?\b(?!\s*(?:office|word|excel|teams|sql|outlook|access|visio|sharepoint|project|dynamics))",
        t,
    ):
        return "MS"
    if re.search(r"bachelor'?s|\bb\.?s\.?\b|\bb\.?sc\b|undergraduate degree", t):
        return "BS"
    return ""


def extract_skills(text: str, limit: int = 12) -> list[str]:
    """Concrete required skills/languages named in the posting (deduped, capped)."""
    t = (text or "").lower()
    return [name for name, rx in _SKILL_RE.items() if rx.search(t)][:limit]


def extract_domains(text: str, limit: int = 6) -> list[str]:
    """Finer fields/domains the posting touches."""
    t = (text or "").lower()
    return [name for name, rx in _DOMAIN_RE.items() if rx.search(t)][:limit]

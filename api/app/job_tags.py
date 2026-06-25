"""Deterministic per-job tags pulled from a posting (no LLM): the required degree level, the
concrete skills/languages it asks for, and the finer domains/fields it touches. Regex,
**word-bounded where the token allows** (`\\b` on alphanumeric names, so "Scala"∉"scalable",
"SQL"∉"MySQL", "ML"∉"HTML") — special tokens like C++/C# and multi-word phrases are matched
literally. Precision over recall — only unambiguous tokens, so a posting isn't mis-tagged.
"""
from __future__ import annotations

import re
from collections import Counter

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


# Common words that carry no search signal — filtered so the keyword cap holds meaningful terms.
_KW_STOP = frozenset(
    """a an and are as at be by for from has have had he her his in is it its of on or our that the to was were will with
    you your we us they them their this these those i me my mine ours but if into more most no nor not now off once only
    other out over own same so some such than then there through too under until up very what when where which while who
    whom why would can could should did do does doing about above after again all also am any because been before being
    below between both during each few further here how all work team company role join looking strong experience years
    ability across including like new help build using within across well also able etc per via plus across""".split()
)
_KW_RE = re.compile(r"[a-z][a-z0-9+#./-]{2,}")  # words >=3 chars, starting with a letter (keeps c++, node.js)


def extract_keywords(text: str, limit: int = 300) -> str:
    """A compact bag of the posting's most salient words, for DESCRIPTION-level relevance recall
    (the curated skill/domain tags are vocab-capped, so a query like "infrastructure"/"payments"
    that isn't a tag would otherwise miss). Frequency-ranked and stopword-filtered, space-joined.
    The cap (300) recovers ~94-100% of real JD-body content (postings average ~400 unique
    significant words, so the top 300 by frequency capture essentially everything that recurs) at
    ~30% less stored text than keeping every word."""
    counts: Counter[str] = Counter()
    for raw in _KW_RE.findall((text or "").lower()):
        w = raw.strip("./-")  # the token class allows internal ./- (node.js, ci/cd) but would
        if len(w) >= 3 and w not in _KW_STOP:  # otherwise swallow trailing sentence punctuation
            counts[w] += 1
    return " ".join(w for w, _ in counts.most_common(limit))

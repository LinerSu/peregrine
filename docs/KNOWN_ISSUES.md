# Known issues

Open defects and gaps live in the **GitHub issue tracker**, not in this file:
<https://github.com/LinerSu/peregrine/issues>

They used to be listed here. Two lists rot — one gets updated when something is fixed and
the other quietly lies — so the tracker is the single source of truth. It also does things
a markdown file can't: a PR closes an issue with `Closes #N`, anyone can comment or claim
one, and `good first issue` marks the ones that are a reasonable first contribution.

**Filing one:** use the templates in `.github/ISSUE_TEMPLATE/` — keep their headings, so
every issue reads the same way for a person skimming and for a coding agent using it as a
work order. Label it `bug` / `enhancement` / `security` / `tests`, plus `ux` when the
behaviour is defensible but confusing, and `good first issue` when it's self-contained and
the fix is obvious once you're looking at the code.

**Never put personal data in an issue.** Postings, employers, profile contents and file
paths from a real search are the user's private context — describe the *shape* of the
problem and use placeholder names (Acme, Initech) in examples.

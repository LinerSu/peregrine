# Your evidence library

Give Peregrine your own long-form writing and the cover-letter writer will quote the parts
that fit a given posting.

**Two ways in.** On the **Profile** tab, *What Peregrine knows about you* has an upload
control and shows what each file contributes. Or copy files straight into
`data/evidence/` — same folder, same result. The panel also tells you when the app is
working from too little, which is the state that makes letters read generic.

## Why it exists

A letter written from your profile alone can only re-narrate your CV. Profile entries are
a line or two each, so the letter restates what the reader is about to see anyway — and
that's what makes generated letters feel fluent and say nothing.

The detail that actually persuades lives somewhere else: why you made a design decision,
what failed first, the number that made a project worth doing. That's in your write-ups,
not your résumé.

## What to put there

Anything you've written about your own work:

- project write-ups, design docs, post-mortems, retrospectives
- papers and abstracts (`.pdf` works — the text is extracted)
- talk notes and slide text
- substantial pull-request or release descriptions
- notes on what you'd do differently next time

Readable formats: `.md`, `.markdown`, `.txt`, `.tex`, `.pdf`. Subfolders are fine.

## How it's used

Each file is split into passages — at your markdown headings where you have them, at
paragraph groups otherwise — and every passage is scored against the posting's required
skills and title. The best two or three go to the letter writer, attributed by file name
so it can say where a claim came from.

Matching is **deterministic keyword overlap**: no tokens are spent, and External and
Internal mode select exactly the same passages. The trade-off is recall — a passage that
describes the same work in different words than the posting uses will score low. Headings
that name the technology and the problem help more than clever titles.

Nothing is invented. The writer is still told to ground every claim in what you actually
have; the library gives it better raw material, not permission to embellish.

## Say what you want next

The forward-looking paragraph needs the one thing no CV contains — your intent. Set it in
the **Profile** tab, or add it to `config/profile.yml` by hand.

**It is not a search filter.** Your target roles already decide which jobs get kept; this
decides what a letter argues you're moving *toward*. "I'm looking for compiler roles"
tells a hiring team nothing they can't infer from your application. Write a claim about
the work:

```yaml
goal: >
  Move from research prototypes into tooling that ships to other engineers — I want the
  analysis I build to run in someone's CI, not just in a paper.
```

Without it, a letter can only describe where you've been.

## Privacy

`data/evidence/` is gitignored and blocked by the pre-commit guard. It's the most personal
material the app holds, and it never leaves your machine except as passages inside a letter
you asked for.

## Next

- **Prepare & apply** — where the letter is drafted and reviewed.
- **External vs Internal mode** — both draft from the same selected passages.

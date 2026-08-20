# Demo & test datasets

Sometimes you want a **fully populated** app — to explore features, take a screenshot, or
test something — without touching your own data. Peregrine ships with demo personas you can
switch on, and supports a private test dataset that never leaves your machine.

## Switch on a demo persona

```bash
./scripts/dataset.sh ai-engineer   # then refresh the page
./scripts/dataset.sh               # show the active dataset + what's available
./scripts/dataset.sh off           # back to your own config/ + data/
```

Each persona is a fictional but realistic person (invented name, companies, schools) with a
profile, jobs, fit evaluations, upskilling notes, and applications — so every tab fills in.
Personas: `ai-engineer` · `ux-designer` · `chem-phd` · `bio-scientist` · `law-student`.

The switch only changes the API's data and reflects on **refresh** — no rebuild.

## How it stays isolated

A persona is generated into a separate, **gitignored** `.demo/<persona>/` directory. The app
reads and writes only that — your real `config/` and `data/` are left alone. To reset a
persona, delete its dir and re-run the switch.

**What the switch does not move is the files themselves.** Your real `config/` and `data/`
stay at their normal paths, so anything reading the repo *directly* — a local CLI in
Internal mode, an editor, a script — still sees them. Internal mode's worker resolves its
paths from `/api/health` for exactly this reason. If you drive the app some other way while
a dataset is active, don't assume `data/` is the demo copy: it isn't.

## A private test profile (kept out of the repo)

`dataset.sh <name>` also accepts a name that *isn't* a built-in persona, as long as you've
placed your own data under `.demo/<name>/`. That's how a personal test résumé you don't want
committed stays isolated — `.demo/` is gitignored, so it never leaves your machine, and your
live `config/` / `data/` stay reserved for your real profile.

## Next

- **Privacy & compliance** — what stays local and what (briefly) goes out.

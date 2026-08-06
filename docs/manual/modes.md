# External vs Internal mode

The AI features (fit scoring, CV parsing, drafting) can run two ways. The switch is in the
top bar and applies everywhere — pick whichever fits your budget. Both do the same things.

## External (default)

The app calls an AI provider directly using a key you set in `.env`:

```bash
LLM_PROVIDER=anthropic          # or openai / ollama / mock
ANTHROPIC_API_KEY=sk-...
```

- Billed per token by that provider.
- With no key (`mock`), every screen still works, but AI answers are placeholders — fine for
  trying the app, not for real evaluations.

## Internal (Claude)

Drives Claude in a **local terminal** embedded in the page, on **your own Anthropic
subscription** — no API key, no per-token cost. Use this if you'd rather run on your existing
plan than pay the metered API.

Internal mode needs [`ttyd`](https://github.com/tsl0922/ttyd) and
[Claude Code](https://claude.com/claude-code) installed locally. The simplest setup:

```bash
./scripts/install-terminal-service.sh   # installs a background user service
```

Then just click **Internal (Claude)** in the top bar. (Or run `./start.sh` to bring up the
stack and the terminal together for one session.) The terminal is bound to `127.0.0.1` —
local-only; never expose it.

### Using a different CLI

The terminal will run whatever CLI you point it at — `PEREGRINE_TERMINAL_CMD` is read by
both `scripts/terminal.sh` and `scripts/install-terminal-service.sh`:

```bash
PEREGRINE_TERMINAL_CMD=codex ./scripts/terminal.sh              # one session
PEREGRINE_TERMINAL_CMD=codex ./scripts/install-terminal-service.sh   # or the background service
```

Pair it with `PEREGRINE_TERMINAL_PORT` to run two CLIs side by side. These are **shell**
variables, not compose ones — putting them in `.env` will not work, because that file is
read by Docker and the terminal runs on the host.

**What actually works today with a non-Claude CLI.** Everything deterministic: reading
`data/jobs/<id>.md` and `config/profile.yml`, and `curl`ing any store-only route. The API
has no authentication and does not care which CLI is calling it.

**What does not.** The guided prompts Internal mode hands you — "evaluate fit for
2026-001", "draft a cover letter for 2026-001" — are bare phrases that only work because
Claude Code auto-loads `.claude/skills/peregrine/SKILL.md` and matches its frontmatter.
Codex discovers skills only under `$CODEX_HOME/skills` (default `~/.codex/skills`), with no
repo-local equivalent, so the same phrase arrives as an unqualified request. Until that is
bridged, treat a non-Claude CLI as: launches fine, drives the API fine, but you will have
to tell it what to do rather than pasting the one-liner.

The rubrics it would follow — `.agents/skills/*/SKILL.md` — are already vendor-neutral, so
it is only the router that is Claude-specific.

## Troubleshooting the terminal

**"Port 7681 is already in use" when running `./start.sh` / `terminal.sh`** — three cases:

1. **The service is already running (most common — this is fine).** If you installed the
   background service, the terminal is *already there*; nothing needed to start. Check with
   `systemctl --user status peregrine-terminal`, then just click **Internal (Claude)**.
2. **Ubuntu's packaged `ttyd` service.** `sudo apt install ttyd` enables a *root login
   shell* on the same port — you'd see a username/password prompt instead of Claude.
   Disable it once: `sudo systemctl disable --now ttyd.service`.
3. **Something else owns the port.** Run on another port:
   `PEREGRINE_TERMINAL_PORT=7682 ./scripts/terminal.sh`.

**Terminal shows a shell prompt instead of your CLI** — it isn't installed or logged in on
the host: install it, run it once to sign in, then restart the service
(`systemctl --user restart peregrine-terminal`). If you installed the CLI through a version
manager (nvm, asdf), re-run `./scripts/install-terminal-service.sh` — the unit bakes in the
CLI's directory at install time, so it moves when your toolchain does.

## How to choose

- **Have API budget / want it fully automatic?** → External with a key.
- **Have a Claude subscription / want zero per-token cost?** → Internal.
- **Just exploring?** → mock (no key) is fine; switch on a real mode when you want real output.

## Next

- **Edit your data directly** — files behind the app.
- **Privacy & compliance** — what leaves your machine (and what doesn't).

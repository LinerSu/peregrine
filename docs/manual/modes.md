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

## How to choose

- **Have API budget / want it fully automatic?** → External with a key.
- **Have a Claude subscription / want zero per-token cost?** → Internal.
- **Just exploring?** → mock (no key) is fine; switch on a real mode when you want real output.

## Next

- **Edit your data directly** — files behind the app.
- **Privacy & compliance** — what leaves your machine (and what doesn't).

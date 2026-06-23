# Install & open

Get Peregrine running on your machine in about five minutes. Everything runs locally — your
data never leaves your computer.

## Prerequisites

- **Docker** + **Docker Compose** (Docker Desktop on Mac/Windows, or Docker Engine on Linux).
- That's it for the basic path. You don't need an API key — Peregrine ships with a **mock**
  assistant so every screen works out of the box. (Add a key later for real AI answers — see
  *External vs Internal mode*.)

## Run it

```bash
git clone https://github.com/LinerSu/peregrine.git
cd peregrine
cp .env.example .env          # the "mock" provider works with no API key
docker compose up --build     # first run builds the images
```

When it finishes, open:

- **Web app → http://localhost:5173**
- API health → http://localhost:8000/api/health (you normally won't need this)

You'll land on the **Jobs** tab with an empty list — that's expected on a fresh install.
Your real profile and jobs are private to your machine, so nothing is pre-filled.

## What you see

- A top bar with the **Peregrine** logo, an **External / Internal** mode switch, and a
  **Docs** button (this manual).
- A left **assistant** panel — a chat where you can type things like *"find jobs matching my
  CV"*.
- Tabs: **Jobs · Applications · Insights · Targets · Profile / CV · Upskilling**.

## Want to see it populated first?

To explore a fully filled-in app (a fictional demo person) before adding your own data:

```bash
./scripts/dataset.sh ai-engineer   # then refresh the page
./scripts/dataset.sh off           # switch back to your own data
```

See *Demo & test datasets* for more.

## Next

- New here? Read **What is Peregrine** for the big picture.
- Ready to use it? Jump to **Find jobs**.

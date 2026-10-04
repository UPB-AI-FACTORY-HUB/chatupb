# Local Development

Fork-specific setup and testing notes for chatupb, not upstream Open WebUI documentation.

chatupb's backend calls upbot server-to-server (`UPBOT_BASE_URL`). Full end-to-end testing of the `chat` channel also needs upbot's own dependencies (RAG server, warehouse) up; see upbot's local dev docs for that.

## Local dev (no Docker), the fast path

Three processes, each in its own terminal:

```bash
# 1. upbot, from the upbot repo
cd path/to/upbot && SERVER_PORT=8090 uv run upbot-server
# upbot defaults to :8080, same as chatupb's backend below - set SERVER_PORT
# on one of them to avoid the collision; 8090 here is just an example

# 2. chatupb backend
cd backend && uv run bash dev.sh   # :8080 by default

# 3. chatupb frontend
npm install
npm run dev
```

Verify it: open the frontend URL, send a chat message, confirm you get a reply. There's no automated test suite; `pytest`/`pytest-docker` and `vitest`/`cypress` are declared as dependencies, but there are no test files under `backend/` and no Cypress specs, and `npm run test:frontend` passes only because Vitest runs with `--passWithNoTests`. This manual check is the way to verify a change for now.

## .env setup

```bash
cp .env.example .env
```

Then set:

- `WEBUI_SECRET_KEY`. Only matters for the `dev.sh` path above: it's required there, and the app hard-crashes on startup without it when auth is enabled. Generate one (`openssl rand -hex 32`) and set it in `.env`, or run `backend/start.sh` instead of `dev.sh`, which auto-generates and persists one for you. The Docker path (below) always auto-generates its own regardless of `.env`, since `docker-compose.yaml` forces this variable blank and the container's entrypoint is `start.sh`.
- `UPBOT_BASE_URL`, value depends on how upbot is running:
  - local dev (`uv run upbot-server`, no Docker): `http://localhost:8090` (or whatever `SERVER_PORT` you set)
  - via Docker compose, both containers on `shared-net`: `http://upbot:8080`
- `UPBOT_API_KEYS`, a JSON map of channel to key, e.g. `{"chat": "your-upbot-api-key"}`, matching a key upbot's `API_KEYS` issues for the `chat` channel.
- `ENABLE_UPBOT_API=true` to turn the integration on.

Speech-to-text (Spanish, on-server Whisper) is also configured via `.env` — see [speech-to-text.md](speech-to-text.md) for `AUDIO_STT_ENGINE`, `WHISPER_LANGUAGE`, `WHISPER_MODEL`, privacy, and browser limits.

## Docker

```bash
docker network create shared-net || true  # one-time; skip if it already exists
docker compose up -d
```

`docker-compose.yaml` joins `shared-net`, shared with other local projects, specifically so the backend can reach upbot server-to-server (`http://upbot:8080`) without hitting browser CORS. If upbot isn't already up on `shared-net`, requests to it fail.

## Fork notes

Three things that do not behave the way you would expect:

- **A model's database row overrides the code.** If a `model` row already exists for a model id, its name and metadata win over whatever the connector returns. Renaming a model or changing its capabilities in code has no visible effect until that row is updated too.
- **`backend/open_webui/static/` is not source.** It is wiped and refilled from the frontend build output every time the backend starts. Edit `static/static/` instead.
- **The frontend build needs extra memory.** `Dockerfile` raises Node's heap for `npm run build`; without it the build runs out of memory.

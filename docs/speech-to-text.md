# Speech-to-text (Spanish)

Fork-specific notes for chatupb microphone / STT. Upstream Open WebUI supports several engines; this fork is configured for **on-server Whisper** so student audio is not sent to unapproved third parties.

## Engine in use

| Setting | Value | Meaning |
|---------|--------|---------|
| `AUDIO_STT_ENGINE` | empty (`""`) | **Whisper (Local)** via faster-whisper on the chatupb backend |
| `WHISPER_LANGUAGE` | `es` | Force Spanish for all transcriptions (overrides per-user language) |
| `WHISPER_MODEL` | `small` | Better Spanish accuracy than the upstream default `base` |

Do **not** set `AUDIO_STT_ENGINE` to `web`, `openai`, `deepgram`, `azure`, or `mistral` for student use unless you have an approved provider and privacy review.

Defaults live in [`.env.example`](../.env.example) and [`docker-compose.yaml`](../docker-compose.yaml).

## Where audio is processed

```
Browser (MediaRecorder)
  → upload to chatupb  POST /api/v1/audio/transcriptions
  → faster-whisper on the chatupb server
  → transcript text returned to the chat input
```

| Path | Audio destination |
|------|-------------------|
| **Default (local Whisper)** | chatupb server only (files under the app data/cache volume) |
| Web API engine (`web`) | Browser / OS vendor (often Google on Chrome, Apple on Safari) — **not recommended** |
| Cloud engines | External APIs — **not used** by fork defaults |

Whisper language codes are ISO-639-1: use **`es`**. Regional tags like `es-BO` are not Whisper language codes. The Web Speech fallback maps bare `es` → `es-BO` for browsers that want BCP-47.

## Browser support

| Browser | Local Whisper path | Notes |
|---------|-------------------|--------|
| **Chrome** (desktop / Android) | Supported | MediaRecorder → server Whisper |
| **Safari / mobile Safari** | Supported over **HTTPS** (or localhost) | Falls back to `audio/mp4` when WebM is unavailable; mic requires a secure context |
| Web API engine | Not supported for student use | Sends audio to the browser vendor; language is set from user settings (default `es-BO`) only as a fallback |

## How to verify

There is no automated STT test suite (see [local-dev.md](local-dev.md)). Manual check:

1. Start chatupb with the STT env vars above (copy from `.env.example` or use Docker Compose).
2. Admin → Settings → Audio: Speech-to-Text Engine should be **Whisper (Local)** / empty.
3. In Chrome: open a chat, click the mic, speak a Spanish sentence, confirm the transcript appears in the chat input.
4. On mobile Safari (HTTPS deployment or tunnel): same check; allow microphone permission when prompted.

## Ops notes

- The first transcription downloads the Whisper `small` model into the data/cache directory (needs disk space and CPU). Later runs reuse the cached model.
- `WHISPER_LANGUAGE=es` is a strict admin override. To allow per-user language (or auto-detect), clear `WHISPER_LANGUAGE` and set Settings → Audio → Language (default UI value is `es`).
- User Settings → Audio → Web API remains available for power users but is discouraged for privacy.

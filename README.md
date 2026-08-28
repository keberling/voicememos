# Voice Portal

Multi-user web app for iPhone Action Button dumps. You record anything — ideas, lists, tasks, job notes, family stuff, reminders, half-baked thoughts. Shortcuts POSTs the audio with your personal token. Voice Portal transcribes it through an OpenAI-compatible LLM router, then decides whether to merge into an existing note or create a new categorized one.

Nothing is too small. Nothing is dropped. Grocery lists are one example, not the product.

## What it does

- Microsoft Entra (Azure AD) sign-in in the browser
- Personal ingest token (`vnp_…`) for the iPhone (no SSO on the phone)
- Shared iOS shortcut template with Import Questions for URL + token
- Transcribe → structure → merge-or-create for every dump
- Named lists, action items, ideas, entities, categories, tags
- Dark UI: Setup, Notes, note detail, Settings
- Users are isolated. Tokens are passwords. Rotate kills the old token.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # then edit
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000`. After Microsoft login, Setup is first until a dump processes successfully.

```bash
pytest
```

## Environment

| Variable | Purpose |
| --- | --- |
| `APP_NAME` | UI title (default Voice Portal) |
| `APP_BASE_URL` | Public URL, no trailing slash. Redirect is `{APP_BASE_URL}/auth/callback` |
| `SECRET_KEY` | Session cookie signing |
| `DATABASE_URL` | SQLite or Postgres (`postgresql+psycopg://…`) |
| `UPLOAD_DIR` | Audio files |
| `MAX_UPLOAD_MB` | Ingest 413 above this |
| `AZURE_AD_CLIENT_ID` | Entra app |
| `AZURE_AD_CLIENT_SECRET` | Entra app |
| `AZURE_AD_TENANT_ID` | GUID or `common` |
| `ALLOWED_EMAILS` | Optional comma list. Empty = any signed-in Microsoft user |
| `SHORTCUT_ICLOUD_URL` | iCloud share link for the template shortcut |
| `SHORTCUT_FILE_URL` | Optional publicly reachable `.shortcut` file |
| `LLM_BASE_URL` | OpenAI-compatible router, include `/v1` if the router needs it |
| `LLM_API_KEY` | Router key |
| `LLM_MODEL` | Chat model |
| `STT_BASE_URL` | Optional, defaults to `LLM_BASE_URL` |
| `STT_API_KEY` | Optional, defaults to `LLM_API_KEY` |
| `STT_MODEL` | Default `whisper-1` |

Router only. Do not hardcode OpenAI, xAI, or Groq in config — point `LLM_BASE_URL` at whatever you run.

## Microsoft Entra

App registration:

- Redirect URI (web): `{APP_BASE_URL}/auth/callback`
- Scopes: `openid profile email User.Read`
- Client secret in `AZURE_AD_CLIENT_SECRET`

Sessions are cookies. Logout clears the cookie.

## iPhone

Phones cannot do SSO. After login, each user gets `vnp_xxxxxxxx`. That token **is** the user tag. Copy it from Setup or Settings. Rotate from Settings; the old token dies.

The app hosts the shared template at `{APP_BASE_URL}/shortcuts/Voice-Dump.shortcut`. See [`shortcuts/README.md`](shortcuts/README.md). iOS Shortcuts cannot put Recorded Audio into a Form text field — use Request Body: **File** and `Authorization: Bearer {token}`.

Setup page is the first thing after login if there is no successful ingest yet, and stays in the nav as **Setup**.

Ingest:

```
POST {APP_BASE_URL}/api/v1/ingest
multipart file=  OR  raw audio body (Shortcuts Request Body: File)
token: form, query, or Authorization: Bearer
tags, title, source optional
→ 202 { id, status: "queued", title }
```

Every ingest is processed. Nothing is discarded because the topic looks unimportant.

## Merge rules

After transcript, the worker loads that user's last 20 notes plus notes whose title, tags, categories, lists, or action items overlap the new transcript.

Merge only if the model says `merge`, `target_note_id` is owned by this user, and `confidence >= 0.6`. Invalid or foreign ids create a new note. Parse failure still creates a note with the raw transcript in ideas (`ready` + warning). If structuring fails, audio and transcript are kept (`error`, Retry).

Named lists union by list name. Unrelated lists are never smashed into one blob.

## API

JSON APIs accept the session cookie or `Authorization: Bearer vnp_…`.

- `GET /health` public
- `GET /auth/login` `GET /auth/callback` `GET /auth/logout`
- `GET /api/v1/me`
- `POST /api/v1/me/token/rotate`
- `POST /api/v1/ingest`
- `GET /api/v1/notes?q=&tag=&category=`
- `GET PATCH DELETE /api/v1/notes/{id}`
- `POST /api/v1/notes/{id}/retry`
- `GET /api/v1/notes/{id}/audio` owner only

## Coolify / Docker

Use the included `Dockerfile`. Give the container a **persistent volume** at `/data` (SQLite + uploads). Set `APP_BASE_URL` to the public HTTPS URL. Entra redirect must match.

Postgres is better in production:

```
DATABASE_URL=postgresql+psycopg://user:pass@host:5432/voiceportal
UPLOAD_DIR=/data/uploads
```

Still mount `/data` for audio.

### What must be real in Docker on Coolify

This repo is a real backend: multipart ingest, durable SQLite/Postgres, disk audio, background worker, Entra OIDC, per-user tokens.

On Coolify you must supply:

1. Entra app registration with the public callback URL
2. Persistent volume for `/data` (or object storage later — not in v1)
3. `APP_BASE_URL` HTTPS
4. LLM router `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL`
5. `SECRET_KEY` and `SHORTCUT_ICLOUD_URL`
6. Optional Postgres instead of SQLite

If Entra is not wired yet, the UI login button will say so. Ingest still works with a user's `vnp_` token once that user exists (created on first successful Microsoft login).

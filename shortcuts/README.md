# iOS shortcut templates

Voice Portal does **not** generate a unique signed `.shortcut` file per user. iOS requires Apple-signed shortcut files, which is a Mac signing problem.

Use **one shared template** for everyone. Each user pastes their own Ingest URL and token at import time via Shortcuts Import Questions.

## Voice Dump (Action Button)

Build once on an iPhone, share via iCloud, set `SHORTCUT_ICLOUD_URL` to that share link.

Required actions:

1. **Record Audio** — Stop Recording: On Tap. Do not save to Photos.
2. **Get Contents of URL**
   - URL = Import Question **Ingest URL** (example `https://your.app/api/v1/ingest`)
   - Method `POST`
   - Body `Form`
   - `file` = Recorded Audio
   - `token` = Import Question **Token** (`vnp_…`)
   - `source` = `ios-shortcut`
   - `tags` optional
3. **Show Notification** using the JSON `title` and `status` from the response.

Then: Settings → Action Button → Shortcut → Voice Dump.

## Process Voice Memo (optional Share Sheet)

Same POST. `file` = Shortcut Input (Audio). Same token and ingest URL import questions.

## After token rotate

Do **not** re-import unless you want to. Open the shortcut and update the Token import value or the token form field. The old token dies immediately.

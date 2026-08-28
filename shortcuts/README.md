# iOS shortcut templates

Voice Portal hosts the template at `{APP_BASE_URL}/shortcuts/Voice-Dump.shortcut`.

We cannot mint `https://www.icloud.com/shortcuts/…` from the server. That link is created only after someone imports the shortcut on an iPhone and taps Share → Copy iCloud Link. Put that in `SHORTCUT_ICLOUD_URL` for a one-tap Add button.

## Why not Form body?

Shortcuts **Form** fields are text. **Recorded Audio** is a file, so the variable picker will not let you drop the recording into `file = Recorded Audio`.

Use **Request Body: File** and put the token in a header.

## Voice Dump (Action Button)

1. **Record Audio** — Start: Immediately. Finish: On Tap. Do not save to Photos.
2. **Get Contents of URL**
   - URL = Import Question **Ingest URL**
   - Method `POST`
   - Headers: `Authorization` = `Bearer ` + Import Question **Token**
   - Request Body: **File**
   - File = Recorded Audio
3. **Get Dictionary Value** `title`, **Get Dictionary Value** `status`, **Show Notification**.

Then: Settings → Action Button → Shortcut → Voice Dump.

## Process Voice Memo (Share Sheet)

Same POST. File = Shortcut Input (Audio). Same Ingest URL and Token import questions.

## After token rotate

Do **not** re-import unless you want to. Open the shortcut and update the Token import value or the Authorization header. The old token dies immediately.

function copyText(text) {
  if (navigator.clipboard && navigator.clipboard.writeText) {
    return navigator.clipboard.writeText(text);
  }
  const el = document.createElement("textarea");
  el.value = text;
  document.body.appendChild(el);
  el.select();
  document.execCommand("copy");
  el.remove();
  return Promise.resolve();
}

document.querySelectorAll("[data-copy]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const sel = btn.getAttribute("data-copy");
    const node = document.querySelector(sel);
    if (!node) return;
    await copyText(node.textContent.trim());
    const prev = btn.textContent;
    btn.textContent = "Copied";
    setTimeout(() => {
      btn.textContent = prev;
    }, 1200);
  });
});

const checks = document.querySelector(".checks[data-note-id]");
if (checks) {
  const noteId = checks.getAttribute("data-note-id");
  checks.querySelectorAll("input[type=checkbox]").forEach((box) => {
    box.addEventListener("change", async () => {
      const items = Array.from(checks.querySelectorAll("input[type=checkbox]")).map((input) => {
        const label = input.closest("label");
        const text = label.querySelector("span").textContent;
        const pills = Array.from(label.querySelectorAll(".pill")).map((p) => p.textContent);
        return {
          text,
          due: pills[0] || null,
          project: pills[1] || null,
          checked: input.checked,
        };
      });
      await fetch(`/api/v1/notes/${noteId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ action_items: items }),
      });
    });
  });
}

const STATUS_COPY = {
  queued: "Received — queued",
  transcribing: "Transcribing audio",
  structuring: "Categorizing",
  ready: "Ready",
  error: "Failed — open the note to retry",
  merged: "Merged into another note",
};

function toast(message, kind) {
  const host = document.getElementById("toasts");
  if (!host || !message) return;
  const el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  el.textContent = message;
  host.appendChild(el);
  setTimeout(() => el.classList.add("in"), 20);
  setTimeout(() => {
    el.classList.remove("in");
    setTimeout(() => el.remove(), 300);
  }, 5000);
}

function fingerprint(notes) {
  return notes
    .map((n) => n.id + ":" + n.status)
    .sort()
    .join("|");
}

function inFlight(notes) {
  return notes.filter((n) => n.status === "queued" || n.status === "transcribing" || n.status === "structuring");
}

function updateBadge(notes) {
  const badge = document.getElementById("live-badge");
  if (!badge) return;
  const n = inFlight(notes).length;
  if (n) {
    badge.hidden = false;
    badge.textContent = String(n);
  } else {
    badge.hidden = true;
  }
}

function updateActivity(notes) {
  const host = document.getElementById("activity");
  if (!host) return;
  const busy = inFlight(notes);
  if (!busy.length) {
    host.hidden = true;
    host.innerHTML = "";
    return;
  }
  host.hidden = false;
  host.innerHTML = busy
    .map(
      (n) =>
        `<a href="/notes/${n.id}">${escapeHtml(n.title || "Voice dump")} — ${escapeHtml(STATUS_COPY[n.status] || n.status)}</a>`
    )
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const SNAP_KEY = "vp-notes-snap";
const SEED_KEY = "vp-notes-seeded";
let reloading = false;

async function pollNotes() {
  if (!document.querySelector(".top")) return;
  let notes;
  try {
    const res = await fetch("/api/v1/notes", { credentials: "same-origin" });
    if (!res.ok) return;
    notes = await res.json();
  } catch (_err) {
    return;
  }
  if (!Array.isArray(notes)) return;
  updateBadge(notes);
  updateActivity(notes);

  let prev = {};
  try {
    prev = JSON.parse(sessionStorage.getItem(SNAP_KEY) || "{}");
  } catch (_err) {
    prev = {};
  }
  const seeded = sessionStorage.getItem(SEED_KEY) === "1";
  const next = {};
  notes.forEach((n) => {
    next[n.id] = { status: n.status, title: n.title };
  });

  if (seeded) {
    for (const n of notes) {
      const before = prev[n.id];
      if (!before) {
        toast((n.title || "Voice dump") + " — " + (STATUS_COPY[n.status] || n.status), n.status);
      } else if (before.status !== n.status) {
        toast((n.title || "Voice dump") + " — " + (STATUS_COPY[n.status] || n.status), n.status);
      }
    }
  }

  const prevFp = fingerprint(Object.entries(prev).map(([id, v]) => ({ id, status: v.status })));
  const nextFp = fingerprint(notes);
  sessionStorage.setItem(SNAP_KEY, JSON.stringify(next));
  sessionStorage.setItem(SEED_KEY, "1");

  const live = document.querySelector("[data-live-notes]");
  if (live && seeded && prevFp !== nextFp && !reloading) {
    const search = document.querySelector("input[type=search]");
    if (!search || document.activeElement !== search) {
      reloading = true;
      window.setTimeout(() => window.location.reload(), 800);
    }
  }

  const notePage = document.querySelector("[data-live-note]");
  if (notePage) {
    const id = notePage.getAttribute("data-live-note");
    const current = notes.find((n) => n.id === id);
    const was = notePage.getAttribute("data-live-status");
    if (current && current.status !== was) {
      window.location.reload();
    }
  }
}

if (document.querySelector(".top")) {
  pollNotes();
  window.setInterval(pollNotes, 2500);
}

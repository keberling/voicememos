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

document.addEventListener("change", async (event) => {
  const box = event.target.closest("[data-action-toggle]");
  if (!box) return;
  const noteId = box.getAttribute("data-note-id");
  const index = box.getAttribute("data-index");
  const row = box.closest("li");
  try {
    const res = await fetch(`/api/v1/notes/${noteId}/actions/${index}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ checked: box.checked }),
    });
    if (!res.ok) throw new Error("Could not update task");
    if (row) row.classList.toggle("done", box.checked);
  } catch (_err) {
    box.checked = !box.checked;
    toast("Could not update task", "error");
  }
});

document.addEventListener("click", async (event) => {
  const btn = event.target.closest("[data-complete-note]");
  if (!btn) return;
  event.preventDefault();
  const noteId = btn.getAttribute("data-complete-note");
  btn.disabled = true;
  try {
    const res = await fetch(`/api/v1/notes/${noteId}/complete`, {
      method: "POST",
      credentials: "same-origin",
    });
    if (!res.ok) throw new Error("Could not complete note");
    const row = btn.closest(".note-row");
    if (row) {
      row.classList.add("is-done");
      row.querySelectorAll("[data-action-toggle]").forEach((input) => {
        input.checked = true;
        input.closest("li")?.classList.add("done");
      });
      btn.remove();
    }
    toast("Marked complete", "ready");
  } catch (_err) {
    btn.disabled = false;
    toast("Could not complete note", "error");
  }
});

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

function reviewStatus(note) {
  const sug = note && note.suggestions;
  return (sug && sug.status) || "";
}

function fingerprint(notes) {
  return notes
    .map((n) => n.id + ":" + n.status + ":" + reviewStatus(n))
    .sort()
    .join("|");
}

function paintReviewBar(note) {
  const bar = document.querySelector("[data-review-bar]");
  const article = document.querySelector("[data-live-note]");
  if (!bar || !article || !note || article.getAttribute("data-live-note") !== note.id) return;
  const st = reviewStatus(note) || "idle";
  const labels = {
    reviewing: "AI is reviewing this note…",
    ready: "Reviewed",
    skipped: "No extra steps needed",
    error: "Review failed",
    idle: "Waiting for AI review",
  };
  bar.className = "review-bar is-" + st;
  bar.setAttribute("data-status", st);
  const label = bar.querySelector(".review-label");
  if (label) label.textContent = labels[st] || labels.idle;
  const btn = document.querySelector("[data-review-box] button[type=submit]");
  if (btn) {
    btn.disabled = st === "reviewing";
    btn.textContent = st === "reviewing" ? "Reviewing…" : "Review again";
  }
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
    next[n.id] = { status: n.status, title: n.title, review: reviewStatus(n) };
  });

  if (seeded) {
    for (const n of notes) {
      const before = prev[n.id];
      paintReviewBar(n);
      if (!before) {
        toast((n.title || "Voice dump") + " — " + (STATUS_COPY[n.status] || n.status), n.status);
      } else if (before.status !== n.status) {
        toast((n.title || "Voice dump") + " — " + (STATUS_COPY[n.status] || n.status), n.status);
      } else if (before.review === "reviewing" && next[n.id].review && next[n.id].review !== "reviewing") {
        toast(
          next[n.id].review === "ready" ? "AI review ready" : next[n.id].review === "skipped" ? "No extra steps needed" : "AI review finished",
          next[n.id].review === "error" ? "error" : "ready"
        );
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

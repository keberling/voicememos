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

function needsReload(prev, notes) {
  const busy = new Set(["queued", "transcribing", "structuring", "merged"]);
  for (const n of notes) {
    const before = prev[n.id];
    if (!before && busy.has(n.status)) return true;
    if (before && before.status !== n.status) return true;
  }
  for (const [id, before] of Object.entries(prev)) {
    if (!notes.some((n) => n.id === id) && before.status && busy.has(before.status)) return true;
  }
  const article = document.querySelector("[data-live-note]");
  if (article) {
    const id = article.getAttribute("data-live-note");
    const n = notes.find((x) => x.id === id);
    if (n && prev[id] && prev[id].review === "reviewing" && reviewStatus(n) !== "reviewing") return true;
  }
  return false;
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
        const row = document.querySelector('.side-note[data-note-id="' + n.id + '"]');
        if (row) {
          row.classList.add("just-in");
          shakeEl(row.querySelector(".side-note-title"));
        }
      } else if (before.status !== n.status) {
        toast((n.title || "Voice dump") + " — " + (STATUS_COPY[n.status] || n.status), n.status);
        shakeEl(document.querySelector('.side-note[data-note-id="' + n.id + '"] .side-note-title'));
        const live = document.querySelector("[data-live-note]");
        if (live && live.getAttribute("data-live-note") === n.id) {
          shakeEl(live.querySelector("h1"));
        }
      }
      } else if (before.review === "reviewing" && next[n.id].review && next[n.id].review !== "reviewing") {
        toast(
          next[n.id].review === "ready" ? "AI review ready" : next[n.id].review === "skipped" ? "No extra steps needed" : "AI review finished",
          next[n.id].review === "error" ? "error" : "ready"
        );
      }
    }
  }

  sessionStorage.setItem(SNAP_KEY, JSON.stringify(next));
  sessionStorage.setItem(SEED_KEY, "1");

  const live = document.querySelector("[data-live-notes]");
  const lastReload = Number(sessionStorage.getItem("vp-reload-at") || 0);
  const cooled = Date.now() - lastReload > 5000;
  if (live && seeded && !reloading && cooled && needsReload(prev, notes)) {
    const search = document.querySelector("input[type=search]");
    if (!search || document.activeElement !== search) {
      reloading = true;
      sessionStorage.setItem("vp-reload-at", String(Date.now()));
      window.setTimeout(() => window.location.reload(), 800);
    }
  }
}

function shakeEl(el) {
  if (!el) return;
  el.classList.remove("shake");
  void el.offsetWidth;
  el.classList.add("shake");
  el.addEventListener("animationend", () => el.classList.remove("shake"), { once: true });
}

function setupThemes() {
  const root = document.documentElement;
  const saved = localStorage.getItem("vp-theme") || "night";
  root.setAttribute("data-theme", saved);
  const pick = document.querySelector("[data-theme-pick]");
  if (!pick) return;
  const sync = () => {
    pick.querySelectorAll("button[data-theme]").forEach((btn) => {
      btn.setAttribute("aria-pressed", btn.getAttribute("data-theme") === root.getAttribute("data-theme") ? "true" : "false");
    });
  };
  sync();
  pick.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-theme]");
    if (!btn) return;
    const theme = btn.getAttribute("data-theme");
    root.setAttribute("data-theme", theme);
    localStorage.setItem("vp-theme", theme);
    sync();
  });
}

if (document.querySelector(".top")) {
  setupThemes();
  pollNotes();
  window.setInterval(pollNotes, 2500);
}

function pickMime() {
  const types = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"];
  if (!window.MediaRecorder) return "";
  return types.find((t) => MediaRecorder.isTypeSupported(t)) || "";
}

function setupHoldToRecord() {
  const buttons = document.querySelectorAll("[data-hold-record]");
  if (!buttons.length) return;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    buttons.forEach((btn) => {
      btn.disabled = true;
      const em = btn.querySelector("em");
      if (em) em.textContent = "Mic not available";
    });
    return;
  }

  let recorder = null;
  let chunks = [];
  let stream = null;
  let activeBtn = null;
  let startedAt = 0;
  let sending = false;

  function setState(btn, state) {
    buttons.forEach((b) => {
      b.classList.toggle("is-recording", false);
      b.classList.toggle("is-sending", false);
      const em = b.querySelector("em");
      const strong = b.querySelector("strong");
      if (!em || !strong) return;
      if (b === btn && state === "recording") {
        em.textContent = "Release to send";
        strong.textContent = "Recording";
      } else if (b === btn && state === "sending") {
        em.textContent = "Uploading…";
      } else {
        em.textContent = "Hold to record";
        strong.textContent = b.getAttribute("data-mode") === "add" ? "Add to this note" : "New note";
      }
    });
    if (btn && state === "recording") btn.classList.add("is-recording");
    if (btn && state === "sending") btn.classList.add("is-sending");
  }

  async function start(btn) {
    if (recorder || sending) return;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (_err) {
      toast("Microphone permission denied", "error");
      return;
    }
    chunks = [];
    const mime = pickMime();
    recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    recorder.ondataavailable = (ev) => {
      if (ev.data && ev.data.size) chunks.push(ev.data);
    };
    recorder.start(200);
    startedAt = Date.now();
    activeBtn = btn;
    setState(btn, "recording");
  }

  async function stop(send) {
    const btn = activeBtn;
    const rec = recorder;
    recorder = null;
    activeBtn = null;
    if (!rec) return;
    const mime = rec.mimeType || pickMime() || "audio/webm";
    await new Promise((resolve) => {
      rec.onstop = resolve;
      try {
        rec.stop();
      } catch (_err) {
        resolve();
      }
    });
    (stream?.getTracks() || []).forEach((t) => t.stop());
    stream = null;
    const elapsed = Date.now() - startedAt;
    if (!send || elapsed < 400) {
      setState(btn, "idle");
      if (send && elapsed < 400) toast("Hold a bit longer to record", "error");
      return;
    }
    const blob = new Blob(chunks, { type: mime });
    if (!blob.size) {
      setState(btn, "idle");
      toast("No audio captured", "error");
      return;
    }
    sending = true;
    setState(btn, "sending");
    const ext = mime.includes("mp4") ? "m4a" : mime.includes("ogg") ? "ogg" : "webm";
    const fd = new FormData();
    fd.append("file", blob, "browser-memo." + ext);
    fd.append("source", "browser");
    const mode = btn.getAttribute("data-mode");
    const target = btn.getAttribute("data-target-id");
    if (mode === "add" && target) fd.append("target_note_id", target);
    try {
      const res = await fetch("/api/v1/ingest", { method: "POST", body: fd, credentials: "same-origin" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Upload failed");
      }
      const body = await res.json();
      toast(mode === "add" ? "Adding to this note…" : "New note queued…", "queued");
      if (mode !== "add" && body.id) {
        window.setTimeout(() => {
          window.location.href = "/notes/" + body.id;
        }, 600);
      }
    } catch (err) {
      toast(err.message || "Could not send recording", "error");
    } finally {
      sending = false;
      setState(btn, "idle");
    }
  }

  buttons.forEach((btn) => {
    btn.addEventListener("contextmenu", (e) => e.preventDefault());
    btn.addEventListener("pointerdown", async (e) => {
      if (e.button != null && e.button !== 0) return;
      e.preventDefault();
      btn.setPointerCapture(e.pointerId);
      await start(btn);
    });
    btn.addEventListener("pointerup", (e) => {
      e.preventDefault();
      stop(true);
    });
    btn.addEventListener("pointercancel", () => stop(false));
  });
}

setupHoldToRecord();

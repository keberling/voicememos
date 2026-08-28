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

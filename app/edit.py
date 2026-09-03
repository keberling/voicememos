from __future__ import annotations


def parse_csv(raw: str | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in (raw or "").split(","):
        text = part.strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return out


def parse_lines(raw: str | None) -> list[str]:
    return [ln.strip() for ln in (raw or "").splitlines() if ln.strip()]


def parse_action_items(raw: str | None) -> list[dict]:
    items = []
    for line in parse_lines(raw):
        checked = False
        text = line
        if text.lower().startswith("[x]"):
            checked = True
            text = text[3:].strip()
        elif text.startswith("[]"):
            text = text[2:].strip()
        if text:
            items.append({"text": text, "due": None, "project": None, "checked": checked})
    return items


def parse_lists(raw: str | None) -> dict[str, list[str]]:
    lists: dict[str, list[str]] = {}
    current = "List"
    for line in (raw or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.endswith(":") and not stripped.startswith("-"):
            current = stripped[:-1].strip() or "List"
            lists.setdefault(current, [])
            continue
        if stripped.startswith("-"):
            stripped = stripped[1:].strip()
        if stripped:
            lists.setdefault(current, []).append(stripped)
    return {k: v for k, v in lists.items() if v}


def format_lists(lists: dict | None) -> str:
    blocks = []
    for name, items in (lists or {}).items():
        lines = [f"{name}:"]
        for item in items:
            lines.append(f"- {item}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def format_action_items(items: list | None) -> str:
    lines = []
    for item in items or []:
        if isinstance(item, str):
            lines.append(item)
            continue
        mark = "[x] " if item.get("checked") else ""
        lines.append(f"{mark}{item.get('text') or ''}".strip())
    return "\n".join(lines)


def format_lines(items: list | None) -> str:
    return "\n".join(str(x) for x in (items or []) if str(x).strip())

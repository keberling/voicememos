from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.shortcut import TEMPLATES, shortcut_file

router = APIRouter(tags=["shortcuts"])

_MEDIA = "application/x-apple-shortcut"


@router.get("/shortcuts/{name}.shortcut")
def download_shortcut(name: str):
    kind = TEMPLATES.get(name)
    if kind is None:
        raise HTTPException(status_code=404, detail="Unknown shortcut")
    data, signed = shortcut_file(kind)
    filename = f"{name}.shortcut"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "X-Shortcut-Signed": "1" if signed else "0",
        "Cache-Control": "public, max-age=300",
    }
    return Response(content=data, media_type=_MEDIA, headers=headers)

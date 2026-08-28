"""Build and optionally Apple-sign the shared Voice Dump shortcuts.

We cannot mint https://www.icloud.com/shortcuts/... from this server. That
link is created only when someone with Shortcuts taps Share → Copy iCloud Link.

What we can do: generate the shortcut ourselves (one template, Import Questions
for Ingest URL + Token) and host it at /shortcuts/Voice-Dump.shortcut.

iOS 15+ refuses unsigned files. If HubSign is reachable we wrap the plist in
Apple's AEA1 signed container so Safari/Files can Add Shortcut. If signing
fails, we still serve the unsigned bplist (importable on a Mac with
`shortcuts sign --mode anyone`).
"""

from __future__ import annotations

import logging
import plistlib
from functools import lru_cache
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger("voiceportal.shortcut")

OBJECT_CHAR = "\ufffc"

# Stable IDs so the generated file is deterministic.
URL_UUID = "A1111111-1111-4111-8111-111111111111"
TOKEN_UUID = "A2222222-2222-4222-8222-222222222222"
AUDIO_UUID = "A3333333-3333-4333-8333-333333333333"
HTTP_UUID = "A4444444-4444-4444-8444-444444444444"
TITLE_UUID = "A5555555-5555-4555-8555-555555555555"
STATUS_UUID = "A6666666-6666-4666-8666-666666666666"
NOTIFY_UUID = "A7777777-7777-4777-8777-777777777777"

P_URL_UUID = "B1111111-1111-4111-8111-111111111111"
P_TOKEN_UUID = "B2222222-2222-4222-8222-222222222222"
P_HTTP_UUID = "B4444444-4444-4444-8444-444444444444"
P_TITLE_UUID = "B5555555-5555-4555-8555-555555555555"
P_STATUS_UUID = "B6666666-6666-4666-8666-666666666666"
P_NOTIFY_UUID = "B7777777-7777-4777-8777-777777777777"

# Teal-ish ARGB, microphone-ish glyph.
ICON_COLOR = 4282601983
ICON_GLYPH = 59511


def _text_token(text: str) -> dict[str, Any]:
    return {
        "Value": {"string": text, "attachmentsByRange": {}},
        "WFSerializationType": "WFTextTokenString",
    }


def _attachment(output_uuid: str, output_name: str, type_: str = "ActionOutput") -> dict[str, Any]:
    value: dict[str, Any] = {
        "OutputUUID": output_uuid,
        "OutputName": output_name,
        "Type": type_,
    }
    if type_ == "ActionOutput":
        value["OutputUUID"] = output_uuid
        value["OutputName"] = output_name
    return {
        "Value": value,
        "WFSerializationType": "WFTextTokenAttachment",
    }


def _text_with_var(output_uuid: str, output_name: str, type_: str = "ActionOutput") -> dict[str, Any]:
    token: dict[str, Any] = {"OutputName": output_name, "Type": type_}
    if type_ == "ActionOutput":
        token["OutputUUID"] = output_uuid
    return {
        "Value": {
            "string": OBJECT_CHAR,
            "attachmentsByRange": {"{0, 1}": token},
        },
        "WFSerializationType": "WFTextTokenString",
    }


def _bearer_header(token_uuid: str) -> dict[str, Any]:
    # "Bearer " is 7 characters; object-replacement char holds the Token variable.
    return {
        "Value": {
            "string": "Bearer " + OBJECT_CHAR,
            "attachmentsByRange": {
                "{7, 1}": {
                    "OutputUUID": token_uuid,
                    "OutputName": "Token",
                    "Type": "ActionOutput",
                }
            },
        },
        "WFSerializationType": "WFTextTokenString",
    }


def _text_action(text: str, action_uuid: str, output_name: str) -> dict[str, Any]:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.gettext",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "CustomOutputName": output_name,
            "WFTextActionText": text,
        },
    }


def _record_audio() -> dict[str, Any]:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.recordaudio",
        "WFWorkflowActionParameters": {
            "UUID": AUDIO_UUID,
            "CustomOutputName": "Recorded Audio",
            "WFRecordingCompression": "Normal",
            "WFRecordingStart": "Immediately",
            "WFRecordingEnd": "On Tap",
        },
    }


def _download_url(
    *,
    url_uuid: str,
    token_uuid: str,
    file_uuid: str | None,
    http_uuid: str,
    file_is_shortcut_input: bool = False,
) -> dict[str, Any]:
    """POST the audio as the raw file body. Form fields cannot take Recorded Audio."""
    if file_is_shortcut_input:
        file_var: dict[str, Any] = {
            "Value": {"Type": "ExtensionInput"},
            "WFSerializationType": "WFTextTokenAttachment",
        }
    else:
        assert file_uuid is not None
        file_var = _attachment(file_uuid, "Recorded Audio")

    headers = {
        "Value": {
            "WFDictionaryFieldValueItems": [
                {
                    "WFItemType": 0,
                    "WFKey": _text_token("Authorization"),
                    "WFValue": _bearer_header(token_uuid),
                }
            ]
        },
        "WFSerializationType": "WFDictionaryFieldValue",
    }
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.downloadurl",
        "WFWorkflowActionParameters": {
            "UUID": http_uuid,
            "CustomOutputName": "Contents of URL",
            "ShowHeaders": True,
            "Advanced": True,
            "WFHTTPMethod": "POST",
            "WFHTTPBodyType": "File",
            "WFURL": _text_with_var(url_uuid, "Ingest URL"),
            "WFHTTPHeaders": headers,
            "WFRequestVariable": file_var,
        },
    }


def _get_key(key: str, from_uuid: str, out_uuid: str, out_name: str) -> dict[str, Any]:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.getvalueforkey",
        "WFWorkflowActionParameters": {
            "UUID": out_uuid,
            "CustomOutputName": out_name,
            "WFDictionaryKey": key,
            "WFGetDictionaryValueType": "Value",
            "WFInput": _attachment(from_uuid, "Contents of URL"),
        },
    }


def _notify(title_uuid: str, status_uuid: str, action_uuid: str) -> dict[str, Any]:
    return {
        "WFWorkflowActionIdentifier": "is.workflow.actions.notification",
        "WFWorkflowActionParameters": {
            "UUID": action_uuid,
            "WFNotificationActionSound": True,
            "WFNotificationActionTitle": _text_with_var(title_uuid, "title"),
            "WFNotificationActionBody": _text_with_var(status_uuid, "status"),
        },
    }


def _import_questions() -> list[dict[str, Any]]:
    return [
        {
            "ActionIndex": 0,
            "Category": "Parameter",
            "DefaultValue": "",
            "ParameterKey": "WFTextActionText",
            "Text": "Ingest URL",
        },
        {
            "ActionIndex": 1,
            "Category": "Parameter",
            "DefaultValue": "",
            "ParameterKey": "WFTextActionText",
            "Text": "Token",
        },
    ]


def _shell(
    *,
    name: str,
    actions: list[dict[str, Any]],
    input_classes: list[str],
    types: list[str],
) -> dict[str, Any]:
    return {
        "WFWorkflowClientRelease": "18.0",
        "WFWorkflowClientVersion": "2605.0.5",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": "ActionExtension" in types,
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": ICON_GLYPH,
            "WFWorkflowIconStartColor": ICON_COLOR,
        },
        "WFWorkflowImportQuestions": _import_questions(),
        "WFWorkflowInputContentItemClasses": input_classes,
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowTypes": types,
        "WFWorkflowActions": actions,
        "WFWorkflowName": name,
    }


def voice_dump_plist() -> dict[str, Any]:
    actions = [
        _text_action("https://example.com/api/v1/ingest", URL_UUID, "Ingest URL"),
        _text_action("vnp_paste_token_on_setup_page", TOKEN_UUID, "Token"),
        _record_audio(),
        _download_url(
            url_uuid=URL_UUID,
            token_uuid=TOKEN_UUID,
            file_uuid=AUDIO_UUID,
            http_uuid=HTTP_UUID,
        ),
        _get_key("title", HTTP_UUID, TITLE_UUID, "title"),
        _get_key("status", HTTP_UUID, STATUS_UUID, "status"),
        _notify(TITLE_UUID, STATUS_UUID, NOTIFY_UUID),
    ]
    return _shell(
        name="Voice Dump",
        actions=actions,
        input_classes=[],
        types=["WatchKit", "NCWidget"],
    )


def process_voice_memo_plist() -> dict[str, Any]:
    actions = [
        _text_action("https://example.com/api/v1/ingest", P_URL_UUID, "Ingest URL"),
        _text_action("vnp_paste_token_on_setup_page", P_TOKEN_UUID, "Token"),
        _download_url(
            url_uuid=P_URL_UUID,
            token_uuid=P_TOKEN_UUID,
            file_uuid=None,
            http_uuid=P_HTTP_UUID,
            file_is_shortcut_input=True,
        ),
        _get_key("title", P_HTTP_UUID, P_TITLE_UUID, "title"),
        _get_key("status", P_HTTP_UUID, P_STATUS_UUID, "status"),
        _notify(P_TITLE_UUID, P_STATUS_UUID, P_NOTIFY_UUID),
    ]
    return _shell(
        name="Process Voice Memo",
        actions=actions,
        input_classes=["WFAVAssetContentItem", "WFGenericFileContentItem"],
        types=["ActionExtension", "WatchKit", "NCWidget"],
    )


def unsigned_bytes(plist: dict[str, Any]) -> bytes:
    return plistlib.dumps(plist, fmt=plistlib.FMT_BINARY)


def xml_plist(plist: dict[str, Any]) -> str:
    return plistlib.dumps(plist, fmt=plistlib.FMT_XML).decode("utf-8")


def sign_via_hubsign(plist: dict[str, Any], name: str) -> bytes | None:
    settings = get_settings()
    url = (settings.HUBSIGN_URL or "").strip()
    if not url or not settings.SIGN_SHORTCUTS:
        return None
    payload = {"shortcutName": name, "shortcut": xml_plist(plist)}
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "voiceportal/1.0",
        "Origin": "https://routinehub.co",
        "Referer": "https://routinehub.co/",
    }
    try:
        with httpx.Client(timeout=25.0) as client:
            response = client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        log.warning("HubSign request failed: %s", exc)
        return None
    if response.status_code != 200:
        log.warning("HubSign HTTP %s: %s", response.status_code, response.text[:200])
        return None
    data = response.content
    if len(data) >= 4 and data[:4] == b"AEA1":
        return data
    log.warning("HubSign response was not a signed shortcut (magic=%r)", data[:8])
    return None


@lru_cache
def shortcut_file(kind: str) -> tuple[bytes, bool]:
    """Return (bytes, signed). kind is voice-dump or process-voice-memo."""
    if kind == "process-voice-memo":
        plist = process_voice_memo_plist()
        name = "Process Voice Memo"
    else:
        plist = voice_dump_plist()
        name = "Voice Dump"
    signed = sign_via_hubsign(plist, name)
    if signed:
        return signed, True
    return unsigned_bytes(plist), False


TEMPLATES = {
    "Voice-Dump": "voice-dump",
    "Process-Voice-Memo": "process-voice-memo",
}

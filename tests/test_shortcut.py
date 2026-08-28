from app.shortcut import shortcut_file, voice_dump_plist
import plistlib


def test_voice_dump_uses_file_body_not_form():
    plist = voice_dump_plist()
    actions = {a["WFWorkflowActionIdentifier"]: a for a in plist["WFWorkflowActions"]}
    assert "is.workflow.actions.recordaudio" in actions
    download = actions["is.workflow.actions.downloadurl"]
    params = download["WFWorkflowActionParameters"]
    assert params["WFHTTPBodyType"] == "File"
    assert params["WFHTTPMethod"] == "POST"
    assert "WFRequestVariable" in params
    assert params["WFRequestVariable"]["Value"]["OutputName"] == "Recorded Audio"
    assert params["ShowHeaders"] is True
    questions = {q["Text"] for q in plist["WFWorkflowImportQuestions"]}
    assert questions == {"Ingest URL", "Token"}


def test_hosted_shortcut_is_public(client):
    r = client.get("/shortcuts/Voice-Dump.shortcut")
    assert r.status_code == 200
    assert r.content[:6] == b"bplist" or r.content[:4] == b"AEA1"
    parsed = None
    if r.content[:6] == b"bplist":
        parsed = plistlib.loads(r.content)
        body_types = [
            a["WFWorkflowActionParameters"].get("WFHTTPBodyType")
            for a in parsed["WFWorkflowActions"]
            if a["WFWorkflowActionIdentifier"] == "is.workflow.actions.downloadurl"
        ]
        assert body_types == ["File"]
    _ = shortcut_file

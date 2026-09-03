from app.grouping import group_notes, is_completed, open_actions, primary_group
from app.llm import parse_review_response


def test_primary_group_uses_first_category():
    note = {"categories": ["home", "family"], "tags": ["paint"]}
    assert primary_group(note) == "home"


def test_group_notes_clusters_by_category():
    notes = [
        {"title": "Paint", "categories": ["home"], "tags": [], "action_items": [], "updated_at": None},
        {"title": "Interview", "categories": ["job"], "tags": [], "action_items": [{"text": "Call", "checked": False}], "updated_at": None},
        {"title": "Gutter", "categories": ["home"], "tags": [], "action_items": [], "updated_at": None},
    ]
    groups = {g["name"]: g for g in group_notes(notes)}
    assert {n["title"] for n in groups["home"]["notes"]} == {"Paint", "Gutter"}
    assert groups["job"]["open_tasks"] == 1


def test_parse_review_skips_and_extracts_steps():
    skipped = parse_review_response('{"appropriate": false, "reason": "just a grocery list"}')
    assert skipped["appropriate"] is False
    assert skipped["status"] == "skipped"
    useful = parse_review_response(
        '{"appropriate": true, "review": "Comcast needs lead time.", "next_steps": ["Text Reid a window"], "questions": ["Is the date firm?"]}'
    )
    assert useful["status"] == "ready"
    assert useful["appropriate"] is True
    assert "Comcast" in useful["review"]
    assert useful["next_steps"] == ["Text Reid a window"]


def test_completed_when_all_tasks_checked():
    note = {"action_items": [{"text": "a", "checked": True}], "completed_at": None}
    assert is_completed(note)
    assert open_actions(note) == []

from app.grouping import group_notes, is_completed, open_actions, primary_group


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


def test_completed_when_all_tasks_checked():
    note = {"action_items": [{"text": "a", "checked": True}], "completed_at": None}
    assert is_completed(note)
    assert open_actions(note) == []

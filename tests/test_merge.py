from app.llm import parse_structure_response
from app.merge import merge_into_existing, union_named_lists


def test_union_lists_keeps_separate_names():
    existing = {"Groceries": ["milk"], "Hardware": ["screws"]}
    incoming = {"Groceries": ["Milk", "oat milk"], "Trip": ["passports"]}
    out = union_named_lists(existing, incoming)
    assert set(out) == {"Groceries", "Hardware", "Trip"}
    groceries = [x.lower() for x in out["Groceries"]]
    assert groceries.count("milk") == 1
    assert "oat milk" in out["Groceries"]
    assert out["Hardware"] == ["screws"]
    assert out["Trip"] == ["passports"]


def test_parse_fail_returns_create_with_warning():
    result = parse_structure_response("sorry I cannot")
    assert result.action == "create"
    assert result.parse_warning
    assert result.ideas


def test_parse_json_object_lists():
    raw = """
    {
      "action": "create",
      "target_note_id": null,
      "title": "Garage door",
      "summary": "Need a spring replaced",
      "categories": ["home", "vehicle"],
      "tags": ["garage"],
      "lists": {"Parts": ["torsion spring"]},
      "action_items": [{"text": "Call door shop", "due": null, "project": null}],
      "ideas": [],
      "entities": {"names": [], "places": ["Main Street"], "vendors": [], "tickets": []},
      "confidence": 0.9
    }
    """
    result = parse_structure_response(raw)
    assert result.action == "create"
    assert result.lists["Parts"] == ["torsion spring"]
    assert result.categories == ["home", "vehicle"]


def test_merge_into_existing_unions_and_keeps_wording():
    existing = {
        "title": "Family reunion",
        "summary": "Old summary",
        "categories": ["family"],
        "tags": ["july"],
        "lists": {"Food": ["brisket"]},
        "action_items": [{"text": "Book the park", "due": None, "project": None, "checked": False}],
        "ideas": ["hire a photographer"],
        "entities": {"names": ["Maya"]},
    }
    result = parse_structure_response(
        """{
          "action": "merge",
          "target_note_id": "abc",
          "title": "Family reunion food",
          "summary": "Add coleslaw and confirm the park.",
          "categories": ["family", "travel"],
          "tags": ["July"],
          "lists": {"Food": ["coleslaw"], "Kids": ["bubbles"]},
          "action_items": [{"text": "Book the park", "due": "Saturday", "project": null}],
          "ideas": ["maybe a slideshow"],
          "entities": {"names": ["maya", "Owen"]},
          "confidence": 0.8
        }"""
    )
    merged = merge_into_existing(existing, result)
    assert merged["title"] == "Family reunion"
    assert "coleslaw" in merged["lists"]["Food"]
    assert merged["lists"]["Kids"] == ["bubbles"]
    assert len([i for i in merged["action_items"] if i["text"].lower() == "book the park"]) == 1
    assert "maybe a slideshow" in merged["ideas"]
    names = [n.lower() for n in merged["entities"]["names"]]
    assert "maya" in names and "owen" in names

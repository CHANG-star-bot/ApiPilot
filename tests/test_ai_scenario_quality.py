"""Deterministic quality checks only; no model or business API calls."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from src.apipilot.ai_client import AIOutputError
from src.apipilot.ai_scenario_generator import (
    build_prompt, generate_scenarios, input_signature, parse_suggestions, validate_scenario,
)
from src.apipilot.openapi_parser import parse_openapi


PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.delenv("APIPILOT_AI_API_KEY", raising=False)
    monkeypatch.setattr(requests.sessions.Session, "request", Mock(side_effect=AssertionError("Network disabled")))


@pytest.fixture
def interface():
    return parse_openapi(PROJECT / "examples" / "ai_scenarios_openapi.json")[0]


@pytest.fixture
def document():
    return json.loads((PROJECT / "examples" / "ai_mock_response.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("strategy, value", [
    ("declared_value", 10), ("minimum", 1), ("maximum", 100),
    ("below_minimum", 0), ("above_maximum", 101),
])
def test_concrete_strategy_claim_is_checked_but_business_remains_pending(interface, document, strategy, value):
    scenario = document["scenarios"][2]
    scenario["inputs"][0].update(strategy=strategy, intended_value=value)

    result = validate_scenario(scenario, interface)

    assert result["inputs"][0]["value"] == value
    assert result["inputs"][0]["intended_value_source"] == "ai_inferred"
    assert result["review"]["input_consistency"] == "CHECKED"
    assert result["review"]["status"] == "PENDING"
    assert result["review"]["business_confirmed"] is False
    assert result["expected_result"]["confirmed"] is False


@pytest.mark.parametrize("strategy, wrong_value", [
    ("declared_value", 20), ("minimum", 2), ("maximum", 99),
    ("below_minimum", -1), ("above_maximum", 102),
])
def test_wrong_claim_rejects_entire_batch_without_rewriting_data(interface, document, strategy, wrong_value):
    document["scenarios"][2]["inputs"][0].update(strategy=strategy, intended_value=wrong_value)
    original = deepcopy(document)
    with pytest.raises(AIOutputError, match="does not match"):
        parse_suggestions(json.dumps(document), interface)
    assert document == original


@pytest.mark.parametrize("wrong_value", [True, "1", 1.0, None])
def test_value_comparison_does_not_coerce_types(interface, document, wrong_value):
    scenario = document["scenarios"][1]
    scenario["inputs"][0].update(strategy="minimum", intended_value=wrong_value)
    with pytest.raises(AIOutputError, match="does not match"):
        validate_scenario(scenario, interface)


def test_submit_claim_cannot_override_preview_mapping(interface, document):
    interface["parameters"][0] = {"name": "mode", "in": "query", "schema": {"enum": ["preview", "submit"]}}
    scenario = document["scenarios"][0]
    scenario.update(name="Submit mode", intent="Review submit behavior")
    scenario["inputs"] = [{"name": "mode", "in": "query", "strategy": "declared_value", "intended_value": "submit"}]

    with pytest.raises(AIOutputError, match="does not match"):
        validate_scenario(scenario, interface)

    # A documented parameter example has priority over enum[0], as before.
    interface["parameters"][0]["example"] = "submit"
    assert validate_scenario(scenario, interface)["inputs"][0]["value"] == "submit"


def test_correct_enum_claim_keeps_free_text_for_manual_review(interface, document):
    interface["parameters"][0] = {"name": "mode", "in": "query", "schema": {"enum": ["preview", "submit"]}}
    scenario = document["scenarios"][0]
    scenario.update(name="Submit mode", intent="An unverified business claim")
    scenario["inputs"] = [{"name": "mode", "in": "query", "strategy": "declared_value", "intended_value": "preview"}]

    result = validate_scenario(scenario, interface)

    assert result["name"] == "Submit mode"
    assert result["inputs"][0]["value"] == "preview"
    assert result["review"]["input_consistency"] == "CHECKED"
    assert result["review"]["business_confirmed"] is False
    assert any("free-text" in reason for reason in result["review"]["reasons"])


@pytest.mark.parametrize("strategy", ["omit", "user_supplied"])
def test_unresolved_or_omitted_input_cannot_claim_a_literal_value(interface, document, strategy):
    scenario = document["scenarios"][2]
    scenario["inputs"][0].update(strategy=strategy, intended_value=None)
    with pytest.raises(AIOutputError, match="cannot claim"):
        validate_scenario(scenario, interface)


@pytest.mark.parametrize("strategy", ["below_minimum", "above_maximum", "omit"])
def test_normal_scenario_cannot_explicitly_violate_supported_constraints(interface, document, strategy):
    document["scenarios"][0]["inputs"][0]["strategy"] = strategy
    with pytest.raises(AIOutputError, match="Normal scenario contradicts"):
        parse_suggestions(json.dumps(document), interface)


def test_optional_omission_is_allowed_and_still_pending(interface, document):
    interface["parameters"][0]["required"] = False
    scenario = document["scenarios"][0]
    scenario["inputs"][0]["strategy"] = "omit"
    result = validate_scenario(scenario, interface)
    assert result["review"]["input_consistency"] == "CHECKED"
    assert result["review"]["business_confirmed"] is False


def test_legacy_and_unknown_business_intent_are_never_approved(interface, document):
    document["scenarios"][0]["intent"] = "A VIP user should receive a business discount"
    result = parse_suggestions(json.dumps(document), interface)
    assert result["executable"] is False
    assert result["ai_inferred"][0]["review"]["input_consistency"] == "UNCONFIRMED"
    for scenario in result["ai_inferred"]:
        assert scenario["review"]["status"] == "PENDING"
        assert scenario["review"]["business_confirmed"] is False
        assert scenario["expected_result"]["status_code"] is None


def test_duplicate_uses_generated_value_not_strategy_category_or_name(interface, document):
    interface["parameters"][0]["schema"]["minimum"] = 10
    extra = deepcopy(document["scenarios"][0])
    extra.update(name="Another intent", category="negative")
    extra["inputs"][0]["strategy"] = "minimum"
    document["scenarios"].append(extra)

    result = parse_suggestions(json.dumps(document), interface)

    assert len(result["ai_inferred"]) == 4  # Preserve evidence; no silent deletion.
    review = result["ai_inferred"][-1]["review"]
    assert review["duplicate_of"] == document["scenarios"][0]["name"]
    assert review["duplicate_kind"] == "concrete"
    assert any("merge or change" in reason for reason in review["reasons"])
    assert review["status"] == "PENDING"


def test_input_order_does_not_hide_duplicate(interface, document):
    interface["parameters"].append({"name": "mode", "in": "query", "schema": {"default": "preview"}})
    document["scenarios"][0]["inputs"].append({"name": "mode", "in": "query", "strategy": "declared_value"})
    extra = deepcopy(document["scenarios"][0])
    extra["name"] = "Reordered input"
    extra["inputs"].reverse()
    document["scenarios"].append(extra)
    result = parse_suggestions(json.dumps(document), interface)
    assert result["ai_inferred"][-1]["review"]["duplicate_kind"] == "concrete"


def test_explicit_omit_and_absent_input_share_an_input_signature(interface, document):
    omitted = deepcopy(document["scenarios"][2])
    omitted.update(name="Explicit omission", inputs=[{"name": "limit", "in": "query", "strategy": "omit"}])
    absent = deepcopy(omitted)
    absent.update(name="No supplied input", inputs=[])
    document["scenarios"].extend([omitted, absent])
    result = parse_suggestions(json.dumps(document), interface)
    assert result["ai_inferred"][-1]["review"]["duplicate_of"] == "Explicit omission"


def test_placeholders_are_only_possible_template_duplicates(interface, document):
    document["scenarios"][0]["inputs"][0]["strategy"] = "user_supplied"
    document["scenarios"][2]["inputs"][0]["strategy"] = "user_supplied"
    result = parse_suggestions(json.dumps(document), interface)
    review = result["ai_inferred"][2]["review"]
    assert review["duplicate_kind"] == "template"
    assert review["input_consistency"] == "UNCONFIRMED"
    assert any("confirm actual data" in reason for reason in review["reasons"])


def test_unknown_body_prevents_claiming_complete_request_equality(interface, document):
    interface["has_request_body"] = True
    extra = deepcopy(document["scenarios"][0])
    extra["name"] = "Same parameters, unknown Body"
    document["scenarios"].append(extra)
    result = parse_suggestions(json.dumps(document), interface)
    assert result["ai_inferred"][-1]["review"]["duplicate_kind"] == "template"


def test_signature_preserves_json_types_order_and_placeholder_distinction():
    def signature(value, strategy="declared_value"):
        return input_signature({"inputs": [{"name": "data", "in": "query", "strategy": strategy, "value": value}]})
    assert signature({"a": 1, "b": 2}) == signature({"b": 2, "a": 1})
    assert signature([1, 2]) != signature([2, 1])
    assert signature(1) != signature(True)
    assert signature(None) != signature(None, "user_supplied")


def test_duplicate_detection_is_scoped_to_one_interface(interface, document):
    first = parse_suggestions(json.dumps(document), interface)
    interface["path"] = "/other-items"
    second = parse_suggestions(json.dumps(document), interface)
    assert all(item["review"]["duplicate_of"] is None for result in (first, second) for item in result["ai_inferred"])


def test_v02_submit_preview_record_is_flagged_without_keyword_repair():
    # Reproduce the V0.2 selections with fixed test data, independent of mutable
    # report files. The raw model response was not retained; no fresh call occurs.
    preview = {
        "name": "Normal request with preview mode", "category": "normal",
        "intent": "Verify preview mode",
        "inputs": [
            {"name": "item_id", "in": "path", "strategy": "user_supplied"},
            {"name": "rating", "in": "query", "strategy": "declared_value"},
            {"name": "mode", "in": "query", "strategy": "declared_value"},
            {"name": "Authorization", "in": "header", "strategy": "user_supplied"},
        ],
        "expected_result": {"status_code": None, "body": None, "notes": "Confirm actual behavior"},
    }
    submit, boundary, negative = (deepcopy(preview) for _ in range(3))
    submit.update(name="Normal request with submit mode", intent="Verify submit mode")
    boundary.update(name="Boundary rating", category="boundary")
    boundary["inputs"][1]["strategy"] = "maximum"
    negative.update(name="Negative rating", category="negative")
    negative["inputs"][1]["strategy"] = "above_maximum"
    document = {"scenarios": [preview, submit, boundary, negative]}
    interface = parse_openapi(PROJECT / "examples" / "ai_review_openapi.json")[0]

    result = parse_suggestions(json.dumps(document), interface)

    submit = next(item for item in result["ai_inferred"] if item["name"] == "Normal request with submit mode")
    assert next(item["value"] for item in submit["inputs"] if item["name"] == "mode") == "preview"
    assert submit["review"]["duplicate_of"] == "Normal request with preview mode"
    assert submit["review"]["duplicate_kind"] == "template"
    assert submit["review"]["input_consistency"] == "UNCONFIRMED"
    assert submit["review"]["business_confirmed"] is False


def test_mock_generation_runs_quality_checks_and_requests_no_network(interface, document):
    document["scenarios"][0]["inputs"][0]["intended_value"] = 10
    client = Mock()
    client.generate.return_value = json.dumps(document)
    result = generate_scenarios(interface, client=client)
    assert result["ai_inferred"][0]["review"]["input_consistency"] == "CHECKED"
    client.generate.assert_called_once()
    prompt = build_prompt(interface)
    assert "FIRST enum item" in prompt and "intended_value" in prompt


def test_claim_validation_error_never_echoes_supplied_data(interface, document):
    secret = "offline-confidential-marker"
    document["scenarios"][0]["inputs"][0]["intended_value"] = secret
    with pytest.raises(AIOutputError) as error:
        parse_suggestions(json.dumps(document), interface)
    assert secret not in str(error.value)

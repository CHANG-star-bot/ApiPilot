import json
import os
from copy import deepcopy
from pathlib import Path
from secrets import token_hex
from unittest.mock import Mock, patch

import pytest
import requests

from src.apipilot import suite_runner
from src.apipilot.ai_client import AIOutputError, AIServiceError
from src.apipilot.ai_scenario_generator import build_prompt, generate_scenarios, parse_suggestions
from src.apipilot.openapi_parser import parse_openapi
from src.apipilot.reporting import write_report


PROJECT = Path(__file__).resolve().parents[1]
OPENAPI = PROJECT / "examples" / "ai_scenarios_openapi.json"
MOCK_RESPONSE = PROJECT / "examples" / "ai_mock_response.json"


def generate_mock_example(output_path):
    """Exercise parsing, the HTTP model adapter and validation using a Mock only."""
    fake_key = "offline-only-" + token_hex(12)
    response = Mock(status_code=200)
    response.json.return_value = {"choices": [{
        "finish_reason": "stop", "message": {"content": MOCK_RESPONSE.read_text(encoding="utf-8")},
    }]}
    with (
        patch.dict(os.environ, {
            "APIPILOT_AI_URL": "https://model.example.test/v1/chat/completions",
            "APIPILOT_AI_MODEL": "offline-model", "APIPILOT_AI_API_KEY": fake_key,
        }),
        patch.object(requests, "post", return_value=response) as request,
        patch.object(requests.sessions.Session, "request", side_effect=RuntimeError("Network disabled")),
    ):
        suggestions = generate_scenarios(parse_openapi(OPENAPI)[0])
        write_report(suggestions, output_path)
        request.assert_called_once()
        assert fake_key not in json.dumps(suggestions)
        assert fake_key not in request.call_args.kwargs["json"]["messages"][1]["content"]
        return suggestions


@pytest.fixture(autouse=True)
def disable_network(monkeypatch):
    monkeypatch.delenv("APIPILOT_AI_API_KEY", raising=False)
    monkeypatch.setattr(requests.sessions.Session, "request", Mock(side_effect=RuntimeError("Network disabled")))


@pytest.fixture
def interface():
    return parse_openapi(OPENAPI)[0]


@pytest.fixture
def model_output():
    return json.loads(MOCK_RESPONSE.read_text(encoding="utf-8"))


def test_mock_model_suggestion_flow_never_executes_test_cases(tmp_path, monkeypatch):
    execute = Mock(side_effect=AssertionError("Suggestions must not be executed"))
    monkeypatch.setattr(suite_runner, "run_suite", execute)
    output_file = tmp_path / "suggestions.json"

    result = generate_mock_example(output_file)

    assert json.loads(output_file.read_text(encoding="utf-8")) == result
    assert result["kind"] == "ai_scenario_suggestions" and result["executable"] is False
    assert "executable_cases" not in result
    assert result["openapi_declared"]["parameters"][0]["schema"]["maximum"] == 100
    assert [item["inputs"][0]["value"] for item in result["ai_inferred"]] == [10, 100, 101]
    assert [item["inputs"][0]["source"] for item in result["ai_inferred"]] == [
        "openapi_declared", "openapi_declared", "ai_inferred",
    ]
    for scenario in result["ai_inferred"]:
        assert scenario["source"] == "ai_inferred"
        assert scenario["expected_result"]["status_code"] is None
        assert scenario["expected_result"]["body"] is None
        assert scenario["expected_result"]["confirmed"] is False
        assert scenario["expected_result"]["source"] == "user_required"
    execute.assert_not_called()


def test_generate_reuses_interface_metadata_and_explicit_client(interface, model_output):
    original = deepcopy(interface)
    client = Mock()
    client.generate.return_value = json.dumps(model_output)

    result = generate_scenarios(interface, client=client)

    assert interface == original
    assert result["openapi_declared"]["path"] == interface["path"]
    assert "OPENAPI_DECLARED" in client.generate.call_args.args[0]
    assert '"minimum": 1' in client.generate.call_args.args[0]
    assert result["user_required"]
    client.generate.assert_called_once()


@pytest.mark.parametrize("text", [
    "not JSON", '```json\n{"scenarios": []}\n```', "[]", "null", "{}",
    '{"scenarios": NaN}', '{"scenarios": [], "scenarios": []}',
    '{"scenarios": [], "executable_cases": []}',
])
def test_invalid_json_and_root_shape(interface, text):
    with pytest.raises(AIOutputError):
        parse_suggestions(text, interface)


@pytest.mark.parametrize("value", [None, {}, [], 1])
def test_model_must_return_text(interface, value):
    with pytest.raises(AIOutputError, match="JSON text"):
        parse_suggestions(value, interface)


@pytest.mark.parametrize("mutation", [
    lambda doc: doc.update(scenarios=[]),
    lambda doc: doc.update(scenarios=doc["scenarios"][:2]),
    lambda doc: doc["scenarios"][0].pop("intent"),
    lambda doc: doc["scenarios"][0].update(name=" "),
    lambda doc: doc["scenarios"][0].update(category="execute"),
    lambda doc: doc["scenarios"][1].update(category="normal"),
    lambda doc: doc["scenarios"][1].update(name=doc["scenarios"][0]["name"]),
    lambda doc: doc["scenarios"][0].update(expected_status=200),
    lambda doc: doc["scenarios"][0].update(inputs={}),
    lambda doc: doc["scenarios"][0]["inputs"][0].update(name="invented_user"),
    lambda doc: doc["scenarios"][0]["inputs"][0].update(value="invented-business-data"),
    lambda doc: doc["scenarios"][0]["inputs"][0].update(source="openapi_declared"),
    lambda doc: doc["scenarios"][0]["inputs"][0].update(strategy="invent_value"),
    lambda doc: doc["scenarios"][0]["inputs"].append(deepcopy(doc["scenarios"][0]["inputs"][0])),
    lambda doc: doc["scenarios"][0]["expected_result"].update(status_code=200),
    lambda doc: doc["scenarios"][0]["expected_result"].update(body={"success": True}),
    lambda doc: doc["scenarios"][0]["expected_result"].update(notes="Will return HTTP 400"),
    lambda doc: doc["scenarios"][0]["expected_result"].update(confirmed=True),
], ids=[
    "empty", "too-few", "missing-field", "empty-name", "unknown-category", "missing-category",
    "duplicate-name", "execution-field", "bad-inputs", "unknown-parameter", "invented-value",
    "invented-provenance", "unknown-strategy", "duplicate-input", "fixed-status", "fixed-body",
    "status-in-prose", "confirmed-result",
])
def test_invalid_model_structure_is_rejected_whole(interface, model_output, mutation):
    mutation(model_output)
    with pytest.raises(AIOutputError):
        parse_suggestions(json.dumps(model_output), interface)


@pytest.mark.parametrize("strategy, value, source", [
    ("declared_value", 10, "openapi_declared"), ("minimum", 1, "openapi_declared"),
    ("maximum", 100, "openapi_declared"), ("below_minimum", 0, "ai_inferred"),
    ("above_maximum", 101, "ai_inferred"), ("omit", None, "ai_inferred"),
    ("user_supplied", None, "user_required"),
])
def test_input_values_are_derived_from_declared_constraints(interface, model_output, strategy, value, source):
    if strategy in ("below_minimum", "above_maximum", "omit"):
        normal = deepcopy(model_output["scenarios"][0])
        normal["name"] = "Retained normal scenario"
        model_output["scenarios"].append(normal)
        model_output["scenarios"][0]["category"] = "negative"
    model_output["scenarios"][0]["inputs"][0]["strategy"] = strategy
    result = parse_suggestions(json.dumps(model_output), interface)
    scenario = result["ai_inferred"][0]
    assert scenario["inputs"][0]["value"] == value
    assert scenario["inputs"][0]["source"] == source
    if strategy == "user_supplied":
        assert scenario["user_required"] == ["Provide query parameter: limit"]


@pytest.mark.parametrize("schema, expected", [
    ({"type": "integer", "enum": [3, 4]}, 3),
    ({"type": "integer", "default": 5}, 5),
])
def test_explicit_enum_and_default_values_are_preserved(interface, model_output, schema, expected):
    # Other scenarios use user input because these schemas declare no numeric bounds.
    interface["parameters"][0]["schema"] = schema
    for scenario in model_output["scenarios"][1:]:
        scenario["inputs"][0]["strategy"] = "user_supplied"
    result = parse_suggestions(json.dumps(model_output), interface)
    assert result["ai_inferred"][0]["inputs"][0]["value"] == expected


@pytest.mark.parametrize("strategy, schema", [
    ("declared_value", {"type": "integer"}),
    ("maximum", {"type": "integer"}),
    ("minimum", {"type": "string", "minimum": 1}),
    ("minimum", {"type": "integer", "minimum": True}),
    ("minimum", {"type": "integer", "minimum": 1.5}),
    ("declared_value", {"$ref": "#/components/schemas/ItemId"}),
    ("declared_value", {"oneOf": [{"type": "integer"}]}),
    ("above_maximum", {"type": "number", "maximum": 1e308}),
])
def test_missing_or_unsupported_constraints_cannot_invent_data(interface, model_output, strategy, schema):
    interface["parameters"][0]["schema"] = schema
    model_output["scenarios"][0]["inputs"][0]["strategy"] = strategy
    with pytest.raises(AIOutputError):
        parse_suggestions(json.dumps(model_output), interface)


def test_credentials_are_omitted_from_prompt_and_require_user_data(interface, model_output):
    secret = "documented-only-" + token_hex(8)
    parameter = {"name": "Authorization", "in": "header", "example": "Bearer " + secret,
                 "schema": {"type": "string", "default": secret}}
    interface["parameters"].append(parameter)
    model_output["scenarios"][0]["inputs"].append({
        "name": "Authorization", "in": "header", "strategy": "user_supplied",
    })

    result = parse_suggestions(json.dumps(model_output), interface)

    assert secret not in build_prompt(interface)
    assert secret not in json.dumps(result)
    assert result["ai_inferred"][0]["inputs"][-1]["value"] is None
    assert "Provide header parameter: Authorization" in result["ai_inferred"][0]["user_required"]
    model_output["scenarios"][0]["inputs"][-1]["strategy"] = "declared_value"
    with pytest.raises(AIOutputError, match="Credentials"):
        parse_suggestions(json.dumps(model_output), interface)


def test_body_and_reference_limitations_remain_explicit(interface, model_output):
    interface["method"] = "POST"
    interface["has_request_body"] = True
    interface["parameters"].append({"$ref": "#/components/parameters/BusinessId"})
    result = parse_suggestions(json.dumps(model_output), interface)
    assert any("Body schema" in message for message in result["user_required"])
    assert any("references" in message for message in result["user_required"])


@pytest.mark.parametrize("escaped", [False, True])
def test_model_echoing_environment_key_is_rejected(interface, model_output, monkeypatch, escaped):
    key = "offline-only-" + token_hex(12)
    monkeypatch.setenv("APIPILOT_AI_API_KEY", key)
    model_output["scenarios"][0]["intent"] = key
    text = json.dumps(model_output)
    if escaped:
        text = text.replace(key, "".join("\\u%04x" % ord(character) for character in key))
    with pytest.raises(AIOutputError, match="credential material"):
        parse_suggestions(text, interface)


def test_invalid_interface_fails_before_model_call(interface):
    interface["method"] = "DELETE"
    client = Mock()
    with pytest.raises(ValueError, match="GET/POST"):
        generate_scenarios(interface, client=client)
    client.generate.assert_not_called()


def test_unconfigured_service_is_explicit(interface):
    with pytest.raises(AIServiceError, match="Set APIPILOT_AI_URL"):
        generate_scenarios(interface)

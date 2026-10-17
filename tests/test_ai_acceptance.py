"""Offline checks of the acceptance script, not evidence of model quality."""

import json
from copy import deepcopy
from secrets import token_hex
from unittest.mock import Mock

import pytest
import requests

from examples import run_ai_acceptance as acceptance
from src.apipilot.ai_client import AIClient, AIOutputError
from src.apipilot.ai_scenario_generator import parse_suggestions, validate_scenario
from src.apipilot.openapi_parser import parse_openapi


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for name in ("APIPILOT_AI_URL", "APIPILOT_AI_MODEL", "APIPILOT_AI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(requests.sessions.Session, "request", Mock(side_effect=AssertionError("Network disabled")))


def configure(monkeypatch):
    key = "offline-only-" + token_hex(12)
    monkeypatch.setenv("APIPILOT_AI_URL", "https://model.example.test/v1/chat/completions")
    monkeypatch.setenv("APIPILOT_AI_MODEL", "offline-router")
    monkeypatch.setenv("APIPILOT_AI_API_KEY", key)
    return key


def model_text():
    # Manually authored Mock text; never treat this as an actual model result.
    document = json.loads((acceptance.PROJECT / "examples" / "ai_mock_response.json").read_text(encoding="utf-8"))
    return json.dumps(document)


def response(text, model="offline-actual-model"):
    result = Mock(status_code=200)
    result.json.return_value = {"model": model, "choices": [{
        "finish_reason": "stop", "message": {"content": text},
    }]}
    return result


def test_both_fixtures_are_supported_and_rules_need_no_model():
    methods = []
    for fixture in acceptance.FIXTURES:
        interfaces = parse_openapi(fixture)
        assert len(interfaces) == 1
        interface = interfaces[0]
        methods.append(interface["method"])
        rules = acceptance.rule_baseline(interface)
        assert {item["category"] for item in rules} == {"normal", "boundary", "negative"}
        assert all(item["source"] == "rule_generated" for item in rules)
        assert all(item["expected_result"]["status_code"] is None for item in rules)
    assert methods == ["GET", "POST"]


def test_rules_do_not_invent_path_ids_credentials_or_body():
    interface = parse_openapi(acceptance.FIXTURES[1])[0]
    for scenario in acceptance.rule_baseline(interface):
        for item in scenario["inputs"]:
            if item["name"] in ("item_id", "Authorization"):
                assert item["strategy"] in ("omit", "user_supplied")
                assert item["value"] is None
        assert "body" not in scenario


def test_unconfigured_entry_writes_honest_report_without_call(tmp_path, monkeypatch, capsys):
    request = Mock(side_effect=AssertionError("Must not call model"))
    monkeypatch.setattr(requests, "post", request)
    output = tmp_path / "report.json"
    assert acceptance.main(["--report", str(output)]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "NOT_CONFIGURED"
    assert report["calls"] == report["responses"] == 0
    assert report["requested_model"] is None
    for item in report["results"]:
        assert item["suggestions"] is None
        assert all(value is None for value in item["metrics"].values())
    pending = report["results"][1]["pending_information"]
    assert any("item_id" in item for item in pending)
    assert any("Authorization" in item for item in pending)
    assert any("Body schema" in item for item in pending)
    assert "CALLS=0" in capsys.readouterr().out
    request.assert_not_called()


def test_mock_full_flow_caps_calls_records_actual_models_and_never_executes(tmp_path, monkeypatch):
    key = configure(monkeypatch)
    get_text = model_text()
    post_text = get_text.replace('"limit"', '"rating"')
    request = Mock(side_effect=[response(get_text, "offline-a"), response(post_text, "offline-b")])
    monkeypatch.setattr(requests, "post", request)
    from src.apipilot import suite_runner
    execute = Mock(side_effect=AssertionError("Suggestions must not execute"))
    monkeypatch.setattr(suite_runner, "run_suite", execute)
    output = tmp_path / "report.json"

    assert acceptance.main(["--report", str(output), "--timeout", "8"]) == 0

    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "VALIDATED"
    assert report["executable"] is False
    assert report["requested_model"] == "offline-router"
    assert report["calls"] == report["responses"] == request.call_count == 2
    assert [item["actual_model"] for item in report["results"]] == ["offline-a", "offline-b"]
    assert all(item["metrics"]["accepted_suggestions"] == 3 for item in report["results"])
    assert all(item["suggestions"]["executable"] is False for item in report["results"])
    assert all(call.kwargs["timeout"] == 8 for call in request.call_args_list)
    assert key not in output.read_text(encoding="utf-8")
    assert all(key not in call.kwargs["json"]["messages"][1]["content"] for call in request.call_args_list)
    execute.assert_not_called()


def test_service_failure_stops_without_retry_and_keeps_unknown_metrics(tmp_path, monkeypatch, capsys):
    key = configure(monkeypatch)
    request = Mock(side_effect=requests.Timeout(key))
    monkeypatch.setattr(requests, "post", request)
    output = tmp_path / "report.json"
    assert acceptance.main(["--report", str(output)]) == 2
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["calls"] == 1 and report["responses"] == 0
    assert [item["status"] for item in report["results"]] == ["SERVICE_ERROR", "NOT_CALLED"]
    assert key not in output.read_text(encoding="utf-8") + capsys.readouterr().out
    assert report["results"][0]["metrics"]["raw_suggestions"] is None
    request.assert_called_once()


def test_invalid_item_count_does_not_partially_accept_batch():
    interface = parse_openapi(acceptance.FIXTURES[0])[0]
    document = json.loads(model_text())
    document["scenarios"][0]["expected_result"]["status_code"] = 200
    metrics, suggestions, error = acceptance.review_output(json.dumps(document), interface, acceptance.rule_baseline(interface))
    assert metrics["raw_json_type"] == "object"
    assert metrics["raw_categories"] == {"normal": 1, "boundary": 1, "negative": 1, "unknown": 0}
    assert metrics["invalid_items"] == 1
    assert metrics["accepted_suggestions"] == 0 and metrics["rejected_suggestions"] == 3
    assert suggestions is None and error


def test_duplicate_inputs_and_names_are_reported_separately():
    interface = parse_openapi(acceptance.FIXTURES[0])[0]
    document = json.loads(model_text())
    extra = deepcopy(document["scenarios"][0])
    extra["name"] = "A different name but the same input"
    document["scenarios"].append(extra)
    metrics, suggestions, error = acceptance.review_output(json.dumps(document), interface, acceptance.rule_baseline(interface))
    assert metrics["duplicate_inputs"] == 1 and metrics["duplicate_names"] == 0
    assert metrics["accepted_suggestions"] == 4 and error is None
    document["scenarios"][-1]["name"] = document["scenarios"][0]["name"]
    metrics, suggestions, error = acceptance.review_output(json.dumps(document), interface, [])
    assert metrics["duplicate_names"] == 1 and metrics["invalid_items"] == 0
    assert metrics["accepted_suggestions"] == 0 and suggestions is None


def test_report_duplicate_count_matches_generator_materialized_inputs():
    interface = parse_openapi(acceptance.FIXTURES[0])[0]
    interface["parameters"][0]["schema"]["minimum"] = 10
    document = json.loads(model_text())
    extra = deepcopy(document["scenarios"][0])
    extra.update(name="Same value through another strategy", category="negative")
    extra["inputs"][0]["strategy"] = "minimum"
    document["scenarios"].append(extra)

    metrics, suggestions, error = acceptance.review_output(json.dumps(document), interface, [])

    assert error is None
    duplicates = [item for item in suggestions["ai_inferred"] if item["review"]["duplicate_of"]]
    assert metrics["duplicate_inputs"] == len(duplicates) == 1
    assert duplicates[0]["review"]["duplicate_kind"] == "concrete"


@pytest.mark.parametrize("text, kind", [("not JSON", "invalid_json"), ("[]", "array"), ("null", "null"), ("{}", "object")])
def test_unreadable_or_wrong_shape_output_does_not_fabricate_counts(text, kind):
    interface = parse_openapi(acceptance.FIXTURES[0])[0]
    metrics, suggestions, error = acceptance.review_output(text, interface, [])
    assert metrics["raw_json_type"] == kind
    assert metrics["raw_suggestions"] is None
    assert suggestions is None and error


def test_rule_comparison_reports_novelty_only():
    interface = parse_openapi(acceptance.FIXTURES[1])[0]
    document = json.loads(model_text().replace('"limit"', '"rating"'))
    document["scenarios"][0]["inputs"].append({"name": "mode", "in": "query", "strategy": "declared_value"})
    metrics, suggestions, error = acceptance.review_output(json.dumps(document), interface, acceptance.rule_baseline(interface))
    assert metrics["novel_inputs_vs_rules"] == 1
    assert suggestions and not error


def test_single_validation_never_bypasses_batch_gate():
    interface = parse_openapi(acceptance.FIXTURES[0])[0]
    candidate = json.loads(model_text())["scenarios"][0]
    assert validate_scenario(candidate, interface)["expected_result"]["confirmed"] is False
    with pytest.raises(AIOutputError, match="3-30"):
        parse_suggestions(json.dumps({"scenarios": [candidate]}), interface)


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf"])
def test_invalid_timeout_does_not_call_model(tmp_path, monkeypatch, timeout):
    configure(monkeypatch)
    request = Mock(side_effect=AssertionError("No call"))
    monkeypatch.setattr(requests, "post", request)
    assert acceptance.main(["--report", str(tmp_path / "result.json"), "--timeout", timeout]) == 2
    request.assert_not_called()


def test_report_cannot_overwrite_fixture(monkeypatch):
    configure(monkeypatch)
    request = Mock(side_effect=AssertionError("No call"))
    monkeypatch.setattr(requests, "post", request)
    before = acceptance.FIXTURES[0].read_bytes()
    assert acceptance.main(["--report", str(acceptance.FIXTURES[0])]) == 2
    assert acceptance.FIXTURES[0].read_bytes() == before
    request.assert_not_called()


def test_bad_fixture_preflight_prevents_all_calls(tmp_path, monkeypatch):
    configure(monkeypatch)
    monkeypatch.setattr(acceptance, "FIXTURES", (acceptance.FIXTURES[0], tmp_path / "missing.json"))
    request = Mock(side_effect=AssertionError("No call"))
    monkeypatch.setattr(requests, "post", request)
    assert acceptance.main(["--report", str(tmp_path / "result.json")]) == 2
    request.assert_not_called()


def test_actual_model_is_optional_and_cleared_on_next_failure(monkeypatch):
    configure(monkeypatch)
    request = Mock(side_effect=[response(model_text()), requests.ConnectionError("offline")])
    monkeypatch.setattr(requests, "post", request)
    client = AIClient()
    client.generate("prompt")
    assert client.last_model == "offline-actual-model"
    from src.apipilot.ai_client import AIServiceError
    with pytest.raises(AIServiceError):
        client.generate("prompt")
    assert client.last_model is None


def test_actual_model_cannot_echo_api_key(tmp_path, monkeypatch):
    key = configure(monkeypatch)
    request = Mock(side_effect=[response(model_text(), key), response(model_text().replace('"limit"', '"rating"'), key)])
    monkeypatch.setattr(requests, "post", request)
    output = tmp_path / "report.json"
    report = acceptance.run_acceptance(output)
    assert all(item["actual_model"] is None for item in report["results"])
    assert key not in output.read_text(encoding="utf-8")

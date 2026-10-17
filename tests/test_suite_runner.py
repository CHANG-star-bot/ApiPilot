import json
from copy import deepcopy
from unittest.mock import Mock, call

import pytest
import requests

from src.apipilot import http_client, suite_runner
from src.apipilot.case_generator import generate_cases
from src.apipilot.suite_runner import run_suite


@pytest.fixture(autouse=True)
def disable_network(monkeypatch):
    monkeypatch.setattr(
        http_client.requests.sessions.Session,
        "request",
        Mock(side_effect=RuntimeError("Real HTTP requests are disabled in these tests")),
    )


@pytest.fixture
def inputs(tmp_path):
    document = {
        "openapi": "3.1.0",
        "info": {"title": "Offline suite example", "version": "1.0.0"},
        "paths": {
            "/health": {
                "get": {"summary": "Mock PASS", "responses": {"200": {"description": "OK"}}},
            },
            "/items": {
                "post": {
                    "summary": "Mock FAIL",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/unstable": {
                "get": {"summary": "Mock ERROR", "responses": {"200": {"description": "OK"}}},
            },
            "/after-error": {
                "get": {"summary": "Mock PASS after ERROR", "responses": {"200": {"description": "OK"}}},
            },
            "/items/{item_id}": {
                "parameters": [{
                    "name": "item_id", "in": "path", "required": True,
                    "schema": {"type": "string"},
                }],
                "get": {"summary": "Needs item_id", "responses": {"200": {"description": "OK"}}},
            },
        },
    }
    config = {
        "base_url": "https://example.test/api",
        "cases": [
            {"method": "GET", "path": "/health", "expected_status": 200, "expected_body": {"ok": True}},
            {
                "method": "POST", "path": "/items", "body": {"value": "offline-example"},
                "params": {"source": "offline"}, "headers": {"Accept": "application/json"},
                "expected_status": 201, "expected_body": {"created": True},
            },
            {"method": "GET", "path": "/unstable", "expected_status": 200},
            {"method": "GET", "path": "/after-error", "expected_status": 200, "expected_body": {"ok": True}},
            {"method": "GET", "path": "/items/{item_id}", "expected_status": 200},
        ],
    }
    openapi_file, config_file = tmp_path / "openapi.json", tmp_path / "config.json"
    openapi_file.write_text(json.dumps(document), encoding="utf-8")
    config_file.write_text(json.dumps(config), encoding="utf-8")
    return openapi_file, config_file


def response(status=200, body=None):
    result = Mock(status_code=status)
    result.json.return_value = body
    return result


def case(name="Offline case", expected_body=None):
    result = {
        "name": name, "method": "GET", "url": "https://example.test/items", "expected_status": 200,
    }
    if expected_body is not None:
        result["expected_body"] = expected_body
    return result


def test_openapi_to_suite_report_end_to_end(inputs, monkeypatch):
    get_request = Mock(side_effect=[
        response(body={"ok": True}),
        requests.Timeout("simulated timeout"),
        response(body={"ok": True}),
    ])
    post_request = Mock(return_value=response(201, {"created": False}))
    monkeypatch.setattr(http_client.requests, "get", get_request)
    monkeypatch.setattr(http_client.requests, "post", post_request)

    generated = generate_cases(*inputs)
    original = deepcopy(generated)
    report = run_suite(**generated)

    assert report["summary"] == {"total": 4, "PASS": 2, "FAIL": 1, "ERROR": 1, "pending": 1}
    assert report["results"] == [
        {"name": "Mock PASS", "status": "PASS", "error": None},
        {"name": "Mock FAIL", "status": "FAIL", "error": "Expected True, got False"},
        {"name": "Mock ERROR", "status": "ERROR", "error": "Timeout: simulated timeout"},
        {"name": "Mock PASS after ERROR", "status": "PASS", "error": None},
    ]
    assert report["pending_cases"] == generated["pending_cases"] == [{
        "name": "Needs item_id", "method": "GET", "path": "/items/{item_id}",
        "reasons": ["Missing path parameter: item_id"],
    }]
    assert get_request.call_args_list == [
        call("https://example.test/api/health", params=None, headers=None, timeout=10.0),
        call("https://example.test/api/unstable", params=None, headers=None, timeout=10.0),
        call("https://example.test/api/after-error", params=None, headers=None, timeout=10.0),
    ]
    post_request.assert_called_once_with(
        "https://example.test/api/items", params={"source": "offline"},
        json={"value": "offline-example"}, headers={"Accept": "application/json"}, timeout=10.0,
    )
    assert generated == original
    # Print an actual report from mocked responses, explicitly labelled as such.
    print(json.dumps({"source": "offline-mock", **report}, indent=2))


def test_all_pending_interfaces_are_preserved_without_execution(inputs, monkeypatch):
    openapi_file, config_file = inputs
    config_file.write_text(json.dumps({"base_url": "https://example.test"}), encoding="utf-8")
    execute = Mock(side_effect=RuntimeError("Pending cases must not execute"))
    monkeypatch.setattr(suite_runner, "run_case", execute)
    generated = generate_cases(openapi_file, config_file)

    report = run_suite(**generated)

    assert report["summary"] == {"total": 0, "PASS": 0, "FAIL": 0, "ERROR": 0, "pending": 5}
    assert report["results"] == []
    assert report["pending_cases"] == generated["pending_cases"]
    execute.assert_not_called()


def test_empty_suite():
    assert run_suite([]) == {
        "summary": {"total": 0, "PASS": 0, "FAIL": 0, "ERROR": 0, "pending": 0},
        "results": [],
        "pending_cases": [],
    }


@pytest.mark.parametrize("error", [
    requests.Timeout("offline timeout"),
    requests.ConnectionError("offline connection failure"),
    AssertionError("execution-stage assertion"),
])
def test_request_exception_is_error_and_next_case_runs(monkeypatch, error):
    get_request = Mock(side_effect=[error, response()])
    monkeypatch.setattr(http_client.requests, "get", get_request)

    report = run_suite([case("Broken request"), case("Next request")])

    assert [item["status"] for item in report["results"]] == ["ERROR", "PASS"]
    assert report["results"][0]["error"] == f"{type(error).__name__}: {error}"
    assert get_request.call_count == 2


def test_invalid_response_json_is_error_and_next_case_runs(monkeypatch):
    invalid_response = response()
    invalid_response.json.side_effect = ValueError("response is not JSON")
    monkeypatch.setattr(http_client.requests, "get", Mock(side_effect=[invalid_response, response()]))

    report = run_suite([case("Bad JSON", {"ok": True}), case("Next request")])

    assert [item["status"] for item in report["results"]] == ["ERROR", "PASS"]
    assert report["results"][0]["error"] == "ValueError: response is not JSON"


def test_status_mismatch_is_fail_without_decoding_body(monkeypatch):
    actual_response = response(503)
    monkeypatch.setattr(http_client.requests, "get", Mock(return_value=actual_response))

    report = run_suite([case(expected_body={"ok": True})])

    assert report["results"][0]["status"] == "FAIL"
    assert report["results"][0]["error"] == "Expected status 200, got 503"
    actual_response.json.assert_not_called()


@pytest.mark.parametrize("actual, expected, message", [
    (None, {"id": 1}, "Expected object, got NoneType"),
    ({}, [], "Expected array, got dict"),
    ({}, {"id": 1}, "Missing key: 'id'"),
    ([], [1], "Expected at least 1 items, got 0"),
    ([{"id": 2}], [{"id": 1}], "Expected 1, got 2"),
])
def test_body_mismatch_is_fail_with_reason(monkeypatch, actual, expected, message):
    monkeypatch.setattr(http_client.requests, "get", Mock(return_value=response(body=actual)))

    report = run_suite([case(expected_body=expected)])

    assert report["results"][0]["status"] == "FAIL"
    assert report["results"][0]["error"] == message


def test_assertion_without_message_still_has_reason(monkeypatch):
    monkeypatch.setattr(suite_runner, "run_case", Mock(return_value=response()))
    monkeypatch.setattr(suite_runner, "assert_response", Mock(side_effect=AssertionError()))

    report = run_suite([case()])

    assert report["results"][0] == {
        "name": "Offline case", "status": "FAIL", "error": "Response assertion failed",
    }


def test_malformed_cases_do_not_stop_the_suite(monkeypatch):
    get_request = Mock(return_value=response())
    monkeypatch.setattr(http_client.requests, "get", get_request)

    report = run_suite([{"name": "Missing request fields"}, None, case("After malformed cases")])

    assert [item["status"] for item in report["results"]] == ["ERROR", "ERROR", "PASS"]
    assert report["results"][1]["name"] == "Case 2"
    get_request.assert_called_once()


def test_pending_report_does_not_modify_original_reasons():
    pending = [{"name": "Pending", "reasons": ["Missing expected_status"]}]

    report = run_suite([], pending)
    report["pending_cases"][0]["reasons"].append("Report-only note")

    assert pending == [{"name": "Pending", "reasons": ["Missing expected_status"]}]


def test_keyboard_interrupt_can_stop_execution(monkeypatch):
    monkeypatch.setattr(http_client.requests, "get", Mock(side_effect=KeyboardInterrupt()))

    with pytest.raises(KeyboardInterrupt):
        run_suite([case()])

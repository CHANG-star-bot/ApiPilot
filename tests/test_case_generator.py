import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.apipilot import http_client
from src.apipilot.assertions import assert_response
from src.apipilot.case_generator import generate_cases
from src.apipilot.case_loader import load_cases
from src.apipilot.case_runner import run_case


@pytest.fixture(autouse=True)
def disable_network(monkeypatch):
    monkeypatch.setattr(
        http_client.requests.sessions.Session,
        "request",
        Mock(side_effect=RuntimeError("Real HTTP requests are disabled in these tests")),
    )


@pytest.fixture
def document():
    return {
        "openapi": "3.0.3",
        "info": {"title": "Offline test API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "get": {
                    "summary": "List items",
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "summary": "Create item",
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": {"type": "object"}}},
                    },
                    "responses": {"201": {"description": "Created"}},
                },
            },
            "/items/{item_id}": {
                "parameters": [{
                    "name": "item_id", "in": "path", "required": True,
                    "schema": {"type": "string"},
                }],
                "get": {"responses": {"200": {"description": "OK"}}},
            },
        },
    }


@pytest.fixture
def config():
    return {
        "base_url": "https://example.test/api/v1",
        "cases": [
            {
                "method": "get",
                "path": "/items",
                "params": {"limit": 2, "tag": ["a", "b"]},
                "headers": {"Accept": "application/json"},
                "expected_status": 200,
                "expected_body": [{"id": "offline-item"}],
            },
            {
                "name": "Explicit POST name",
                "method": "POST",
                "path": "/items",
                "params": {"source": "offline"},
                "headers": {"Content-Type": "application/json"},
                "body": {"value": "offline-example"},
                "expected_status": 201,
                "expected_body": {"created": True},
            },
            {"method": "GET", "path": "/items/{item_id}", "expected_status": 200},
        ],
    }


def generate(tmp_path, document, config):
    openapi_file = tmp_path / "openapi.json"
    config_file = tmp_path / "config.json"
    openapi_file.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    config_file.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    return generate_cases(openapi_file, config_file)


def test_sample_generation():
    examples = Path(__file__).resolve().parents[1] / "examples"

    result = generate_cases(
        examples / "case_generation_openapi.json", examples / "case_generation_config.json"
    )

    assert result == {
        "executable_cases": [
            {
                "name": "List users (offline example)",
                "method": "GET",
                "url": "https://example.test/api/v1/users",
                "expected_status": 200,
                "params": {"limit": 2},
                "headers": {"Accept": "application/json"},
                "expected_body": [{"name": "offline-example"}],
            },
            {
                "name": "Create user (offline example)",
                "method": "POST",
                "url": "https://example.test/api/v1/users",
                "expected_status": 201,
                "params": {"source": "offline"},
                "headers": {"Content-Type": "application/json"},
                "body": {"name": "offline-example"},
                "expected_body": {"name": "offline-example"},
            },
        ],
        "pending_cases": [{
            "name": "Get user (needs user_id)",
            "method": "GET",
            "path": "/users/{user_id}",
            "reasons": ["Missing path parameter: user_id"],
        }],
    }


@pytest.mark.parametrize(
    "base_url, expected_url",
    [
        ("https://example.test", "https://example.test/items"),
        ("https://example.test/", "https://example.test/items"),
        ("https://example.test/api/v1", "https://example.test/api/v1/items"),
        ("https://example.test/api/v1/", "https://example.test/api/v1/items"),
        ("http://example.test/api/", "http://example.test/api/items"),
    ],
)
def test_joins_url_and_preserves_base_path(tmp_path, document, config, base_url, expected_url):
    config["base_url"] = base_url

    assert generate(tmp_path, document, config)["executable_cases"][0]["url"] == expected_url


@pytest.mark.parametrize(
    "value, encoded",
    [("a/b?c#d", "a%2Fb%3Fc%23d"), ("中 文", "%E4%B8%AD%20%E6%96%87"), (0, "0"), (False, "false")],
)
def test_substitutes_and_encodes_path_parameters(tmp_path, document, config, value, encoded):
    config["cases"][2]["path_params"] = {"item_id": value}

    result = generate(tmp_path, document, config)

    assert result["pending_cases"] == []
    assert result["executable_cases"][2]["url"] == "https://example.test/api/v1/items/" + encoded
    assert "path_params" not in result["executable_cases"][2]


def test_does_not_infer_status_from_openapi_responses(tmp_path, document, config):
    del config["cases"][0]["expected_status"]

    result = generate(tmp_path, document, config)

    assert [case["method"] for case in result["executable_cases"]] == ["POST"]
    pending = result["pending_cases"][0]
    assert pending["path"] == "/items"
    assert "Missing expected_status" in pending["reasons"]
    assert "url" not in pending and "expected_status" not in pending


@pytest.mark.parametrize("status", [None, "200", True, 600])
def test_invalid_status_is_pending(tmp_path, document, config, status):
    config["cases"][0]["expected_status"] = status

    result = generate(tmp_path, document, config)

    assert result["pending_cases"][0]["method"] == "GET"
    assert any("expected_status" in reason for reason in result["pending_cases"][0]["reasons"])


@pytest.mark.parametrize("value", [None, "", []])
def test_missing_or_invalid_path_value_is_pending(tmp_path, document, config, value):
    config["cases"][2]["path_params"] = {"item_id": value}
    # A query parameter with the same name must not fill a path placeholder.
    config["cases"][2]["params"] = {"item_id": "query-only-value"}

    result = generate(tmp_path, document, config)

    assert len(result["executable_cases"]) == 2
    assert "item_id" in result["pending_cases"][0]["reasons"][0]


@pytest.mark.parametrize("include_null", [False, True])
def test_missing_body_is_pending(tmp_path, document, config, include_null):
    del config["cases"][1]["body"]
    if include_null:
        config["cases"][1]["body"] = None

    result = generate(tmp_path, document, config)

    assert [case["method"] for case in result["executable_cases"]] == ["GET"]
    assert "Missing body" in result["pending_cases"][0]["reasons"][0]


@pytest.mark.parametrize("body", [{}, [], False, 0])
def test_explicit_empty_or_false_body_is_preserved(tmp_path, document, config, body):
    config["cases"][1]["body"] = body

    post_case = generate(tmp_path, document, config)["executable_cases"][1]

    assert post_case["body"] == body
    assert type(post_case["body"]) is type(body)


def test_empty_configuration_never_generates_executable_cases(tmp_path, document, config):
    del config["cases"]

    result = generate(tmp_path, document, config)

    assert result["executable_cases"] == []
    assert len(result["pending_cases"]) == 3
    assert all("Missing test configuration" in item["reasons"] for item in result["pending_cases"])
    assert "Missing body for declared requestBody" in result["pending_cases"][1]["reasons"]
    assert "Missing path parameter: item_id" in result["pending_cases"][2]["reasons"]


def test_status_only_case_keeps_optional_fields_absent(tmp_path, document, config):
    config["cases"][0] = {"method": "GET", "path": "/items", "expected_status": 204}

    assert generate(tmp_path, document, config)["executable_cases"][0] == {
        "name": "List items",
        "method": "GET",
        "url": "https://example.test/api/v1/items",
        "expected_status": 204,
    }


@pytest.mark.parametrize("location", ["query", "header"])
def test_required_query_or_header_needs_explicit_data(tmp_path, document, config, location):
    document["paths"]["/items"]["get"]["parameters"] = [{
        "name": "X-Example", "in": location, "required": True, "schema": {"type": "string"},
    }]

    result = generate(tmp_path, document, config)
    assert f"Missing required {location} parameter: X-Example" in result["pending_cases"][0]["reasons"]

    field = "params" if location == "query" else "headers"
    name = "X-Example" if location == "query" else "x-example"
    config["cases"][0][field][name] = "explicit-offline-value"
    assert len(generate(tmp_path, document, config)["executable_cases"]) == 2


def test_unresolved_reference_is_pending(tmp_path, document, config):
    document["paths"]["/items"]["get"]["parameters"] = [{"$ref": "./missing.json#/parameter"}]

    result = generate(tmp_path, document, config)

    assert "Unresolved parameter reference" in result["pending_cases"][0]["reasons"][0]


def test_get_body_is_pending_because_executor_would_ignore_it(tmp_path, document, config):
    config["cases"][0]["body"] = {"explicit": "offline"}

    result = generate(tmp_path, document, config)

    assert "GET body is not supported" in result["pending_cases"][0]["reasons"][0]


def test_generated_cases_work_with_existing_execution_chain(tmp_path, document, config, monkeypatch):
    get_response = Mock(status_code=200)
    get_response.json.return_value = [{"id": "offline-item", "extra": "allowed"}]
    post_response = Mock(status_code=201)
    post_response.json.return_value = {"created": True, "id": "offline-created"}
    get_request = Mock(return_value=get_response)
    post_request = Mock(return_value=post_response)
    monkeypatch.setattr(http_client.requests, "get", get_request)
    monkeypatch.setattr(http_client.requests, "post", post_request)

    result = generate(tmp_path, document, config)
    get_request.assert_not_called()
    post_request.assert_not_called()

    # Export only ready cases: load_cases and run_case need no changes.
    ready_file = tmp_path / "ready_cases.json"
    ready_file.write_text(json.dumps(result["executable_cases"]), encoding="utf-8")
    for case in load_cases(ready_file):
        assert_response(run_case(case), case)

    get_request.assert_called_once_with(
        "https://example.test/api/v1/items",
        params={"limit": 2, "tag": ["a", "b"]},
        headers={"Accept": "application/json"},
        timeout=10.0,
    )
    post_request.assert_called_once_with(
        "https://example.test/api/v1/items",
        params={"source": "offline"},
        json={"value": "offline-example"},
        headers={"Content-Type": "application/json"},
        timeout=10.0,
    )
    assert result["executable_cases"][1]["name"] == "Explicit POST name"
    assert len(result["pending_cases"]) == 1


@pytest.mark.parametrize("base_url", [None, "/relative", "https://example.test/api?q=1", "https://example.test/#fragment"])
def test_rejects_invalid_base_url(tmp_path, document, config, base_url):
    config["base_url"] = base_url

    with pytest.raises(ValueError, match="base_url"):
        generate(tmp_path, document, config)


def test_duplicate_method_and_path_are_rejected(tmp_path, document, config):
    config["cases"].append({"method": "GET", "path": "/items", "expected_status": 200})

    with pytest.raises(ValueError, match="Duplicate case configuration"):
        generate(tmp_path, document, config)


def test_unknown_configured_interface_is_rejected(tmp_path, document, config):
    config["cases"][0]["path"] = "/typo"

    with pytest.raises(ValueError, match="interface not found"):
        generate(tmp_path, document, config)


def test_invalid_configuration_json(tmp_path):
    openapi_file = Path(__file__).resolve().parents[1] / "examples" / "sample_openapi.json"
    config_file = tmp_path / "broken.json"
    config_file.write_text('{"base_url":', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid test configuration JSON"):
        generate_cases(openapi_file, config_file)


def test_configuration_must_be_an_object(tmp_path, document):
    with pytest.raises(ValueError, match="configuration must be an object"):
        generate(tmp_path, document, [])

import json
from unittest.mock import Mock

import pytest

from src.apipilot import http_client
from src.apipilot.assertions import assert_response
from src.apipilot.case_loader import load_cases
from src.apipilot.case_runner import run_case


@pytest.fixture
def mock_http(monkeypatch):
    get_request = Mock(name="requests.get")
    post_request = Mock(name="requests.post")
    monkeypatch.setattr(http_client.requests, "get", get_request)
    monkeypatch.setattr(http_client.requests, "post", post_request)

    # Reject any request that accidentally bypasses the mocks.
    monkeypatch.setattr(
        http_client.requests.sessions.Session,
        "request",
        Mock(side_effect=RuntimeError("Real HTTP requests are disabled in these tests")),
    )
    return get_request, post_request


@pytest.mark.parametrize("method", ["GET", "get", "POST", "post"])
def test_load_run_and_assert_request(tmp_path, mock_http, method):
    get_request, post_request = mock_http
    is_post = method.upper() == "POST"
    case = {
        "name": f"offline {method} case",
        "method": method,
        "url": "https://example.test/posts" if is_post else "https://example.test/users/1",
        "params": {"source": "apipilot"},
        "headers": {"Accept": "application/json", "X-Test": "offline"},
        "body": {"title": "ApiPilot", "body": "Offline POST", "userId": 1}
        if is_post
        else None,
        "expected_status": 201 if is_post else 200,
        "expected_body": {"id": 101 if is_post else 1, "author": {"id": 1}},
    }
    response_mock = Mock(status_code=case["expected_status"])
    response_mock.json.return_value = {
        "id": case["expected_body"]["id"],
        "author": {"id": 1, "name": "Offline User"},
        "title": "ApiPilot",
    }
    request_mock = post_request if is_post else get_request
    other_request_mock = get_request if is_post else post_request
    request_mock.return_value = response_mock

    # Use a temporary JSON file so the public API cases stay unchanged.
    case_file = tmp_path / "cases.json"
    case_file.write_text(json.dumps([case]), encoding="utf-8")
    loaded_case = load_cases(case_file)[0]

    response = run_case(loaded_case)
    assert_response(response, loaded_case)

    expected_arguments = {"params": case["params"], "headers": case["headers"], "timeout": 10.0}
    if is_post:
        expected_arguments["json"] = case["body"]
    request_mock.assert_called_once_with(case["url"], **expected_arguments)
    other_request_mock.assert_not_called()
    assert response is response_mock
    response_mock.json.assert_called_once_with()


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_run_case_defaults_optional_request_fields(mock_http, method):
    get_request, post_request = mock_http
    case = {
        "method": method,
        "url": "https://example.test/items",
        "expected_status": 200,
        "expected_body": {"id": 1},
    }
    response_mock = Mock(status_code=200)
    response_mock.json.return_value = {"id": 1}
    request_mock = post_request if method == "POST" else get_request
    other_request_mock = get_request if method == "POST" else post_request
    request_mock.return_value = response_mock

    response = run_case(case)
    assert_response(response, case)

    expected_arguments = {"params": None, "headers": None, "timeout": 10.0}
    if method == "POST":
        expected_arguments["json"] = None
    request_mock.assert_called_once_with(case["url"], **expected_arguments)
    other_request_mock.assert_not_called()


@pytest.mark.parametrize(
    "expected_status, expected_body",
    [(200, {"author": {"id": 1}}), (201, {"author": {"id": 2}})],
    ids=["wrong-status", "wrong-nested-body"],
)
def test_response_mismatch_raises_assertion(mock_http, expected_status, expected_body):
    get_request, post_request = mock_http
    case = {
        "method": "POST",
        "url": "https://example.test/posts",
        "body": {"title": "ApiPilot", "userId": 1},
        "expected_status": expected_status,
        "expected_body": expected_body,
    }
    response_mock = Mock(status_code=201)
    response_mock.json.return_value = {"id": 101, "author": {"id": 1}}
    post_request.return_value = response_mock

    response = run_case(case)
    with pytest.raises(AssertionError):
        assert_response(response, case)

    post_request.assert_called_once_with(
        case["url"], params=None, json=case["body"], headers=None, timeout=10.0
    )
    get_request.assert_not_called()
    if expected_status == response.status_code:
        response_mock.json.assert_called_once_with()
    else:
        response_mock.json.assert_not_called()

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.parse import quote_plus

import pytest
import requests

from src.apipilot import cli, http_client


# These are deliberately fake credentials used only to verify report redaction.
AUTH_TOKEN = "offline-private-token"
API_KEY = "offline+api/key"
COOKIE = "offline-session-value"


def write_inputs(directory):
    document = {
        "openapi": "3.1.0",
        "info": {"title": "Offline CLI example", "version": "1.0.0"},
        "paths": {
            "/health": {"get": {
                "summary": "Mock PASS", "responses": {"200": {"description": "OK"}},
            }},
            "/items": {"post": {
                "summary": "Mock FAIL",
                "requestBody": {
                    "required": True,
                    "content": {"application/json": {"schema": {"type": "object"}}},
                },
                "responses": {"201": {"description": "Created"}},
            }},
            "/unstable": {"get": {
                "summary": "Mock ERROR", "responses": {"200": {"description": "OK"}},
            }},
            "/after-error": {"get": {
                "summary": "Mock PASS after ERROR", "responses": {"200": {"description": "OK"}},
            }},
            "/items/{item_id}": {
                "parameters": [{
                    "name": "item_id", "in": "path", "required": True,
                    "schema": {"type": "string"},
                }],
                "get": {
                    "summary": "Needs item_id", "responses": {"200": {"description": "OK"}},
                },
            },
        },
    }
    config = {
        "base_url": "https://example.test/api",
        "cases": [
            {"method": "GET", "path": "/health", "expected_status": 200,
             "expected_body": {"ok": True}},
            {"method": "POST", "path": "/items", "body": {"value": "offline-example"},
             "params": {"api_key": API_KEY},
             "headers": {"Authorization": f"Bearer {AUTH_TOKEN}", "Cookie": f"sid={COOKIE}"},
             "expected_status": 201, "expected_body": {"created": True}},
            {"method": "GET", "path": "/unstable", "expected_status": 200},
            {"method": "GET", "path": "/after-error", "expected_status": 200,
             "expected_body": {"ok": True}},
            {"method": "GET", "path": "/items/{item_id}", "expected_status": 200},
        ],
    }
    openapi_file, config_file = directory / "openapi.json", directory / "config.json"
    openapi_file.write_text(json.dumps(document), encoding="utf-8")
    config_file.write_text(json.dumps(config), encoding="utf-8")
    return openapi_file, config_file


def response(status=200, body=None):
    result = Mock(status_code=status)
    result.json.return_value = body
    return result


def arguments(inputs, report):
    return ["--openapi", str(inputs[0]), "--config", str(inputs[1]), "--report", str(report)]


def run_mock_example(report_path):
    """Generate a real report file through the CLI, using only mocked HTTP calls."""
    with TemporaryDirectory() as directory:
        inputs = write_inputs(Path(directory))
        timeout = requests.Timeout(
            f"simulated timeout https://example.test?api_key={quote_plus(API_KEY)}; "
            f"Authorization: Bearer {AUTH_TOKEN}; Cookie: sid={COOKIE}"
        )
        with (
            patch.object(http_client.requests, "get", side_effect=[
                response(body={"ok": True}), timeout, response(body={"ok": True}),
            ]) as get_request,
            patch.object(http_client.requests, "post", return_value=response(201, {"created": False})) as post_request,
            patch.object(requests.sessions.Session, "request", side_effect=RuntimeError("Network disabled")),
        ):
            code = cli.main(arguments(inputs, report_path) + ["--timeout", "2.5"])
            assert get_request.call_count == 3
            assert all(call.kwargs["timeout"] == 2.5 for call in get_request.call_args_list)
            post_request.assert_called_once_with(
                "https://example.test/api/items", params={"api_key": API_KEY},
                json={"value": "offline-example"},
                headers={"Authorization": f"Bearer {AUTH_TOKEN}", "Cookie": f"sid={COOKIE}"},
                timeout=2.5,
            )
            return code


@pytest.fixture(autouse=True)
def disable_network(monkeypatch):
    monkeypatch.setattr(
        requests.sessions.Session, "request", Mock(side_effect=RuntimeError("Network disabled")),
    )


@pytest.fixture
def inputs(tmp_path):
    return write_inputs(tmp_path)


def test_cli_end_to_end_with_mocked_http(tmp_path, capsys):
    report_file = tmp_path / "reports" / "mock.json"

    assert run_mock_example(report_file) == 1

    text = report_file.read_text(encoding="utf-8")
    report = json.loads(text)
    assert report["summary"] == {"total": 4, "PASS": 2, "FAIL": 1, "ERROR": 1, "pending": 1}
    assert [item["status"] for item in report["results"]] == ["PASS", "FAIL", "ERROR", "PASS"]
    assert report["results"][1]["error"] == "Response value mismatch (values omitted)"
    assert report["results"][2]["error"] == (
        "Timeout: simulated timeout https://example.test?api_key=[REDACTED]; "
        "Authorization: [REDACTED]; Cookie: [REDACTED]"
    )
    assert report["pending_cases"][0]["reasons"] == ["Missing path parameter: item_id"]
    for secret in (AUTH_TOKEN, API_KEY, quote_plus(API_KEY), COOKIE):
        assert secret not in text
    assert "headers" not in text and '"body"' not in text
    assert "TOTAL=4 EXECUTED=4 PASS=2 FAIL=1 ERROR=1 PENDING=1" in capsys.readouterr().out


@pytest.mark.parametrize("selection", ["mixed", "ready", "pending", "empty"])
def test_terminal_and_json_use_the_same_total(inputs, tmp_path, monkeypatch, capsys, selection):
    document = json.loads(inputs[0].read_text(encoding="utf-8"))
    config = json.loads(inputs[1].read_text(encoding="utf-8"))
    if selection == "ready":
        document["paths"].pop("/items/{item_id}")
        config["cases"] = config["cases"][:-1]
    elif selection in ("pending", "empty"):
        config["cases"] = []
        if selection == "empty":
            document["paths"] = {}
    inputs[0].write_text(json.dumps(document), encoding="utf-8")
    inputs[1].write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(http_client.requests, "get", Mock(return_value=response(body={"ok": True})))
    monkeypatch.setattr(http_client.requests, "post", Mock(return_value=response(201, {"created": True})))
    report_file = tmp_path / "report.json"

    assert cli.main(arguments(inputs, report_file)) == (2 if selection in ("pending", "empty") else 0)

    report = json.loads(report_file.read_text(encoding="utf-8"))
    summary = report["summary"]
    terminal = {
        key: int(value)
        for key, value in (item.split("=") for item in capsys.readouterr().out.splitlines()[0].split())
    }
    assert terminal["TOTAL"] == terminal["EXECUTED"] == summary["total"] == len(report["results"])
    assert summary["total"] == summary["PASS"] + summary["FAIL"] + summary["ERROR"]
    assert terminal["PENDING"] == summary["pending"] == len(report["pending_cases"])
    for status in ("PASS", "FAIL", "ERROR"):
        assert terminal[status] == summary[status]


@pytest.mark.parametrize("outcome, expected_code, status", [
    ("pass", 0, "PASS"), ("fail", 1, "FAIL"), ("error", 1, "ERROR"),
])
def test_cli_exit_codes_and_default_timeout(inputs, tmp_path, monkeypatch, outcome, expected_code, status):
    config = json.loads(inputs[1].read_text(encoding="utf-8"))
    config["cases"] = config["cases"][:1]
    inputs[1].write_text(json.dumps(config), encoding="utf-8")
    request = Mock(return_value=response(body={"ok": outcome == "pass"}))
    if outcome == "error":
        request.side_effect = requests.ConnectionError("simulated connection failure")
    monkeypatch.setattr(http_client.requests, "get", request)
    report_file = tmp_path / "report.json"

    assert cli.main(arguments(inputs, report_file)) == expected_code

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["results"][0]["status"] == status
    assert report["summary"]["pending"] == 4
    request.assert_called_once_with(
        "https://example.test/api/health", params=None, headers=None, timeout=10.0,
    )


@pytest.mark.parametrize("index", [0, 1], ids=["openapi", "config"])
def test_missing_input_file(inputs, tmp_path, monkeypatch, capsys, index):
    inputs[index].unlink()
    execute = Mock()
    monkeypatch.setattr(cli, "run_suite", execute)
    report_file = tmp_path / "report.json"

    assert cli.main(arguments(inputs, report_file)) == 2

    assert "FileNotFoundError" in capsys.readouterr().err
    assert not report_file.exists()
    execute.assert_not_called()


@pytest.mark.parametrize("index, content", [
    (0, "{broken"), (1, "{broken"), (0, "[]"), (1, "[]"),
    (1, '{"base_url": "invalid"}'),
    (1, '{"base_url": "https://example.test", "cases": "invalid"}'),
])
def test_invalid_input(inputs, tmp_path, monkeypatch, capsys, index, content):
    inputs[index].write_text(content, encoding="utf-8")
    execute = Mock()
    monkeypatch.setattr(cli, "run_suite", execute)
    report_file = tmp_path / "report.json"

    assert cli.main(arguments(inputs, report_file)) == 2

    assert "ApiPilot error:" in capsys.readouterr().err
    assert not report_file.exists()
    execute.assert_not_called()


@pytest.mark.parametrize("empty_document, pending_count", [(False, 5), (True, 0)])
def test_no_executable_cases_still_writes_report(inputs, tmp_path, monkeypatch, capsys, empty_document, pending_count):
    config = {"base_url": "https://example.test", "cases": []}
    inputs[1].write_text(json.dumps(config), encoding="utf-8")
    if empty_document:
        document = json.loads(inputs[0].read_text(encoding="utf-8"))
        document["paths"] = {}
        inputs[0].write_text(json.dumps(document), encoding="utf-8")
    request = Mock()
    monkeypatch.setattr(http_client.requests, "get", request)
    monkeypatch.setattr(http_client.requests, "post", request)
    report_file = tmp_path / "report.json"

    assert cli.main(arguments(inputs, report_file)) == 2

    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["summary"]["total"] == 0
    assert len(report["pending_cases"]) == pending_count
    assert all(case["reasons"] for case in report["pending_cases"])
    assert "No executable cases" in capsys.readouterr().err
    request.assert_not_called()


@pytest.mark.parametrize("target", ["openapi", "config", "directory", "blocked-parent"])
def test_invalid_output_path_does_not_execute(inputs, tmp_path, monkeypatch, target):
    report_file = {"openapi": inputs[0], "config": inputs[1], "directory": tmp_path,
                   "blocked-parent": inputs[1] / "report.json"}[target]
    original = [file.read_bytes() for file in inputs]
    execute = Mock()
    monkeypatch.setattr(cli, "run_suite", execute)

    assert cli.main(arguments(inputs, report_file)) == 2

    assert [file.read_bytes() for file in inputs] == original
    execute.assert_not_called()


def test_report_write_error_returns_two(inputs, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(http_client.requests, "get", Mock(return_value=response(body={"ok": True})))
    monkeypatch.setattr(http_client.requests, "post", Mock(return_value=response(201, {"created": True})))
    monkeypatch.setattr(cli, "write_report", Mock(side_effect=PermissionError("cannot write report")))

    assert cli.main(arguments(inputs, tmp_path / "report.json")) == 2

    output = capsys.readouterr()
    assert "TOTAL=4 EXECUTED=4 PASS=4 FAIL=0 ERROR=0 PENDING=1" in output.out
    assert "PermissionError: cannot write report" in output.err


@pytest.mark.parametrize("timeout", ["0", "-1", "nan", "inf", "bad"])
def test_invalid_cli_timeout(inputs, tmp_path, monkeypatch, timeout):
    execute = Mock()
    monkeypatch.setattr(cli, "run_suite", execute)

    with pytest.raises(SystemExit) as error:
        cli.main(arguments(inputs, tmp_path / "report.json") + ["--timeout", timeout])

    assert error.value.code == 2
    execute.assert_not_called()


@pytest.mark.parametrize("args, expected_code, message", [
    (["--help"], 0, "--timeout"),
    ([], 2, "required"),
    (["--openapi", "missing-openapi.json", "--config", "missing-config.json",
      "--report", "unused-report.json"], 2, "FileNotFoundError"),
])
def test_python_module_entry_point(args, expected_code, message):
    project = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "src.apipilot.cli", *args], cwd=project,
        capture_output=True, text=True, timeout=10,
    )

    assert result.returncode == expected_code
    assert message in result.stdout + result.stderr

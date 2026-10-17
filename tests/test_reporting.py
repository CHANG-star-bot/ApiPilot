import json
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote, quote_plus

import pytest

from src.apipilot.reporting import collect_secrets, redact, write_report


def test_report_masks_configured_secrets_and_preserves_original(tmp_path):
    secret = 'private+value/with "quotes"'
    config = {"cases": [{
        "headers": {"X-Custom-Auth": secret, "Authorization": "Bearer separate-token"},
        "params": {"api_key": secret}, "body": {"password": secret},
    }]}
    report = {
        "summary": {"total": 1, "PASS": 0, "FAIL": 0, "ERROR": 1, "pending": 0},
        "results": [{"name": "Configured " + secret, "status": "ERROR",
                     "error": f"Failure: {secret!r}; {quote(secret, safe='')}; {quote_plus(secret)}"}],
        "pending_cases": [{"name": "Pending", "reasons": ["Missing " + secret]}],
        "authorization": "another-secret",
    }
    original = deepcopy(report)
    output = tmp_path / "reports" / "result.json"

    write_report(report, output, collect_secrets(config))

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved["authorization"] == "[REDACTED]"
    assert saved["results"][0]["status"] == "ERROR"
    assert saved["results"][0]["name"] == "Configured [REDACTED]"
    assert saved["pending_cases"][0]["reasons"] == ["Missing [REDACTED]"]
    assert "private" not in saved["results"][0]["error"]
    assert report == original


@pytest.mark.parametrize("message, secrets", [
    ("Authorization: Bearer unknown-token", ["unknown-token"]),
    ("https://example.test?api_key=unknown-key&limit=1", ["unknown-key"]),
    ('{"access_token": "unknown token with spaces"}', ["unknown token with spaces"]),
    ("Cookie: sid=unknown-session; other=unknown-other", ["unknown-session", "unknown-other"]),
    ("https://user:unknown-password@example.test/path", ["user:", "unknown-password"]),
    ("Basic dXNlcjpwYXNz", ["dXNlcjpwYXNz"]),
])
def test_common_authentication_patterns_are_masked(message, secrets):
    sanitized = redact(message)
    assert "[REDACTED]" in sanitized
    for secret in secrets:
        assert secret not in sanitized


def test_response_value_mismatches_omit_unconfigured_actual_secrets():
    assert redact("Expected 'anything', got 'server-only-credential'") == (
        "Response value mismatch (values omitted)"
    )
    assert redact("Expected status 200, got 403") == "Expected status 200, got 403"
    assert redact("Expected object, got NoneType") == "Expected object, got NoneType"


def test_collect_secrets_handles_empty_bearer_and_url_credentials():
    config = {"headers": {"Authorization": "Bearer "},
              "base_url": "https://name:p%2Bass@example.test", "token": 12345}
    secrets = collect_secrets(config)
    assert "p+ass" in secrets and "12345" in secrets
    assert "p+ass" not in redact("connection error p+ass 12345", secrets)
    assert redact({"status": "PASS", "method": "GET"}, ("PASS", "GET")) == {
        "status": "PASS", "method": "GET",
    }


def test_failed_atomic_write_preserves_existing_report(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    output.write_text('{"previous": true}', encoding="utf-8")

    def denied_replace(self, target):
        raise PermissionError("simulated replacement failure")

    monkeypatch.setattr(Path, "replace", denied_replace)
    with pytest.raises(PermissionError):
        write_report({"new": True}, output)

    assert json.loads(output.read_text(encoding="utf-8")) == {"previous": True}
    assert list(tmp_path.glob("*.tmp")) == []

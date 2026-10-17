from unittest.mock import Mock

import pytest

from src.apipilot import http_client


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("timeout", [None, 2.5], ids=["default", "custom"])
def test_timeout_is_passed_to_http_request(monkeypatch, method, timeout):
    request = Mock()
    monkeypatch.setattr(http_client.requests, method.lower(), request)
    kwargs = {} if timeout is None else {"timeout": timeout}

    http_client.send_request(method, "https://example.test", **kwargs)

    assert request.call_args.kwargs["timeout"] == (10.0 if timeout is None else timeout)


@pytest.mark.parametrize("timeout", [None, 0, -1, False, float("nan"), float("inf"), "bad"])
def test_invalid_timeout_is_rejected_before_request(monkeypatch, timeout):
    request = Mock()
    monkeypatch.setattr(http_client.requests, "get", request)

    with pytest.raises(ValueError, match="positive finite number"):
        http_client.send_request("GET", "https://example.test", timeout=timeout)

    request.assert_not_called()

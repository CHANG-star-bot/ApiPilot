import math

import requests


DEFAULT_TIMEOUT = 10.0


def send_request(method, url, params=None, json=None, headers=None, timeout=DEFAULT_TIMEOUT):
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
        raise ValueError("timeout must be a positive finite number of seconds")
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("timeout must be a positive finite number of seconds")
    method = method.upper()

    if method == "GET":
        response = requests.get(
            url,
            params=params,
            headers=headers,
            timeout=timeout
        )

    elif method == "POST":
        response = requests.post(
            url,
            params=params,
            json=json,
            headers=headers,
            timeout=timeout
        )

    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    return response

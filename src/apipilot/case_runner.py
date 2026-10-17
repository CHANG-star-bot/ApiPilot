from src.apipilot.http_client import DEFAULT_TIMEOUT, send_request

def run_case(case, timeout=DEFAULT_TIMEOUT):
    response=send_request(
        method=case["method"],
        url=case["url"],
        params=case.get("params"),
        json=case.get("body"),
        headers=case.get("headers"),
        timeout=timeout
    )

    return response

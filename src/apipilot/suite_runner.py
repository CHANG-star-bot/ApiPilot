from copy import deepcopy

from .assertions import assert_response
from .case_runner import run_case
from .http_client import DEFAULT_TIMEOUT


def run_suite(executable_cases, pending_cases=None, timeout=DEFAULT_TIMEOUT):
    """Execute generated cases sequentially and return a JSON-serializable report.

    Call with run_suite(**generate_cases(openapi_path, config_path)).
    summary.total counts executed cases only; pending cases are copied unchanged.
    Ordinary per-case exceptions are recorded without stopping the suite.
    KeyboardInterrupt and SystemExit still propagate so execution can be stopped.
    """
    pending = deepcopy(pending_cases) if pending_cases is not None else []
    results = []
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0}

    for index, case in enumerate(executable_cases, start=1):
        name = case.get("name") if isinstance(case, dict) else None
        status, error = _execute_case(case, timeout)
        results.append({"name": name or f"Case {index}", "status": status, "error": error})
        counts[status] += 1

    return {
        "summary": {"total": len(results), **counts, "pending": len(pending)},
        "results": results,
        "pending_cases": pending,
    }


def _execute_case(case, timeout):
    # An execution error is ERROR, even if it happens to be AssertionError.
    try:
        response = run_case(case, timeout=timeout)
    except Exception as error:
        return "ERROR", f"{type(error).__name__}: {error}"

    try:
        assert_response(response, case)
    except AssertionError as error:
        return "FAIL", str(error) or "Response assertion failed"
    except Exception as error:
        # Includes errors while decoding the response JSON.
        return "ERROR", f"{type(error).__name__}: {error}"

    return "PASS", None

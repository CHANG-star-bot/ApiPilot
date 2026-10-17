import pytest

from src.apipilot.case_loader import load_cases
from src.apipilot.case_runner import run_case
from src.apipilot.assertions import assert_response


cases = load_cases("cases/user_cases.json")


@pytest.mark.parametrize(
    "case",
    cases,
    ids=[case["name"] for case in cases]
)
@pytest.mark.integration
def test_user_case(case):
    response = run_case(case)

    assert_response(response, case)

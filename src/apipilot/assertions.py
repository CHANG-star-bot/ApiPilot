def assert_data(actual, expected):
    if isinstance(expected, dict):
        assert isinstance(actual, dict), f"Expected object, got {type(actual).__name__}"
        for key, expected_value in expected.items():
            assert key in actual, f"Missing key: {key!r}"
            assert_data(actual[key], expected_value)

    elif isinstance(expected, list):
        assert isinstance(actual, list), f"Expected array, got {type(actual).__name__}"
        assert len(actual) >= len(expected), (
            f"Expected at least {len(expected)} items, got {len(actual)}"
        )

        for index, expected_item in enumerate(expected):
            assert_data(actual[index], expected_item)

    else:
        assert actual == expected, f"Expected {expected!r}, got {actual!r}"


def assert_response(response, case):
    assert response.status_code == case["expected_status"], (
        f"Expected status {case['expected_status']}, got {response.status_code}"
    )

    expected_body = case.get("expected_body")

    if expected_body is not None:
        actual_body = response.json()
        assert_data(actual_body, expected_body)

from src.apipilot.http_client import send_request
import pytest

@pytest.mark.integration
def test_send_get_request():
    response = send_request("GET", "http://jsonplaceholder.typicode.com/users/1")

    assert response.status_code == 200
    assert response.json()["id"]==1

@pytest.mark.integration
def test_send_get_request_with_params():
    response = send_request(
        method="GET",
        url="https://jsonplaceholder.typicode.com/comments",
        params={"postId": 1}
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) > 0
    assert data[0]["postId"] == 1

def test_unsupported_method():
    with pytest.raises(ValueError):
        send_request(
            method="ABC",
            url="https://example.com"
        )

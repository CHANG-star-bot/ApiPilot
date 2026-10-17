import requests
import pytest


@pytest.mark.integration
def test_get_user():
    url = "https://jsonplaceholder.typicode.com/users/1"

    response = requests.get(url)
    data = response.json()

    assert response.status_code == 200
    assert data["id"] == 1

@pytest.mark.integration
def test_get_wrong_user_id():
    url = "https://jsonplaceholder.typicode.com/users/1"

    response = requests.get(url)
    data = response.json()

    assert data["id"] == 2

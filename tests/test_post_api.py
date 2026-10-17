import requests
import pytest


@pytest.mark.integration
def test_create_post():
    url = "https://jsonplaceholder.typicode.com/posts"

    data = {
        "title": "ApiPilot",
        "body": "My first POST request",
        "userId": 1
    }

    response = requests.post(url, json=data)

    print("status:", response.status_code)
    print("response:", response.json())

    assert response.status_code == 201

import requests


url = "https://jsonplaceholder.typicode.com/users/1"

response = requests.get(url)

data = response.json()

print(response.status_code)
print(data["name"])

assert response.status_code == 200
assert data["id"] == 2
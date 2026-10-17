import json
from pathlib import Path

import pytest

from src.apipilot.openapi_parser import parse_openapi


@pytest.fixture
def document():
    return {
        "openapi": "3.0.3",
        "info": {"title": "Test API", "version": "1.0.0"},
        "paths": {"/users": {"get": {"responses": {"200": {"description": "OK"}}}}},
    }


def write_document(tmp_path, document):
    file_path = tmp_path / "openapi.json"
    file_path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return file_path


def test_parse_sample_document():
    sample_path = Path(__file__).resolve().parents[1] / "examples" / "sample_openapi.json"

    assert parse_openapi(sample_path) == [
        {
            "method": "GET",
            "path": "/users",
            "summary": "List users",
            "parameters": [
                {
                    "name": "limit",
                    "in": "query",
                    "required": False,
                    "schema": {"type": "integer", "minimum": 1},
                }
            ],
            "has_request_body": False,
        },
        {
            "method": "POST",
            "path": "/users",
            "summary": "POST /users",
            "parameters": [],
            "has_request_body": True,
        },
    ]


@pytest.mark.parametrize("version", ["3.0.3", "3.1.0"])
def test_supports_openapi_versions(tmp_path, document, version):
    document["openapi"] = version

    interfaces = parse_openapi(write_document(tmp_path, document))

    assert [(item["method"], item["path"]) for item in interfaces] == [("GET", "/users")]


def test_only_extracts_get_and_post(tmp_path, document):
    path_item = document["paths"]["/users"]
    path_item.update({
        "summary": "Users",
        "description": "Path metadata is not an operation",
        "servers": [{"url": "/v1"}],
        "post": {"responses": {"201": {"description": "Created"}}},
        "put": {"responses": {"200": {"description": "Updated"}}},
        "delete": {"responses": {"204": {"description": "Deleted"}}},
    })
    document["paths"]["x-note"] = "A specification extension"

    interfaces = parse_openapi(write_document(tmp_path, document))

    assert [item["method"] for item in interfaces] == ["GET", "POST"]


def test_inherits_and_overrides_parameters(tmp_path, document):
    user_id = {
        "name": "user_id", "in": "path", "required": True, "schema": {"type": "integer"}
    }
    default_limit = {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 10}}
    operation_limit = {"name": "limit", "in": "query", "schema": {"type": "integer", "default": 20}}
    header = {"name": "limit", "in": "header", "schema": {"type": "string"}}
    document["paths"] = {
        "/users/{user_id}": {
            "parameters": [user_id, default_limit],
            "get": {
                "parameters": [operation_limit, header],
                "responses": {"200": {"description": "OK"}},
            },
        }
    }

    interface = parse_openapi(write_document(tmp_path, document))[0]

    assert interface["path"] == "/users/{user_id}"
    assert interface["parameters"] == [user_id, operation_limit, header]


@pytest.mark.parametrize("summary", [None, ""])
def test_defaults_missing_fields(tmp_path, document, summary):
    # None here means omit summary, rather than put JSON null in the document.
    if summary is not None:
        document["paths"]["/users"]["get"]["summary"] = summary

    assert parse_openapi(write_document(tmp_path, document)) == [{
        "method": "GET",
        "path": "/users",
        "summary": "GET /users",
        "parameters": [],
        "has_request_body": False,
    }]


def test_preserves_utf8_summary(tmp_path, document):
    document["paths"]["/users"]["get"]["summary"] = "获取用户列表"

    assert parse_openapi(write_document(tmp_path, document))[0]["summary"] == "获取用户列表"


def test_keeps_references_without_resolving_them(tmp_path, document):
    reference = {"$ref": "./parameters.json#/limit"}
    document["paths"]["/users"]["get"]["parameters"] = [reference]
    document["paths"]["/users"]["get"]["requestBody"] = {"$ref": "./bodies.json#/filter"}

    interface = parse_openapi(write_document(tmp_path, document))[0]

    assert interface["parameters"] == [reference]
    assert interface["has_request_body"] is True


def test_empty_paths(tmp_path, document):
    document["paths"] = {}

    assert parse_openapi(write_document(tmp_path, document)) == []


@pytest.mark.parametrize("section", ["components", "webhooks"])
def test_openapi_31_without_paths(tmp_path, document, section):
    document["openapi"] = "3.1.0"
    del document["paths"]
    document[section] = {}

    assert parse_openapi(write_document(tmp_path, document)) == []


@pytest.mark.parametrize("invalid_document", [[], None, "not an object"])
def test_rejects_non_object_documents(tmp_path, invalid_document):
    with pytest.raises(ValueError, match="document must be an object"):
        parse_openapi(write_document(tmp_path, invalid_document))


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("openapi", None, "Only OpenAPI"),
        ("openapi", "2.0", "Only OpenAPI"),
        ("openapi", "3.2.0", "Only OpenAPI"),
        ("openapi", "3.1", "Only OpenAPI"),
        ("info", None, "info must contain"),
        ("info", {"title": "Missing version"}, "info must contain"),
        ("paths", None, "paths must be an object"),
        ("paths", [], "paths must be an object"),
    ],
)
def test_rejects_invalid_top_level_fields(tmp_path, document, field, value, message):
    document[field] = value

    with pytest.raises(ValueError, match=message):
        parse_openapi(write_document(tmp_path, document))


@pytest.mark.parametrize("field", ["openapi", "info", "paths"])
def test_rejects_missing_required_fields(tmp_path, document, field):
    del document[field]

    with pytest.raises(ValueError):
        parse_openapi(write_document(tmp_path, document))


@pytest.mark.parametrize(
    "path_item, message",
    [
        ([], "Path Item must be an object"),
        ({"get": []}, "Operation must be an object"),
        ({"get": {"summary": None}}, "summary must be a string"),
        ({"parameters": {}, "get": {}}, "parameters must be an array"),
        ({"get": {"parameters": {}}}, "parameters must be an array"),
        ({"get": {"parameters": [1]}}, "Each parameter must be an object"),
        ({"get": {"parameters": [{"name": "q"}]}}, "Inline parameters need"),
        ({"get": {"parameters": [{"in": "query"}]}}, "Inline parameters need"),
        ({"get": {"parameters": [{"$ref": 1}]}}, r"Parameter \$ref must be a string"),
        ({"post": {"requestBody": []}}, "requestBody must be an object"),
        ({"$ref": "#/components/pathItems/Users"}, "Path Item references are not supported"),
    ],
)
def test_rejects_invalid_or_unsupported_path_items(tmp_path, document, path_item, message):
    document["paths"]["/users"] = path_item

    with pytest.raises(ValueError, match=message):
        parse_openapi(write_document(tmp_path, document))


def test_rejects_invalid_path(tmp_path, document):
    document["paths"] = {"users": document["paths"]["/users"]}

    with pytest.raises(ValueError, match="path must start"):
        parse_openapi(write_document(tmp_path, document))


def test_rejects_invalid_json(tmp_path):
    file_path = tmp_path / "broken.json"
    file_path.write_text('{"openapi":', encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid OpenAPI JSON"):
        parse_openapi(file_path)


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        parse_openapi(tmp_path / "missing.json")

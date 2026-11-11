"""No external calls or real credentials: all HTTP is an in-memory transport."""
import json

import httpx
import pytest

from embodied_notes import provider

FAKE_KEY = "unit-test-sentinel-never-a-real-credential"


@pytest.fixture(autouse=True)
def isolated_model_environment(monkeypatch):
    for name in ("EPN_MODEL", "EPN_API_KEY", "EPN_BASE_URL", "EPN_MAX_INPUT_CHARS"):
        monkeypatch.delenv(name, raising=False)


def configure(monkeypatch):
    monkeypatch.setenv("EPN_MODEL", "unit-test-model")
    monkeypatch.setenv("EPN_API_KEY", FAKE_KEY)


def mock_http(monkeypatch, handler):
    original = httpx.Client
    calls = []

    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"] == 180

        def wrapped(request):
            calls.append(request)
            return handler(request)

        return original(transport=httpx.MockTransport(wrapped), **kwargs)

    monkeypatch.setattr(provider.httpx, "Client", factory)
    return calls


def forbid_http(monkeypatch):
    def unexpected(**kwargs):
        pytest.fail("A configuration or size failure must occur before an HTTP request")
    monkeypatch.setattr(provider.httpx, "Client", unexpected)


@pytest.mark.parametrize("model,key", [(None, None), ("configured", None), (None, FAKE_KEY), ("   ", FAKE_KEY)])
def test_requires_explicit_model_and_key(monkeypatch, model, key):
    forbid_http(monkeypatch)
    if model is not None:
        monkeypatch.setenv("EPN_MODEL", model)
    if key is not None:
        monkeypatch.setenv("EPN_API_KEY", key)
    with pytest.raises(ValueError, match="requires EPN_MODEL and EPN_API_KEY") as caught:
        provider.generate({})
    assert FAKE_KEY not in str(caught.value)


@pytest.mark.parametrize("endpoint", [
    "http://remote.example/v1", "http://localhost:80@remote.example/v1",
    "http://127.0.0.1:80@remote.example/v1", "https://user:password@remote.example/v1",
    "https://remote.example:bad/v1", "https://remote.example/v1?secret=value",
])
def test_rejects_nonlocal_http_and_credential_urls_before_sending(monkeypatch, endpoint):
    configure(monkeypatch)
    forbid_http(monkeypatch)
    monkeypatch.setenv("EPN_BASE_URL", endpoint)
    with pytest.raises(ValueError, match="EPN_BASE_URL") as caught:
        provider.generate({})
    assert endpoint not in str(caught.value)
    assert FAKE_KEY not in str(caught.value)


def test_rejects_oversized_evidence_without_truncation_or_request(monkeypatch):
    configure(monkeypatch)
    forbid_http(monkeypatch)
    monkeypatch.setenv("EPN_MAX_INPUT_CHARS", "100")
    packet = {"chunks": [{"text": "x" * 200}]}
    with pytest.raises(ValueError, match="No silent truncation"):
        provider.generate(packet)
    assert len(packet["chunks"][0]["text"]) == 200


@pytest.mark.parametrize("limit", ["nope", "0", "-4"])
def test_invalid_size_configuration_fails_before_request(monkeypatch, limit):
    configure(monkeypatch)
    forbid_http(monkeypatch)
    monkeypatch.setenv("EPN_MAX_INPUT_CHARS", limit)
    with pytest.raises(ValueError, match="positive integer"):
        provider.generate({})


@pytest.mark.parametrize("kind,endpoint", [("summary", "https://models.example/v1"), ("research", "http://[::1]:8080/v1")])
def test_returns_json_object_and_sends_the_corresponding_schema(monkeypatch, kind, endpoint):
    configure(monkeypatch)
    monkeypatch.setenv("EPN_BASE_URL", endpoint)

    def handler(request):
        assert str(request.url) == endpoint + "/chat/completions"
        assert request.headers["authorization"] == "Bearer " + FAKE_KEY
        sent = json.loads(request.content)
        assert sent["response_format"] == {"type": "json_object"}
        material = json.loads(sent["messages"][1]["content"])
        assert material["allowed_tags"] == []  # An explicit empty override stays empty.
        assert FAKE_KEY not in sent["messages"][1]["content"]
        assert ("coverage" if kind == "summary" else "packet_id") in material["output_schema"]["required"]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": '{"result":"ok"}'}}]})

    calls = mock_http(monkeypatch, handler)
    assert provider.generate({"allowed_tags": ["task/manipulation"]}, kind=kind, tags=[]) == {"result": "ok"}
    assert len(calls) == 1


@pytest.mark.parametrize("status", [302, 401, 429, 500])
def test_http_failures_are_not_retried_and_do_not_echo_response_or_credentials(monkeypatch, status):
    configure(monkeypatch)
    calls = mock_http(monkeypatch, lambda request: httpx.Response(status, text="Authorization: Bearer " + FAKE_KEY,
                                                               headers={"location": "https://other.example"}))
    with pytest.raises(ValueError, match=f"HTTP {status}") as caught:
        provider.generate({})
    assert FAKE_KEY not in str(caught.value)
    assert len(calls) == 1


@pytest.mark.parametrize("response", [
    None, {"choices": []}, {"choices": [FAKE_KEY]},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": "invalid-json " + FAKE_KEY}}]},
    {"choices": [{"message": {"content": json.dumps([FAKE_KEY])}}]},
    {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
])
def test_malformed_or_incomplete_model_output_is_rejected_without_echo(monkeypatch, response):
    configure(monkeypatch)
    mock_http(monkeypatch, lambda request: httpx.Response(200, json=response))
    with pytest.raises(ValueError) as caught:
        provider.generate({})
    assert FAKE_KEY not in str(caught.value)


def test_network_exception_text_is_not_exposed_or_retried(monkeypatch):
    configure(monkeypatch)

    def handler(request):
        raise httpx.ConnectError("transport echoed credential " + FAKE_KEY, request=request)

    calls = mock_http(monkeypatch, handler)
    with pytest.raises(ValueError, match="ConnectError") as caught:
        provider.generate({})
    assert FAKE_KEY not in str(caught.value)
    assert len(calls) == 1

import httpx
import pytest
from fastapi.testclient import TestClient
from aetheris.api import Settings, create_app, summarize, validate_url


class MockProvider:
    def __init__(self, broken=False):
        self.calls = 0
        self.broken = broken

    async def retrieve(self, url: str) -> str:
        self.calls += 1
        if self.broken:
            raise httpx.ConnectError("private upstream details must not leak")
        return "Project summary for demonstration\nThe report checks input records for common data issues.\nThe output is intended for operations teams to review."


@pytest.fixture
def provider():
    return MockProvider()


@pytest.fixture
def client(provider):
    return TestClient(create_app(Settings("demo-token", frozenset({"example.com"})), provider))


def test_health_does_not_expose_token(client):
    data = client.get("/healthz").json()
    assert data == {"status": "ok"}
    assert "demo-token" not in str(data)


def test_auth_fail_closed(client, provider):
    payload = {"url": "https://example.com/docs"}
    assert client.post("/extract", json=payload).status_code == 401
    assert client.post("/extract", json=payload, headers={"X-Proxy-Key": "wrong"}).status_code == 401
    assert provider.calls == 0


@pytest.mark.parametrize("url", [
    "http://example.com/docs", "https://localhost/home", "https://127.0.0.1/a",
    "https://example.com.evil.test/", "https://example.com:8443/",
    "https://user:pass@example.com/", "https://example.com/one#fragment",
    "https://169.254.169.254/metadata", "file:///etc/passwd",
])
def test_url_restrictions(url):
    with pytest.raises(ValueError):
        validate_url(url, frozenset({"example.com"}))


def test_rejects_unconfigured_hosts():
    with pytest.raises(ValueError):
        validate_url("https://example.com/test", frozenset())


def test_success_source_based_fields(client, provider):
    response = client.post("/extract", headers={"X-Proxy-Key": "demo-token"}, json={"url": "https://example.com/docs", "topic": "ops"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["headline"] == "Project summary for demonstration"
    assert data["source_url"] == "https://example.com/docs"
    assert data["topic"] == "ops"
    assert len(data["key_facts"]) == 2
    assert provider.calls == 1


def test_provider_failure_is_generic():
    client = TestClient(create_app(Settings("demo-token", frozenset({"example.com"})), MockProvider(broken=True)))
    response = client.post("/extract", headers={"X-Proxy-Key": "demo-token"}, json={"url": "https://example.com/docs"})
    assert response.status_code == 502
    assert "private upstream" not in response.text


def test_summarization_is_deterministic():
    body = "A short title that describes the source\nA factual sentence describing a record audit process.\nAnother sentence describing an audit result with evidence."
    assert summarize(body) == summarize(body)


def test_no_credentials_means_no_access():
    client = TestClient(create_app(Settings("", frozenset({"example.com"})), MockProvider()))
    assert client.post("/extract", headers={"X-Proxy-Key": "anything"}, json={"url": "https://example.com/docs"}).status_code == 401

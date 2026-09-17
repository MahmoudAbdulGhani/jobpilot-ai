"""Independent pack configuration exercised through the real SDK with mocked HTTP."""
import json
import socket
import httpx
import pytest
from openai import OpenAI
from pydantic import ValidationError
from app.core.config import Settings
from app.evaluation.fixtures import cases
from app.services.application_pack_service import pack_provider_for, pack_provider_configuration
from app.services.profile_suggestion_service import provider_configuration, SuggestionError
from app.services.ai_provider import ProviderFailure

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("No provider network requests permitted")
    monkeypatch.setattr(socket.socket, "connect", forbidden)

def config(**kw):
    values = dict(SECRET_KEY="x"*48, POSTGRES_USER="test", POSTGRES_PASSWORD="test",
        JOBPILOT_AI_ENABLED=True, JOBPILOT_AI_TEST_PROVIDER=False,
        JOBPILOT_AI_PROVIDER="groq", JOBPILOT_GROQ_MODEL="openai/gpt-oss-20b",
        JOBPILOT_GROQ_API_KEY="synthetic", JOBPILOT_OPENAI_API_KEY="synthetic",
        JOBPILOT_AI_MAX_OUTPUT_TOKENS=1500, JOBPILOT_AI_TIMEOUT_SECONDS=30)
    values.update(kw)
    return Settings(_env_file=None, **values)

def test_pack_settings_reach_wire_without_changing_profile_fit_configuration(monkeypatch):
    requests, clients = [], []
    def transport(request):
        requests.append(json.loads(request.content))
        assert str(request.url) == "https://api.openai.com/v1/responses"
        return httpx.Response(400, json={"error": {"type": "invalid_request_error"}})
    def client(**kw):
        assert kw["max_retries"] == 0 and kw["timeout"] == 60
        result = OpenAI(**kw, http_client=httpx.Client(transport=httpx.MockTransport(transport)))
        clients.append(result)
        return result
    monkeypatch.setattr("openai.OpenAI", client)
    settings = config()
    assert provider_configuration(settings)[:2] == ("groq", "openai/gpt-oss-20b")
    assert pack_provider_configuration(settings)[:2] == ("openai", "gpt-5-mini")
    provider = pack_provider_for(settings)
    try:
        with pytest.raises(ProviderFailure):
            provider.create_pack(cases()[0]["source"])
        assert len(requests) == 1
        wire = requests[0]
        assert wire["reasoning"] == {"effort": "minimal"}
        assert wire["max_output_tokens"] == 4000
        assert wire["text"]["format"]["strict"] is True
        assert wire["model"] == "gpt-5-mini" and wire["store"] is False
        assert provider._profile_request_options() == {}
        assert settings.JOBPILOT_AI_MAX_OUTPUT_TOKENS == 1500
        assert settings.JOBPILOT_AI_TIMEOUT_SECONDS == 30
    finally:
        for client in clients: client.close()

@pytest.mark.parametrize("overrides", [{"JOBPILOT_OPENAI_API_KEY":None}, {"JOBPILOT_AI_ENABLED":False}])
def test_pack_fail_closed_without_fallback(overrides):
    with pytest.raises(SuggestionError):
        pack_provider_for(config(**overrides))

@pytest.mark.parametrize("field,value", [("JOBPILOT_PACK_MAX_OUTPUT_TOKENS",0), ("JOBPILOT_PACK_TIMEOUT_SECONDS",0), ("JOBPILOT_PACK_REASONING_EFFORT","none"), ("JOBPILOT_PACK_PROVIDER","groq")])
def test_unsupported_pack_settings_rejected(field,value):
    with pytest.raises(ValidationError): config(**{field:value})

def test_test_provider_remains_guarded():
    with pytest.raises(SuggestionError):
        pack_provider_for(config(JOBPILOT_AI_TEST_PROVIDER=True,E2E_TEST_MODE=False))

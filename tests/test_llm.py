import httpx
import pytest

from app.config import Settings, _ensure_v1
from app.llm import LLMError, structure_dump, transcribe_audio


def _settings(**kwargs) -> Settings:
    payload = {
        "LLM_BASE_URL": "http://router:8080/v1",
        "LLM_API_KEY": "",
        "LLM_MODEL": "auto",
        "LLM_ROUTER_URL": "",
        "LLM_ROUTER_API_TOKEN": "",
        "LLM_ROUTER_MODEL": "",
        "LM_API_KEY": "",
        "STT_BASE_URL": "",
        "STT_API_KEY": "",
        "STT_MODEL": "whisper-1",
    }
    payload.update(kwargs)
    return Settings.model_construct(**payload)


def test_router_url_alias_is_enough():
    settings = _settings(
        LLM_BASE_URL="",
        LLM_ROUTER_URL="http://172.16.22.193:8080/v1",
        LM_API_KEY="local",
    )
    assert settings.llm_base_url == "http://172.16.22.193:8080/v1"
    assert settings.stt_base_url == "http://172.16.22.193:8080/v1"
    assert settings.llm_api_key == "local"


def test_ensure_v1_appends_when_missing():
    assert _ensure_v1("http://router:8080") == "http://router:8080/v1"
    assert _ensure_v1("http://router:8080/v1") == "http://router:8080/v1"
    assert _ensure_v1("") == ""


@pytest.mark.asyncio
async def test_stt_requires_base_url_not_api_key():
    settings = _settings(LLM_BASE_URL="", STT_BASE_URL="")
    assert settings.stt_base_url == ""
    with pytest.raises(LLMError, match="STT is not configured"):
        await transcribe_audio("/tmp/none.m4a", settings=settings)


@pytest.mark.asyncio
async def test_transcribe_does_not_require_api_key(tmp_path, monkeypatch):
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"fake")
    settings = _settings(LLM_API_KEY="")
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, data=None, files=None, json=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["data"] = data
            return httpx.Response(200, json={"text": "buy milk"})

    monkeypatch.setattr("app.llm.httpx.AsyncClient", FakeClient)
    text = await transcribe_audio(audio, settings=settings)
    assert text == "buy milk"
    assert captured["url"] == "http://router:8080/v1/audio/transcriptions"
    assert "Authorization" not in captured["headers"]


@pytest.mark.asyncio
async def test_structure_sends_stream_false(monkeypatch):
    settings = _settings(LLM_BASE_URL="http://router:8080", LLM_API_KEY="local")
    captured = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, headers=None, data=None, files=None, json=None):
            captured["url"] = url
            captured["headers"] = headers or {}
            captured["json"] = json
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": '{"action":"create","title":"Milk","ideas":["buy milk"],"confidence":0.9}'
                            }
                        }
                    ]
                },
            )

    monkeypatch.setattr("app.llm.httpx.AsyncClient", FakeClient)
    result = await structure_dump("buy milk", [], settings=settings)
    assert captured["url"] == "http://router:8080/v1/chat/completions"
    assert captured["json"]["stream"] is False
    assert captured["json"]["model"] == "auto"
    assert captured["headers"]["Authorization"] == "Bearer local"
    assert result.title == "Milk"

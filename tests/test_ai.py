import io
import json

import pytest

from civicloop.ai import (
    AIAdapterError,
    GeminiAdapter,
    InvalidAnalysisOutput,
    OpenWeightHTTPAdapter,
    create_analysis_adapter_from_env,
    validate_analysis_output,
)


class FakeGeminiResponse:
    text = '{"category":"mixed_waste","severity":"high","confidence":0.9,"details":{"bags":2}}'


class FakeGeminiModels:
    def __init__(self):
        self.contents = None

    def generate_content(self, **kwargs):
        self.contents = kwargs["contents"]
        return FakeGeminiResponse()


class FakeGeminiClient:
    def __init__(self):
        self.models = FakeGeminiModels()


class FakeHTTPResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


def test_validate_analysis_output_rejects_invalid_values():
    with pytest.raises(InvalidAnalysisOutput):
        validate_analysis_output({"category": "", "confidence": 0.5})
    with pytest.raises(InvalidAnalysisOutput):
        validate_analysis_output({"category": "waste", "confidence": 2})
    with pytest.raises(InvalidAnalysisOutput):
        validate_analysis_output({"category": "waste", "details": []})


def test_gemini_adapter_returns_validated_output_and_receives_image():
    client = FakeGeminiClient()
    adapter = GeminiAdapter(client=client)
    result = adapter.analyze({"description": "waste", "media": [{"content": b"image", "content_type": "image/jpeg"}]})

    assert result["category"] == "mixed_waste"
    assert result["confidence"] == 0.9
    assert client.models.contents[0].startswith("Analyze this waste-management incident")


def test_open_weight_adapter_parses_openai_compatible_response():
    def opener(_request, timeout):
        assert timeout == 5
        return FakeHTTPResponse({"choices": [{"message": {"content": '{"category":"plastic","severity":"medium","confidence":0.8,"details":{}}'}}]})

    adapter = OpenWeightHTTPAdapter("http://model.test/v1", "vision-model", timeout_seconds=5, opener=opener)
    result = adapter.analyze({"description": "plastic", "media": [{"content": b"image", "content_type": "image/jpeg"}]})

    assert result["category"] == "plastic"
    assert result["severity"] == "medium"


def test_open_weight_adapter_supports_json_content_response():
    def opener(_request, timeout):
        return FakeHTTPResponse({"choices": [{"message": {"content": {"category": "organic", "severity": "low", "confidence": 0.7, "details": {}}}}]})

    adapter = OpenWeightHTTPAdapter("http://model.test", "vision-model", opener=opener)
    assert adapter.analyze({"description": "leaves"})["category"] == "organic"


def test_adapter_factory_selects_open_weight(monkeypatch):
    monkeypatch.setenv("CIVICLOOP_AI_PROVIDER", "open_weight")
    monkeypatch.setenv("OPEN_WEIGHT_ENDPOINT", "http://model.test")
    monkeypatch.setenv("OPEN_WEIGHT_MODEL", "vision-model")

    adapter = create_analysis_adapter_from_env()

    assert isinstance(adapter, OpenWeightHTTPAdapter)


def test_adapter_factory_rejects_incomplete_open_weight_config(monkeypatch):
    monkeypatch.setenv("CIVICLOOP_AI_PROVIDER", "open_weight")
    monkeypatch.delenv("OPEN_WEIGHT_ENDPOINT", raising=False)
    monkeypatch.delenv("OPEN_WEIGHT_MODEL", raising=False)

    with pytest.raises(AIAdapterError):
        create_analysis_adapter_from_env()
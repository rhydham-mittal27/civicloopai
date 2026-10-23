from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.request import Request, urlopen


class AIAdapterError(RuntimeError):
    """Raised when a model provider cannot produce valid analysis."""


class InvalidAnalysisOutput(AIAdapterError):
    pass


@dataclass(frozen=True)
class AnalysisOutput:
    category: str
    severity: str | None
    confidence: float | None
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "severity": self.severity,
            "confidence": self.confidence,
            "details": self.details,
        }


def validate_analysis_output(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidAnalysisOutput("Model output must be a JSON object")
    category = value.get("category")
    if not isinstance(category, str) or not category.strip():
        raise InvalidAnalysisOutput("Model output requires a non-empty category")
    severity = value.get("severity")
    if severity is not None and severity not in {"low", "medium", "high", "critical"}:
        raise InvalidAnalysisOutput("Severity must be low, medium, high, or critical")
    confidence = value.get("confidence")
    if confidence is not None:
        if (
            isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not 0 <= confidence <= 1
        ):
            raise InvalidAnalysisOutput("Confidence must be between 0 and 1")
        confidence = float(confidence)
    details = value.get("details", {})
    if not isinstance(details, dict):
        raise InvalidAnalysisOutput("Details must be a JSON object")
    return AnalysisOutput(
        category=category.strip(),
        severity=severity,
        confidence=confidence,
        details=details,
    ).as_dict()


class AnalysisAdapter(Protocol):
    provider: str
    model_name: str

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def _prompt_for(payload: dict[str, Any]) -> str:
    return (
        "Analyze this waste-management incident. Return only JSON with this shape: "
        '{"category": string, "severity": "low|medium|high|critical", '
        '"confidence": number between 0 and 1, "details": object}. '
        "Do not invent location facts. Incident data: "
        + json.dumps(
            {key: value for key, value in payload.items() if key != "media"},
            default=str,
        )
    )


class GeminiAdapter:
    provider = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = "gemini-2.5-flash",
        client: Any = None,
    ) -> None:
        self.model_name = model_name
        self._uses_sdk = client is None
        if client is None:
            try:
                from google import genai
            except ImportError as error:
                raise AIAdapterError(
                    "Install the ai extra to use GeminiAdapter"
                ) from error
            key = api_key or os.environ.get("GEMINI_API_KEY")
            try:
                from google.genai import types as genai_types

                # without a time limit one stalled connection would hold the worker thread forever
                client = genai.Client(api_key=key, http_options=genai_types.HttpOptions(timeout=30_000))
            except (ImportError, AttributeError, TypeError):
                client = genai.Client(api_key=key)
        self.client = client

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        contents: list[Any] = [_prompt_for(payload)]
        for media in payload.get("media", []):
            if isinstance(media, dict) and isinstance(media.get("content"), bytes):
                try:
                    from google.genai import types

                    contents.append(
                        types.Part.from_bytes(
                            data=media["content"],
                            mime_type=media.get("content_type", "image/jpeg"),
                        )
                    )
                except ImportError as error:
                    if self._uses_sdk:
                        raise AIAdapterError(
                            "Gemini media support requires google-genai"
                        ) from error
                    contents.append(
                        {
                            "inline_data": {
                                "mime_type": media.get("content_type", "image/jpeg"),
                                "data": media["content"],
                            }
                        }
                    )
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config={"response_mime_type": "application/json"},
            )
            parsed = json.loads(response.text)
        except Exception as error:
            code = getattr(error, "code", None)
            if code == 429:
                raise AIAdapterError("Gemini quota or rate limit reached. Try again later.") from error
            if isinstance(error, json.JSONDecodeError):
                raise AIAdapterError("Gemini returned an answer that was not valid JSON") from error
            raise AIAdapterError(f"Gemini analysis request failed{f' ({code})' if code else ''}") from error
        return validate_analysis_output(parsed)


class OpenWeightHTTPAdapter:
    """Adapter for OpenAI-compatible servers hosting an open-weight vision model."""

    provider = "open_weight"

    def __init__(
        self,
        endpoint: str,
        model_name: str,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        opener: Any = urlopen,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.opener = opener

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        content: list[dict[str, Any]] = [{"type": "text", "text": _prompt_for(payload)}]
        for media in payload.get("media", []):
            if isinstance(media, dict) and isinstance(media.get("content"), bytes):
                encoded = base64.b64encode(media["content"]).decode("ascii")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media.get('content_type', 'image/jpeg')};base64,{encoded}"
                        },
                    }
                )
        body = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(
            f"{self.endpoint}/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout_seconds) as response:
                provider_response = json.loads(response.read().decode("utf-8"))
            content_value = provider_response["choices"][0]["message"]["content"]
            if isinstance(content_value, dict):
                parsed = content_value
            else:
                parsed = json.loads(content_value)
        except Exception as error:
            raise AIAdapterError("Open-weight analysis request failed") from error
        return validate_analysis_output(parsed)


def create_analysis_adapter_from_env() -> AnalysisAdapter:
    provider = os.getenv("CIVICLOOP_AI_PROVIDER", "gemini").lower()
    if provider == "gemini":
        return GeminiAdapter(
            api_key=os.getenv("GEMINI_API_KEY"),
            model_name=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        )
    if provider in {"open_weight", "open-weight"}:
        endpoint = os.getenv("OPEN_WEIGHT_ENDPOINT")
        model_name = os.getenv("OPEN_WEIGHT_MODEL")
        if not endpoint or not model_name:
            raise AIAdapterError(
                "OPEN_WEIGHT_ENDPOINT and OPEN_WEIGHT_MODEL are required"
            )
        return OpenWeightHTTPAdapter(
            endpoint, model_name, os.getenv("OPEN_WEIGHT_API_KEY")
        )
    raise AIAdapterError(f"Unsupported AI provider: {provider}")

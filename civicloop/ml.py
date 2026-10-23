from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class ModelRunner(Protocol):
    def predict(self, features: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ModelMetadata:
    name: str
    version: str
    provider: str
    task: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RegisteredModel:
    metadata: ModelMetadata
    runner: ModelRunner


class ModelRegistry:
    def __init__(self) -> None:
        self._models: dict[tuple[str, str], RegisteredModel] = {}

    def register(self, metadata: ModelMetadata, runner: ModelRunner) -> RegisteredModel:
        key = (metadata.name, metadata.version)
        if key in self._models:
            raise ValueError(f"Model version already registered: {metadata.name}:{metadata.version}")
        registered = RegisteredModel(metadata, runner)
        self._models[key] = registered
        return registered

    def get(self, name: str, version: str) -> RegisteredModel:
        try:
            return self._models[(name, version)]
        except KeyError as error:
            raise LookupError(f"Model version not found: {name}:{version}") from error

    def list(self) -> list[ModelMetadata]:
        return [model.metadata for model in sorted(self._models.values(), key=lambda item: (item.metadata.name, item.metadata.version))]
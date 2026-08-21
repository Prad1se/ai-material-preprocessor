from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..models import Operation


@dataclass(frozen=True)
class PreviewRequest:
    sources: tuple[Path, ...]
    operation: Operation
    output_root: Path
    parameters: Mapping[str, object] = field(default_factory=dict)
    tool_paths: Mapping[str, str] = field(default_factory=dict)
    manual_location: str = ""


class PreviewProvider(Protocol):
    def build(self, request: PreviewRequest) -> object: ...


class UnregisteredPreviewProviderError(ValueError):
    def __init__(self, operation: Operation) -> None:
        super().__init__(f"No preview provider is registered for operation {operation.name}.")
        self.operation = operation


class PreviewProviderRegistry:
    def __init__(
        self,
        providers: Mapping[Operation, PreviewProvider] | None = None,
    ) -> None:
        self._providers: dict[Operation, PreviewProvider] = dict(providers or {})

    def register(self, operations: Iterable[Operation], provider: PreviewProvider) -> None:
        for operation in operations:
            if operation in self._providers:
                raise ValueError(f"A preview provider is already registered for {operation.name}.")
            self._providers[operation] = provider

    def build(self, request: PreviewRequest) -> object:
        provider = self._providers.get(request.operation)
        if provider is None:
            raise UnregisteredPreviewProviderError(request.operation)
        return provider.build(request)

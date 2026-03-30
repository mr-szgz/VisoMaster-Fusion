"""Reference-only plugin contract for remote import providers.

This file is intentionally standalone and not integrated into the application.
It models business-level behavior for any remote source (API, website, cloud drive,
rclone target, etc.) without exposing transport-specific details.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class MediaKind(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class EntryKind(str, Enum):
    MEDIA = "media"
    COLLECTION = "collection"


@dataclass(frozen=True)
class ProviderSettings:
    """Opaque provider settings stored by the host app.

    The contract intentionally does not prescribe endpoint/query/auth fields.
    Each provider interprets this mapping as needed.
    """

    values: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowseRequest:
    """High-level browse request for searching or navigating remote content."""

    query: str | None = None
    scope_token: str | None = None
    media_kinds: frozenset[MediaKind] = field(
        default_factory=lambda: frozenset({MediaKind.IMAGE, MediaKind.VIDEO})
    )
    cursor: str | None = None
    page_size: int = 50


@dataclass(frozen=True)
class RemoteEntry:
    """One item shown in the import browser UI."""

    entry_id: str
    kind: EntryKind
    title: str
    media_kind: MediaKind | None = None
    browse_token: str | None = None
    preview_uri: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowseResult:
    entries: Sequence[RemoteEntry]
    next_cursor: str | None = None


@dataclass(frozen=True)
class ImportCandidate:
    """Canonical media reference that the host can import."""

    source_id: str
    media_kind: MediaKind
    display_name: str
    content_uri: str
    preview_uri: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class ProviderContractError(Exception):
    """Raised when provider settings/requests cannot be handled."""


class RemoteImportProvider(ABC):
    """Business-level contract that all remote providers implement."""

    @classmethod
    @abstractmethod
    def provider_id(cls) -> str:
        """Stable plugin id (for example: 'youtube', 'gdrive', 'stashapp')."""

    @classmethod
    def display_name(cls) -> str:
        """Human-friendly provider label for UI."""
        return cls.provider_id()

    def validate_settings(self, settings: ProviderSettings) -> None:
        """Optional preflight validation. Override when provider needs it."""

    @abstractmethod
    def browse(
        self,
        settings: ProviderSettings,
        request: BrowseRequest,
    ) -> BrowseResult:
        """Return browser entries (media and/or collections) for the requested scope."""

    @abstractmethod
    def materialize_for_import(
        self,
        settings: ProviderSettings,
        selected_entries: Sequence[RemoteEntry],
    ) -> Sequence[ImportCandidate]:
        """Convert user-selected browser entries into importable media references."""

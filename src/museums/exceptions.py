"""Domain exception hierarchy for the museums application."""

from __future__ import annotations

from museums.enums.external_source import ExternalSource


class DomainError(Exception):
    """Base class for all domain exceptions."""


class NotFoundError(DomainError):
    """Raised when a requested entity does not exist."""

    def __init__(self, entity: str, identifier: str | int) -> None:
        self.entity = entity
        self.identifier = identifier
        super().__init__(f"{entity} '{identifier}' not found")


class RefreshCooldownError(DomainError):
    """Raised when a refresh is attempted before the cooldown period expires."""

    def __init__(self, remaining_seconds: int) -> None:
        self.retry_after_seconds = remaining_seconds
        super().__init__(f"Refresh cooldown active — retry after {remaining_seconds}s")


class ExternalServiceError(DomainError):
    """Base class for external service failures."""

    service_name: ExternalSource

    def __init__(self, message: str) -> None:
        super().__init__(message)


class MediaWikiUnavailableError(ExternalServiceError):
    """Raised when the MediaWiki API is unreachable or returns 5xx."""

    service_name = ExternalSource.MEDIAWIKI


class WikidataUnavailableError(ExternalServiceError):
    """Raised when the Wikidata SPARQL endpoint is unreachable or returns 5xx."""

    service_name = ExternalSource.WIKIDATA


class ExternalDataParseError(DomainError):
    """Raised when an external API response has an unexpected shape."""

    def __init__(self, source: ExternalSource, detail: str) -> None:
        self.source = source
        self.detail = detail
        super().__init__(f"Failed to parse response from '{source}': {detail}")


class InsufficientDataError(DomainError):
    """Raised when there are fewer than 5 harmonized rows to fit the regression."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Insufficient data for regression: {reason}")

"""Tests for src/museums/exceptions.py."""

from __future__ import annotations

from museums.exceptions import (
    ExternalServiceError,
    MediaWikiUnavailableError,
    NotFoundError,
    RefreshCooldownError,
    WikidataUnavailableError,
)


def test_refresh_cooldown_error_exposes_retry_after_seconds() -> None:
    """RefreshCooldownError must expose retry_after_seconds for the handler."""
    exc = RefreshCooldownError(remaining_seconds=3600)

    assert exc.retry_after_seconds == 3600


def test_not_found_error_includes_entity_and_identifier_in_message() -> None:
    """str(NotFoundError) must include both entity name and identifier."""
    exc = NotFoundError(entity="Museum", identifier="Q12345")

    message = str(exc)

    assert "Museum" in message
    assert "Q12345" in message


def test_external_service_error_stores_service_name() -> None:
    """ExternalServiceError subclasses must carry the expected service_name."""
    mediawiki_exc = MediaWikiUnavailableError("connection refused")
    wikidata_exc = WikidataUnavailableError("timeout")

    assert mediawiki_exc.service_name == "mediawiki"
    assert wikidata_exc.service_name == "wikidata"
    assert isinstance(mediawiki_exc, ExternalServiceError)
    assert isinstance(wikidata_exc, ExternalServiceError)

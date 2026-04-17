"""ExternalSource enum — identifies which external API is the source of an error."""

from __future__ import annotations

from enum import StrEnum


class ExternalSource(StrEnum):
    MEDIAWIKI = "mediawiki"
    WIKIDATA = "wikidata"

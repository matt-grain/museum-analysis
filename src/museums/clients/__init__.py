"""Clients package — re-exports external API clients and their DTOs."""

from museums.clients.mediawiki_client import MediaWikiClient, MuseumListEntry
from museums.clients.wikidata_client import (
    MuseumEnrichment,
    PopulationPoint,
    VisitorPoint,
    WikidataClient,
)

__all__ = [
    "MediaWikiClient",
    "MuseumEnrichment",
    "MuseumListEntry",
    "PopulationPoint",
    "VisitorPoint",
    "WikidataClient",
]

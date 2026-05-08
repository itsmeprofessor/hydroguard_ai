"""
HydroGuard-AI — Retrospective Event Scraper (stub)
====================================================
Pluggable interface for fetching verified flood/cloudburst event labels
from external sources (NDMA Pakistan, PMD, news scrapers).

Stage 3 implementation: stub returning empty list.
Future: implement NDMA/PMD API integration here.
The LabelEngine accepts this interface; swap the stub for a real
implementation when official data sources become available.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

logger = logging.getLogger(__name__)


class RetroEventScraper:
    """
    Stub retrospective event scraper.

    Future implementation will:
    1. Query NDMA Pakistan flood event database
    2. Query PMD weather alerts archive
    3. Parse verified event records into (date, LabelOutput) tuples

    Currently returns empty list for all queries.
    """

    def __init__(
        self,
        ndma_api_url: Optional[str] = None,
        pmd_api_url:  Optional[str] = None,
    ):
        self._ndma_url = ndma_api_url
        self._pmd_url  = pmd_api_url

    async def fetch_events(
        self,
        city_slug:  str,
        start_date: date,
        end_date:   date,
    ) -> list:
        """
        Fetch verified flood/cloudburst events for a city in a date range.

        Returns list of (date, LabelOutput) tuples.
        Empty list in current stub implementation.
        """
        logger.debug(
            "RetroEventScraper.fetch_events: stub called for %s [%s -> %s]",
            city_slug, start_date, end_date,
        )
        return []

    @property
    def is_configured(self) -> bool:
        """True when real API credentials are configured."""
        return False

    @property
    def source_name(self) -> str:
        return "stub"

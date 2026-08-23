"""News providers — RSS ingestion (Yahoo Finance headlines)."""

from providers.news.rss import classify_relevance, fetch_symbol_headlines, parse_rss

__all__ = ["classify_relevance", "fetch_symbol_headlines", "parse_rss"]

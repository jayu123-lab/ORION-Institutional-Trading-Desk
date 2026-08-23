"""Tests for providers.news.rss — pure parsing logic (no network)."""

from datetime import UTC, datetime

from providers.news.rss import classify_relevance, parse_pub_date, parse_rss

VALID_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Yahoo Finance</title>
  <item>
    <title>Fed signals rate decision will hinge on CPI inflation data</title>
    <link>https://finance.yahoo.com/news/fed-1</link>
    <pubDate>Sat, 22 Aug 2026 22:20:00 +0000</pubDate>
    <description>Central bank guidance ahead of Jackson Hole.</description>
  </item>
  <item>
    <title>Apple shares steady after buyback announcement</title>
    <link>https://finance.yahoo.com/news/aapl-2</link>
    <pubDate>Sat, 22 Aug 2026 19:59:00 +0000</pubDate>
  </item>
  <item>
    <description>no title here</description>
  </item>
</channel></rss>"""


class TestParseRss:
    def test_parses_valid_feed(self):
        items = parse_rss(VALID_RSS)
        assert len(items) == 2  # item without title is skipped
        first = items[0]
        assert "Fed" in first.title
        assert first.link == "https://finance.yahoo.com/news/fed-1"
        assert first.description == "Central bank guidance ahead of Jackson Hole."
        assert first.published_at.year == 2026

    def test_pubdate_is_tz_aware_utc(self):
        items = parse_rss(VALID_RSS)
        assert items[0].published_at.tzinfo is not None

    def test_item_without_description_ok(self):
        items = parse_rss(VALID_RSS)
        assert items[1].description is None

    def test_malformed_xml_returns_empty(self):
        assert parse_rss("<rss><channel><item>") == []

    def test_empty_string_returns_empty(self):
        assert parse_rss("") == []

    def test_non_rss_xml_returns_empty(self):
        assert parse_rss("<html><body>hi</body></html>") == []


class TestClassifyRelevance:
    def test_high_macro_keywords(self):
        assert classify_relevance("Fed holds rates amid sticky inflation") == "HIGH"
        assert classify_relevance("NFP jobs report smashes estimates") == "HIGH"

    def test_noise_keywords(self):
        assert classify_relevance("Poll: who wins the election?") == "NOISE"

    def test_default_medium(self):
        assert classify_relevance("Apple opens new store in Madrid") == "MEDIUM"


class TestParsePubDate:
    def test_rfc822_with_offset(self):
        dt = parse_pub_date("Sat, 22 Aug 2026 19:59:00 -0400")
        assert dt.tzinfo is not None
        assert dt.utcoffset().total_seconds() == -4 * 3600

    def test_garbage_falls_back_to_now(self):
        before = datetime.now(UTC)
        dt = parse_pub_date("not-a-date")
        after = datetime.now(UTC)
        assert before <= dt.replace(tzinfo=UTC) <= after

    def test_none_falls_back_to_now(self):
        assert parse_pub_date(None).tzinfo is not None

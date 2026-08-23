"""Tests for provider tier hierarchy (PRIORITY 12)."""

from core.market_data.tiers import (
    DEFAULT_TIERS,
    FeedGrade,
    FeedTier,
    load_tiers,
    status_from_grade,
)


class TestDefaults:
    def test_rtds_is_primary_institutional(self):
        assert DEFAULT_TIERS["polymarket-rtds"] == (FeedTier.PRIMARY, FeedGrade.INSTITUTIONAL_LIVE)

    def test_yahoo_not_institutional(self):
        tier, grade = DEFAULT_TIERS["yahoo"]
        assert tier == FeedTier.SECONDARY
        assert grade != FeedGrade.INSTITUTIONAL_LIVE

    def test_simulated_is_fallback(self):
        assert DEFAULT_TIERS["simulated"][0] == FeedTier.FALLBACK

    def test_status_mapping(self):
        assert status_from_grade(FeedGrade.INSTITUTIONAL_LIVE) == "LIVE"
        assert status_from_grade(FeedGrade.UNOFFICIAL) == "DELAYED"
        assert status_from_grade(FeedGrade.SIMULATED) == "SIMULATED"
        assert status_from_grade(FeedGrade.DELAYED) == "DELAYED"


class TestConfigLoad:
    def test_missing_config_returns_defaults(self, tmp_path):
        tiers = load_tiers(str(tmp_path / "nope.json"))
        assert tiers["yahoo"] == DEFAULT_TIERS["yahoo"]

    def test_config_overrides_defaults(self, tmp_path):
        cfg = tmp_path / "tiers.json"
        cfg.write_text(
            '{"yahoo": ["FALLBACK_FEED", "UNOFFICIAL"], "cftc": ["SECONDARY_FEED", "DELAYED"]}',
            encoding="utf-8",
        )
        tiers = load_tiers(str(cfg))
        assert tiers["yahoo"] == (FeedTier.FALLBACK, FeedGrade.UNOFFICIAL)
        assert tiers["polymarket-rtds"] == DEFAULT_TIERS["polymarket-rtds"]

    def test_invalid_entries_ignored(self, tmp_path):
        cfg = tmp_path / "tiers.json"
        cfg.write_text('{"unknown-provider": ["PRIMARY_FEED", "LIVE"], "yahoo": ["BAD", "BAD"]}', encoding="utf-8")
        tiers = load_tiers(str(cfg))
        assert "unknown-provider" not in tiers
        assert tiers["yahoo"] == DEFAULT_TIERS["yahoo"]  # invalid entry → default kept

    def test_malformed_json_falls_back(self, tmp_path):
        cfg = tmp_path / "broken.json"
        cfg.write_text("{not json", encoding="utf-8")
        assert load_tiers(str(cfg))["yahoo"] == DEFAULT_TIERS["yahoo"]

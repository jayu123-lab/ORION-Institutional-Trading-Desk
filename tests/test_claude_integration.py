import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from core.agents.claude_integration import ClaudeDecisionAnalyzer


class TestClaudeDecisionAnalyzer:
    """Test Claude API integration."""

    def test_initialization(self):
        """Test analyzer initializes correctly."""
        analyzer = ClaudeDecisionAnalyzer(api_key="test-key")
        assert analyzer.api_key == "test-key"
        assert analyzer.model == "claude-opus-5"
        assert analyzer.base_url == "https://api.anthropic.com"

    def test_is_configured(self):
        """Test configuration check."""
        analyzer_with_key = ClaudeDecisionAnalyzer(api_key="test-key")
        assert analyzer_with_key.is_configured()

        analyzer_no_key = ClaudeDecisionAnalyzer(api_key=None)
        assert not analyzer_no_key.is_configured()

    @pytest.mark.asyncio
    async def test_analyze_without_api_key(self):
        """Test analysis gracefully fails without API key."""
        analyzer = ClaudeDecisionAnalyzer(api_key=None)

        result = await analyzer.analyze_market_context(
            symbol="BTC",
            current_price=95000.0,
            bid_ask={"bid": 94999.0, "ask": 95001.0},
            recent_volume={"volume_1h": 1234.5, "volume_24h": 45678.9},
            market_regime="TRENDING",
            macro_context="Fed on hold",
            data_quality="HIGH",
        )

        assert result["status"] == "skipped"
        assert "reason" in result

    @pytest.mark.asyncio
    async def test_analyze_with_api_error(self):
        """Test handling of API errors."""
        analyzer = ClaudeDecisionAnalyzer(api_key="test-key")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await analyzer.analyze_market_context(
                symbol="BTC",
                current_price=95000.0,
                bid_ask={"bid": 94999.0, "ask": 95001.0},
                recent_volume={"volume_1h": 1234.5, "volume_24h": 45678.9},
                market_regime="TRENDING",
                macro_context="Fed on hold",
                data_quality="HIGH",
            )

            assert result["status"] == "error"
            assert "401" in result["reason"]

    @pytest.mark.asyncio
    async def test_analyze_successful_response(self):
        """Test successful API response."""
        analyzer = ClaudeDecisionAnalyzer(api_key="test-key")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "content": [{"text": "BTC showing institutional accumulation patterns"}]
            }
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await analyzer.analyze_market_context(
                symbol="BTC",
                current_price=95000.0,
                bid_ask={"bid": 94999.0, "ask": 95001.0},
                recent_volume={"volume_1h": 1234.5, "volume_24h": 45678.9},
                market_regime="TRENDING",
                macro_context="Fed on hold",
                data_quality="HIGH",
            )

            assert result["status"] == "success"
            assert result["symbol"] == "BTC"
            assert "accumulation" in result["analysis"]

    @pytest.mark.asyncio
    async def test_generate_trade_decision(self):
        """Test trade decision generation."""
        analyzer = ClaudeDecisionAnalyzer(api_key="test-key")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "content": [{"text": "LONG with 2.1 R:R, stop at 93500, target at 98000"}]
            }
            mock_client.post.return_value = mock_response
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await analyzer.generate_trade_decision(
                symbol="BTC",
                analysis_context="Strong institutional accumulation",
                current_positions={"BTC": 0.0},
                risk_limits={
                    "max_daily_loss": 1000,
                    "risk_reward_ratio": 2.0,
                    "position_limit": 1.0,
                },
            )

            assert result["status"] == "success"
            assert "LONG" in result["decision"]
            assert "2.1 R:R" in result["decision"]

    @pytest.mark.asyncio
    async def test_http_exception_handling(self):
        """Test handling of HTTP exceptions."""
        analyzer = ClaudeDecisionAnalyzer(api_key="test-key")

        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.post.side_effect = Exception("Connection timeout")
            mock_client_class.return_value.__aenter__.return_value = mock_client

            result = await analyzer.analyze_market_context(
                symbol="BTC",
                current_price=95000.0,
                bid_ask={"bid": 94999.0, "ask": 95001.0},
                recent_volume={"volume_1h": 1234.5, "volume_24h": 45678.9},
                market_regime="TRENDING",
                macro_context="Fed on hold",
                data_quality="HIGH",
            )

            assert result["status"] == "error"
            assert "Connection timeout" in result["reason"]

    def test_system_prompt_structure(self):
        """Test system prompts are well-formed."""
        analyzer = ClaudeDecisionAnalyzer(api_key="test-key")

        sys_prompt = analyzer._get_system_prompt()
        assert "institutional" in sys_prompt.lower()
        assert "analysis" in sys_prompt.lower()

        decision_prompt = analyzer._get_decision_system_prompt()
        assert "risk" in decision_prompt.lower()
        assert "stop loss" in decision_prompt.lower()

    def test_analysis_prompt_includes_required_fields(self):
        """Test analysis prompt includes all required fields."""
        analyzer = ClaudeDecisionAnalyzer(api_key="test-key")

        prompt = analyzer._build_analysis_prompt(
            symbol="BTC",
            current_price=95000.0,
            bid_ask={"bid": 94999.0, "ask": 95001.0},
            recent_volume={"volume_1h": 1234.5},
            market_regime="TRENDING",
            macro_context="Fed pause",
            data_quality="HIGH",
        )

        assert "BTC" in prompt
        assert "95000" in prompt
        assert "TRENDING" in prompt
        assert "Fed pause" in prompt

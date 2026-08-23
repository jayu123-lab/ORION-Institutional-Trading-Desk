"""Focused checks for the permanent start screen and Spanish UX contract."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
WEB = ROOT / "apps" / "web"


def test_start_screen_and_global_navigation_contract():
    layout = (WEB / "app" / "layout.tsx").read_text(encoding="utf-8")
    start = (WEB / "app" / "start" / "page.tsx").read_text(encoding="utf-8")
    shell = (WEB / "components" / "AppShell.tsx").read_text(encoding="utf-8")
    assert 'href="/start"' in layout or 'href="/start"' in shell
    assert '["command_center", "/command"]' in shell
    assert "orion:open-cio" in shell and "/api/v1/chat" in shell
    assert "ORION INITIALIZING" in start
    assert '"/health"' in start and '"/api/v1/cio/agents"' in start


def test_spanish_catalog_is_default_and_preserves_technical_tokens():
    source = (WEB / "lib" / "i18n.ts").read_text(encoding="utf-8")
    assert 'DEFAULT_LANG: LangCode = "es"' in source
    assert '"XAUUSD"' not in source  # ticker values stay outside UI translation
    from core.translation.service import translate_text

    result = translate_text("Liquidity Sweep XAUUSD at 2300.50", "es", "en")
    assert "XAUUSD" in result.text and "2300.50" in result.text
    assert "barrido de liquidez" in result.text


def test_i18n_api_contract(client):
    catalogs = client.get("/api/v1/i18n/catalogs")
    assert catalogs.status_code == 200
    payload = catalogs.json()
    assert payload["ui_language_default"] == "es"
    assert {item["code"] for item in payload["languages"]} == {"es", "en", "fr", "de", "it", "pt"}


@pytest.fixture(name="client")
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ORION_TEST_DATABASE_URL", f"sqlite:///{tmp_path / 'ux.db'}")
    monkeypatch.setenv("ORION_EMBEDDED_DATA", "false")
    from core.config import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from apps.api.main import app
    from core.memory.database import init_db

    init_db()
    with TestClient(app) as test_client:
        yield test_client

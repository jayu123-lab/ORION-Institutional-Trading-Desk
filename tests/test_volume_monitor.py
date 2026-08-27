"""Tests for volume monitor."""
import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from core.volume_monitor.volume_engine import VolumeSnapshot, VolumeMonitor


def test_volume_snapshot_creation():
    """Test creating a volume snapshot."""
    snapshot = VolumeSnapshot(
        symbol="SPY",
        volume=Decimal("50000000"),
        price=Decimal("450.25"),
        timestamp=datetime.utcnow(),
        source="yahoo",
    )
    
    assert snapshot.symbol == "SPY"
    assert snapshot.volume == Decimal("50000000")
    assert snapshot.price == Decimal("450.25")
    assert snapshot.notional > 0


def test_volume_monitor_storage():
    """Test storing and retrieving volume snapshots."""
    monitor = VolumeMonitor()
    
    snapshot = VolumeSnapshot(
        symbol="QQQ",
        volume=Decimal("30000000"),
        price=Decimal("375.50"),
        timestamp=datetime.utcnow(),
        source="yahoo",
    )
    
    monitor._store_snapshot("QQQ", snapshot)
    retrieved = monitor.get_latest_volume("QQQ")
    
    assert retrieved is not None
    assert retrieved.symbol == "QQQ"
    assert retrieved.volume == Decimal("30000000")


def test_volume_history():
    """Test retrieving volume history."""
    monitor = VolumeMonitor()
    now = datetime.utcnow()
    
    for i in range(5):
        snapshot = VolumeSnapshot(
            symbol="GLD",
            volume=Decimal("1000000") * (i + 1),
            price=Decimal("200.00"),
            timestamp=now - timedelta(hours=i),
            source="yahoo",
        )
        monitor._store_snapshot("GLD", snapshot)
    
    history = monitor.get_volume_history("GLD", hours=24)
    assert len(history) == 5


def test_volume_spike_detection():
    """Test volume spike detection."""
    monitor = VolumeMonitor()
    now = datetime.utcnow()
    
    # Add baseline volumes
    for i in range(5):
        snapshot = VolumeSnapshot(
            symbol="TEST",
            volume=Decimal("1000000"),
            price=Decimal("100.00"),
            timestamp=now - timedelta(hours=i),
            source="yahoo",
        )
        monitor._store_snapshot("TEST", snapshot)
    
    # Add spike
    spike = VolumeSnapshot(
        symbol="TEST",
        volume=Decimal("5000000"),  # 5x average
        price=Decimal("100.00"),
        timestamp=now,
        source="yahoo",
    )
    monitor._store_snapshot("TEST", spike)
    
    assert monitor.is_volume_spike("TEST", threshold=1.5)


def test_monitored_symbols():
    """Test tracking monitored symbols."""
    monitor = VolumeMonitor()
    
    for symbol in ["SPY", "QQQ", "GLD"]:
        snapshot = VolumeSnapshot(
            symbol=symbol,
            volume=Decimal("1000000"),
            price=Decimal("100.00"),
            timestamp=datetime.utcnow(),
            source="yahoo",
        )
        monitor._store_snapshot(symbol, snapshot)
    
    symbols = monitor.get_monitored_symbols()
    assert set(symbols) == {"SPY", "QQQ", "GLD"}


def test_volume_report_format():
    """Test volume report formatting."""
    monitor = VolumeMonitor()
    
    snapshot = VolumeSnapshot(
        symbol="BTC",
        volume=Decimal("25000000000"),
        price=Decimal("45000.00"),
        timestamp=datetime.utcnow(),
        source="coingecko",
    )
    monitor._store_snapshot("BTC", snapshot)
    
    report = monitor.format_volume_report("BTC")
    assert "BTC" in report
    assert "Volume" in report
    assert "coingecko" in report

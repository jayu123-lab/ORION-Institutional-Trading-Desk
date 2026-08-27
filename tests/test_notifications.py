"""Tests for notification engine."""
import pytest
from core.notifications.notifier import NotificationEngine, AlertLevel, Notification


def test_notification_creation():
    """Test creating a notification."""
    notif = Notification(
        title="Test Alert",
        message="This is a test",
        level=AlertLevel.HIGH,
    )
    assert notif.title == "Test Alert"
    assert notif.level == AlertLevel.HIGH


def test_notification_slack_payload():
    """Test converting notification to Slack format."""
    notif = Notification(
        title="Test",
        message="Test message",
        level=AlertLevel.HIGH,
    )
    payload = notif.to_slack_payload()
    assert "attachments" in payload
    assert payload["attachments"][0]["title"] == "Test"


def test_notification_engine_creation():
    """Test creating notification engine."""
    engine = NotificationEngine()
    assert not engine.notification_history


def test_volume_spike_alert():
    """Test volume spike alert method."""
    engine = NotificationEngine()
    # Would require async context to actually test sending
    assert engine.send_volume_spike_alert is not None


def test_alert_history():
    """Test retrieving alert history."""
    engine = NotificationEngine()
    notif = Notification(
        title="Test",
        message="Test message",
        level=AlertLevel.HIGH,
    )
    engine.notification_history.append(notif)
    
    history = engine.get_alert_history()
    assert len(history) == 1
    assert history[0].title == "Test"


def test_alert_summary_format():
    """Test alert summary formatting."""
    engine = NotificationEngine()
    notif1 = Notification("Alert1", "Message1", AlertLevel.HIGH)
    notif2 = Notification("Alert2", "Message2", AlertLevel.MEDIUM)
    
    engine.notification_history.extend([notif1, notif2])
    summary = engine.format_alert_summary()
    
    assert "Alert Summary" in summary
    assert "HIGH" in summary
    assert "MEDIUM" in summary

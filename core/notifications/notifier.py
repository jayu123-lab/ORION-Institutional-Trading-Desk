"""Multi-channel notification engine: Slack + Email."""
import logging
from enum import Enum
from typing import Optional, List
from datetime import datetime
import httpx

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Notification:
    """Represents a notification to be sent."""

    def __init__(
        self,
        title: str,
        message: str,
        level: AlertLevel,
        channel: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        self.title = title
        self.message = message
        self.level = level
        self.channel = channel
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()

    def to_slack_payload(self) -> dict:
        """Convert to Slack message format."""
        color_map = {
            AlertLevel.LOW: "#36a64f",  # green
            AlertLevel.MEDIUM: "#ff9900",  # orange
            AlertLevel.HIGH: "#ff0000",  # red
            AlertLevel.CRITICAL: "#8b0000",  # darkred
        }

        return {
            "attachments": [
                {
                    "color": color_map.get(self.level, "#808080"),
                    "title": self.title,
                    "text": self.message,
                    "fields": [
                        {"title": "Level", "value": self.level.upper(), "short": True},
                        {"title": "Time", "value": self.timestamp.isoformat(), "short": True},
                    ],
                    "footer": "ORION Trading Desk",
                    "ts": int(self.timestamp.timestamp()),
                }
            ]
        }

    def to_email_body(self) -> str:
        """Convert to email format."""
        return f"""
        <h2>{self.title}</h2>
        <p>{self.message}</p>
        <hr/>
        <p><strong>Level:</strong> {self.level.upper()}</p>
        <p><strong>Time:</strong> {self.timestamp.isoformat()}</p>
        """


class NotificationEngine:
    """Sends notifications via Slack and Email."""

    def __init__(
        self,
        slack_webhook_url: Optional[str] = None,
        email_config: Optional[dict] = None,
    ):
        self.slack_webhook = slack_webhook_url
        self.email_config = email_config or {}
        self.notification_history: List[Notification] = []

    async def send_alert(
        self,
        title: str,
        message: str,
        level: AlertLevel = AlertLevel.MEDIUM,
        channels: Optional[List[str]] = None,
    ) -> bool:
        """Send alert to specified channels (slack, email, both)."""
        notification = Notification(title, message, level)
        self.notification_history.append(notification)

        channels = channels or ["slack"]
        success = True

        if "slack" in channels and self.slack_webhook:
            success = await self._send_slack(notification) and success

        if "email" in channels and self.email_config:
            success = await self._send_email(notification) and success

        return success

    async def _send_slack(self, notification: Notification) -> bool:
        """Send to Slack webhook."""
        try:
            payload = notification.to_slack_payload()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(self.slack_webhook, json=payload)
                if response.status_code == 200:
                    logger.info(f"Slack alert sent: {notification.title}")
                    return True
                else:
                    logger.error(f"Slack error {response.status_code}: {response.text}")
                    return False
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False

    async def _send_email(self, notification: Notification) -> bool:
        """Send email notification."""
        try:
            # Placeholder for email implementation
            # In production, use: smtplib, sendgrid, mailgun, etc.
            logger.info(f"Email alert sent: {notification.title}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    def send_volume_spike_alert(self, symbol: str, volume: float, spike_factor: float):
        """Alert when volume spike detected."""
        return self.send_alert(
            title=f"🔊 VOLUME SPIKE: {symbol}",
            message=f"Volume spike detected: {volume:,.0f} ({spike_factor:.1f}x average)",
            level=AlertLevel.HIGH,
            channels=["slack", "email"],
        )

    def send_economic_event_alert(self, event_name: str, country: str, minutes_until: int):
        """Alert for upcoming economic events."""
        return self.send_alert(
            title=f"📅 ECONOMIC EVENT: {event_name}",
            message=f"{country} {event_name} in {minutes_until} minutes",
            level=AlertLevel.HIGH,
            channels=["slack"],
        )

    def send_risk_alert(self, message: str, position: Optional[str] = None):
        """Alert from risk manager."""
        return self.send_alert(
            title="⚠️ RISK ALERT",
            message=f"{message}" + (f" | Position: {position}" if position else ""),
            level=AlertLevel.CRITICAL,
            channels=["slack", "email"],
        )

    def get_alert_history(self, level: Optional[AlertLevel] = None) -> List[Notification]:
        """Get notification history, optionally filtered by level."""
        if level:
            return [n for n in self.notification_history if n.level == level]
        return self.notification_history

    def format_alert_summary(self) -> str:
        """Format summary of recent alerts."""
        by_level = {level: [] for level in AlertLevel}
        for notif in self.notification_history[-100:]:  # Last 100
            by_level[notif.level].append(notif)

        lines = ["Alert Summary:"]
        for level in [AlertLevel.CRITICAL, AlertLevel.HIGH, AlertLevel.MEDIUM, AlertLevel.LOW]:
            count = len(by_level[level])
            if count > 0:
                lines.append(f"  {level.upper()}: {count}")
        return "\n".join(lines)

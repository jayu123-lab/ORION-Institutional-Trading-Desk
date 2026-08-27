"""Dashboard widgets and components for ORION Command Center."""
import logging
from enum import Enum
from typing import List, Dict, Optional, Any
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class WidgetType(str, Enum):
    METRIC = "metric"
    CHART = "chart"
    TABLE = "table"
    ALERT = "alert"
    HEATMAP = "heatmap"
    GAUGE = "gauge"


@dataclass
class DashboardWidget:
    """Represents a dashboard widget."""

    id: str
    type: WidgetType
    title: str
    data: Dict[str, Any]
    refresh_interval: int = 60  # seconds
    position: tuple = (0, 0)  # (row, col)
    size: tuple = (1, 1)  # (height, width)

    def to_json(self) -> dict:
        """Convert to JSON for API response."""
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "data": self.data,
            "refresh_interval": self.refresh_interval,
            "position": self.position,
            "size": self.size,
            "timestamp": datetime.utcnow().isoformat(),
        }


class Dashboard:
    """Main dashboard orchestrator."""

    def __init__(self, name: str = "ORION Command Center"):
        self.name = name
        self.widgets: List[DashboardWidget] = []
        self.last_update = None

    def add_widget(self, widget: DashboardWidget) -> None:
        """Add widget to dashboard."""
        self.widgets.append(widget)
        logger.info(f"Added widget: {widget.id}")

    def add_metric_widget(
        self,
        widget_id: str,
        title: str,
        value: Any,
        unit: str = "",
        status: str = "normal",
    ) -> None:
        """Add metric widget (KPI, stat, etc.)."""
        widget = DashboardWidget(
            id=widget_id,
            type=WidgetType.METRIC,
            title=title,
            data={
                "value": value,
                "unit": unit,
                "status": status,  # normal, warning, critical
            },
        )
        self.add_widget(widget)

    def add_table_widget(
        self,
        widget_id: str,
        title: str,
        headers: List[str],
        rows: List[List[Any]],
    ) -> None:
        """Add table widget."""
        widget = DashboardWidget(
            id=widget_id,
            type=WidgetType.TABLE,
            title=title,
            data={
                "headers": headers,
                "rows": rows,
            },
        )
        self.add_widget(widget)

    def add_alert_widget(
        self,
        widget_id: str,
        title: str,
        message: str,
        level: str = "info",
    ) -> None:
        """Add alert widget."""
        widget = DashboardWidget(
            id=widget_id,
            type=WidgetType.ALERT,
            title=title,
            data={
                "message": message,
                "level": level,  # info, warning, error, success
            },
        )
        self.add_widget(widget)

    def add_gauge_widget(
        self,
        widget_id: str,
        title: str,
        value: float,
        min_val: float = 0,
        max_val: float = 100,
        unit: str = "",
    ) -> None:
        """Add gauge widget (speedometer style)."""
        widget = DashboardWidget(
            id=widget_id,
            type=WidgetType.GAUGE,
            title=title,
            data={
                "value": value,
                "min": min_val,
                "max": max_val,
                "unit": unit,
            },
        )
        self.add_widget(widget)

    def add_heatmap_widget(
        self,
        widget_id: str,
        title: str,
        matrix: List[List[float]],
        labels: List[str],
    ) -> None:
        """Add heatmap widget (correlation matrix, etc.)."""
        widget = DashboardWidget(
            id=widget_id,
            type=WidgetType.HEATMAP,
            title=title,
            data={
                "matrix": matrix,
                "labels": labels,
            },
        )
        self.add_widget(widget)

    def get_all_widgets(self) -> List[dict]:
        """Get all widgets as JSON."""
        return [w.to_json() for w in self.widgets]

    def get_widget(self, widget_id: str) -> Optional[DashboardWidget]:
        """Get specific widget."""
        for w in self.widgets:
            if w.id == widget_id:
                return w
        return None

    def update_widget_data(self, widget_id: str, data: Dict[str, Any]) -> bool:
        """Update widget data."""
        widget = self.get_widget(widget_id)
        if widget:
            widget.data.update(data)
            self.last_update = datetime.utcnow()
            return True
        return False

    def render_text(self) -> str:
        """Render dashboard as text (for terminal display)."""
        lines = [f"=== {self.name} ==="]
        for widget in self.widgets:
            lines.append(f"\n[{widget.type.value.upper()}] {widget.title}")
            if widget.type == WidgetType.METRIC:
                value = widget.data.get("value")
                unit = widget.data.get("unit", "")
                lines.append(f"  Value: {value} {unit}")
            elif widget.type == WidgetType.ALERT:
                message = widget.data.get("message")
                level = widget.data.get("level", "info").upper()
                lines.append(f"  [{level}] {message}")
            elif widget.type == WidgetType.TABLE:
                headers = widget.data.get("headers", [])
                rows = widget.data.get("rows", [])
                lines.append(f"  {' | '.join(headers)}")
                for row in rows[:5]:  # Show first 5 rows
                    lines.append(f"  {' | '.join(map(str, row))}")
        return "\n".join(lines)

    def to_json(self) -> dict:
        """Export entire dashboard as JSON."""
        return {
            "name": self.name,
            "widgets": self.get_all_widgets(),
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }

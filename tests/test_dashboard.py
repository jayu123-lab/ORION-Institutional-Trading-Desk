"""Tests for dashboard visualization."""
import pytest
from core.visualization.dashboard import (
    Dashboard,
    DashboardWidget,
    WidgetType,
)


def test_dashboard_creation():
    """Test creating a dashboard."""
    dashboard = Dashboard("Test Dashboard")
    assert dashboard.name == "Test Dashboard"
    assert len(dashboard.widgets) == 0


def test_add_metric_widget():
    """Test adding a metric widget."""
    dashboard = Dashboard()
    dashboard.add_metric_widget("metric_1", "SPX", 5000, unit="pts")
    
    assert len(dashboard.widgets) == 1
    assert dashboard.widgets[0].title == "SPX"


def test_add_table_widget():
    """Test adding a table widget."""
    dashboard = Dashboard()
    dashboard.add_table_widget(
        "table_1",
        "Positions",
        ["Symbol", "Size", "PnL"],
        [["SPY", "100", "+250"], ["GLD", "50", "-150"]],
    )
    
    assert len(dashboard.widgets) == 1
    assert dashboard.widgets[0].type == WidgetType.TABLE


def test_add_alert_widget():
    """Test adding an alert widget."""
    dashboard = Dashboard()
    dashboard.add_alert_widget("alert_1", "Risk Alert", "Position too large", level="warning")
    
    assert len(dashboard.widgets) == 1
    assert dashboard.widgets[0].type == WidgetType.ALERT


def test_add_gauge_widget():
    """Test adding a gauge widget."""
    dashboard = Dashboard()
    dashboard.add_gauge_widget("gauge_1", "VIX", 22.5, min_val=10, max_val=50)
    
    assert len(dashboard.widgets) == 1
    assert dashboard.widgets[0].type == WidgetType.GAUGE


def test_update_widget_data():
    """Test updating widget data."""
    dashboard = Dashboard()
    dashboard.add_metric_widget("metric_1", "SPX", 5000)
    
    success = dashboard.update_widget_data("metric_1", {"value": 5100})
    assert success
    assert dashboard.get_widget("metric_1").data["value"] == 5100


def test_get_widget():
    """Test retrieving specific widget."""
    dashboard = Dashboard()
    dashboard.add_metric_widget("metric_1", "Test", 100)
    
    widget = dashboard.get_widget("metric_1")
    assert widget is not None
    assert widget.title == "Test"


def test_dashboard_json_export():
    """Test exporting dashboard as JSON."""
    dashboard = Dashboard("Test")
    dashboard.add_metric_widget("metric_1", "SPX", 5000)
    
    json_data = dashboard.to_json()
    assert json_data["name"] == "Test"
    assert len(json_data["widgets"]) == 1

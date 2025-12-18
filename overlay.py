"""
WiFi Gaming Monitor - Desktop Overlay (PyQt5)
Transparent, always-on-top network status overlay for gaming
Fetches data from the web API for consistent values
"""

import sys
import urllib.request
import json
from dataclasses import dataclass
from typing import Optional
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QMenu, QAction
)
from PyQt5.QtCore import Qt, QTimer, QPoint, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QColor, QPainter, QBrush


@dataclass
class OverlayConfig:
    """Configuration for the overlay"""
    # Position (from bottom-right corner)
    x_offset: int = 20
    y_offset: int = 100

    # Appearance
    bg_color: str = '#0a0a0f'
    bg_alpha: int = 230  # 0-255

    # Colors
    text_color: str = '#ffffff'
    good_color: str = '#10b981'
    warning_color: str = '#f59e0b'
    critical_color: str = '#ef4444'
    muted_color: str = '#606070'

    # Size
    width: int = 200
    height: int = 280
    compact_mode: bool = False

    # Update interval (ms)
    update_interval: int = 1000

    # API endpoint
    api_url: str = 'http://127.0.0.1:5555/api/metrics'


@dataclass
class MetricsData:
    """Simple metrics container from API"""
    ping_ms: Optional[float] = None
    jitter_ms: Optional[float] = None
    packet_loss_percent: float = 0.0
    signal_percent: Optional[int] = None
    quality_score: int = 0
    quality_status: str = "Unknown"
    ssid: Optional[str] = None


class MonitorThread(QThread):
    """Background thread that fetches metrics from API"""
    metrics_updated = pyqtSignal(object)

    def __init__(self, api_url: str, interval_ms: int = 1000):
        super().__init__()
        self.api_url = api_url
        self.interval = interval_ms
        self.running = True

    def run(self):
        while self.running:
            try:
                # Fetch from API
                req = urllib.request.Request(self.api_url, headers={'Accept': 'application/json'})
                with urllib.request.urlopen(req, timeout=2) as response:
                    data = json.loads(response.read().decode('utf-8'))

                # Convert to MetricsData
                metrics = MetricsData(
                    ping_ms=data['latency']['ping'],
                    jitter_ms=data['latency']['jitter'],
                    packet_loss_percent=data['packets']['loss_percent'],
                    signal_percent=data['wifi']['signal_percent'],
                    quality_score=data['quality']['score'],
                    quality_status=data['quality']['status'],
                    ssid=data['wifi']['ssid']
                )
                self.metrics_updated.emit(metrics)

            except urllib.error.URLError:
                # API not available - emit empty metrics
                self.metrics_updated.emit(MetricsData(quality_status="API Offline"))
            except Exception as e:
                print(f"API fetch error: {e}")

            self.msleep(self.interval)

    def stop(self):
        self.running = False
        self.wait()


class GamingOverlay(QWidget):
    """
    Transparent overlay window showing network metrics
    """

    def __init__(self, config: Optional[OverlayConfig] = None):
        super().__init__()
        self.config = config or OverlayConfig()
        self.drag_position = None

        self._setup_window()
        self._create_ui()
        self._start_monitoring()
        self._position_window()

    def _setup_window(self):
        """Configure window flags for always-on-top overlay"""
        # Critical flags for gaming overlay
        self.setWindowFlags(
            Qt.FramelessWindowHint |        # No window border
            Qt.WindowStaysOnTopHint |       # Always on top
            Qt.Tool |                       # Tool window (not in taskbar)
            Qt.WindowDoesNotAcceptFocus |   # Don't steal focus from game
            Qt.X11BypassWindowManagerHint | # Bypass WM on Linux
            Qt.WindowTransparentForInput    # Optional: click-through
        )

        # Remove WindowTransparentForInput to allow interaction
        # Re-set without that flag
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.X11BypassWindowManagerHint
        )

        # Transparency
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # Size
        self.setFixedSize(self.config.width, self.config.height)

    def _position_window(self):
        """Position window in bottom-right corner"""
        screen = QApplication.primaryScreen().geometry()
        x = screen.width() - self.config.width - self.config.x_offset
        y = screen.height() - self.config.height - self.config.y_offset
        self.move(x, y)

    def _create_ui(self):
        """Create the overlay UI"""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Container with background
        self.container = QFrame()
        self.container.setObjectName("container")
        self.container.setStyleSheet(f"""
            #container {{
                background-color: rgba(10, 10, 15, {self.config.bg_alpha});
                border-radius: 8px;
                border: 1px solid #252530;
            }}
        """)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(12, 10, 12, 10)
        container_layout.setSpacing(8)

        # Title bar
        title_bar = QHBoxLayout()

        self.drag_label = QLabel(":: WiFi Monitor ::")
        self.drag_label.setFont(QFont("Consolas", 8))
        self.drag_label.setStyleSheet(f"color: {self.config.muted_color};")
        self.drag_label.setCursor(Qt.OpenHandCursor)
        title_bar.addWidget(self.drag_label)

        title_bar.addStretch()

        self.close_btn = QLabel("X")
        self.close_btn.setFont(QFont("Consolas", 8, QFont.Bold))
        self.close_btn.setStyleSheet(f"color: {self.config.muted_color};")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.mousePressEvent = lambda e: self.close()
        self.close_btn.enterEvent = lambda e: self.close_btn.setStyleSheet(f"color: {self.config.critical_color};")
        self.close_btn.leaveEvent = lambda e: self.close_btn.setStyleSheet(f"color: {self.config.muted_color};")
        title_bar.addWidget(self.close_btn)

        container_layout.addLayout(title_bar)

        # Quality score
        quality_frame = QVBoxLayout()
        quality_frame.setAlignment(Qt.AlignCenter)

        self.quality_label = QLabel("--")
        self.quality_label.setFont(QFont("Consolas", 36, QFont.Bold))
        self.quality_label.setStyleSheet(f"color: {self.config.good_color};")
        self.quality_label.setAlignment(Qt.AlignCenter)
        quality_frame.addWidget(self.quality_label)

        self.quality_status = QLabel("CONNECTING")
        self.quality_status.setFont(QFont("Consolas", 9))
        self.quality_status.setStyleSheet(f"color: {self.config.muted_color};")
        self.quality_status.setAlignment(Qt.AlignCenter)
        quality_frame.addWidget(self.quality_status)

        container_layout.addLayout(quality_frame)

        # Metrics
        self.ping_row = self._create_metric_row("PING", "--", "ms")
        container_layout.addLayout(self.ping_row['layout'])

        self.jitter_row = self._create_metric_row("JITTER", "--", "ms")
        container_layout.addLayout(self.jitter_row['layout'])

        self.loss_row = self._create_metric_row("LOSS", "--", "%")
        container_layout.addLayout(self.loss_row['layout'])

        self.signal_row = self._create_metric_row("SIGNAL", "--", "%")
        container_layout.addLayout(self.signal_row['layout'])

        # SSID
        self.ssid_label = QLabel("")
        self.ssid_label.setFont(QFont("Consolas", 8))
        self.ssid_label.setStyleSheet(f"color: {self.config.muted_color};")
        self.ssid_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self.ssid_label)

        # Status indicator bar
        self.status_bar = QFrame()
        self.status_bar.setFixedHeight(3)
        self.status_bar.setStyleSheet(f"background-color: {self.config.good_color}; border-radius: 1px;")
        container_layout.addWidget(self.status_bar)

        layout.addWidget(self.container)

    def _create_metric_row(self, label: str, value: str, unit: str) -> dict:
        """Create a metric display row"""
        row_layout = QHBoxLayout()
        row_layout.setSpacing(5)

        label_widget = QLabel(label)
        label_widget.setFont(QFont("Consolas", 9))
        label_widget.setStyleSheet(f"color: {self.config.muted_color};")
        label_widget.setFixedWidth(60)
        row_layout.addWidget(label_widget)

        value_widget = QLabel(value)
        value_widget.setFont(QFont("Consolas", 14, QFont.Bold))
        value_widget.setStyleSheet(f"color: {self.config.text_color};")
        value_widget.setAlignment(Qt.AlignRight)
        value_widget.setFixedWidth(60)
        row_layout.addWidget(value_widget)

        unit_widget = QLabel(unit)
        unit_widget.setFont(QFont("Consolas", 9))
        unit_widget.setStyleSheet(f"color: {self.config.muted_color};")
        row_layout.addWidget(unit_widget)

        row_layout.addStretch()

        return {'layout': row_layout, 'value': value_widget}

    def _start_monitoring(self):
        """Start the background monitoring thread"""
        self.monitor_thread = MonitorThread(self.config.api_url, self.config.update_interval)
        self.monitor_thread.metrics_updated.connect(self._update_display)
        self.monitor_thread.start()

        # Also set up a timer to periodically ensure we stay on top
        self.topmost_timer = QTimer(self)
        self.topmost_timer.timeout.connect(self._ensure_on_top)
        self.topmost_timer.start(500)  # Every 500ms

    def _ensure_on_top(self):
        """Periodically ensure window stays on top"""
        # Raise the window
        self.raise_()

        # On Windows, use win32 API for extra assurance
        try:
            import ctypes
            hwnd = int(self.winId())
            HWND_TOPMOST = -1
            SWP_NOMOVE = 0x0002
            SWP_NOSIZE = 0x0001
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040

            ctypes.windll.user32.SetWindowPos(
                hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
            )
        except Exception:
            pass

    def _update_display(self, metrics: MetricsData):
        """Update the display with new metrics"""
        # Quality score
        self.quality_label.setText(str(metrics.quality_score))
        self.quality_status.setText(metrics.quality_status.upper())

        # Quality color
        if metrics.quality_score >= 75:
            color = self.config.good_color
        elif metrics.quality_score >= 50:
            color = self.config.warning_color
        else:
            color = self.config.critical_color

        self.quality_label.setStyleSheet(f"color: {color};")
        self.status_bar.setStyleSheet(f"background-color: {color}; border-radius: 1px;")

        # Ping
        if metrics.ping_ms is not None:
            self.ping_row['value'].setText(f"{metrics.ping_ms:.0f}")
            self.ping_row['value'].setStyleSheet(
                f"color: {self._get_metric_color(metrics.ping_ms, 50, 100)};"
            )
        else:
            self.ping_row['value'].setText("--")
            self.ping_row['value'].setStyleSheet(f"color: {self.config.muted_color};")

        # Jitter
        if metrics.jitter_ms is not None:
            self.jitter_row['value'].setText(f"{metrics.jitter_ms:.1f}")
            self.jitter_row['value'].setStyleSheet(
                f"color: {self._get_metric_color(metrics.jitter_ms, 10, 30)};"
            )
        else:
            self.jitter_row['value'].setText("--")
            self.jitter_row['value'].setStyleSheet(f"color: {self.config.muted_color};")

        # Packet Loss
        self.loss_row['value'].setText(f"{metrics.packet_loss_percent:.1f}")
        self.loss_row['value'].setStyleSheet(
            f"color: {self._get_metric_color(metrics.packet_loss_percent, 1, 5)};"
        )

        # Signal
        if metrics.signal_percent is not None:
            self.signal_row['value'].setText(str(metrics.signal_percent))
            self.signal_row['value'].setStyleSheet(
                f"color: {self._get_signal_color(metrics.signal_percent)};"
            )
        else:
            self.signal_row['value'].setText("--")
            self.signal_row['value'].setStyleSheet(f"color: {self.config.muted_color};")

        # SSID
        if metrics.ssid:
            self.ssid_label.setText(metrics.ssid)

    def _get_metric_color(self, value: float, warning_threshold: float, critical_threshold: float) -> str:
        """Get color based on metric value (higher = worse)"""
        if value >= critical_threshold:
            return self.config.critical_color
        elif value >= warning_threshold:
            return self.config.warning_color
        else:
            return self.config.good_color

    def _get_signal_color(self, value: int) -> str:
        """Get color based on signal strength (higher = better)"""
        if value >= 70:
            return self.config.good_color
        elif value >= 50:
            return self.config.warning_color
        else:
            return self.config.critical_color

    # Mouse events for dragging
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_position = event.globalPos() - self.frameGeometry().topLeft()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self.drag_position:
            self.move(event.globalPos() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        self.drag_position = None
        self.setCursor(Qt.ArrowCursor)

    def contextMenuEvent(self, event):
        """Show right-click context menu"""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1a24;
                color: white;
                border: 1px solid #333;
            }
            QMenu::item:selected {
                background-color: #333;
            }
        """)

        compact_action = menu.addAction("Compact Mode")
        compact_action.triggered.connect(self._toggle_compact)

        menu.addSeparator()

        close_action = menu.addAction("Close")
        close_action.triggered.connect(self.close)

        menu.exec_(event.globalPos())

    def _toggle_compact(self):
        """Toggle compact mode"""
        self.config.compact_mode = not self.config.compact_mode
        # TODO: Implement compact view

    def closeEvent(self, event):
        """Clean up on close"""
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.stop()
        if hasattr(self, 'topmost_timer'):
            self.topmost_timer.stop()
        event.accept()


def main():
    """Main entry point"""
    print("\n" + "="*50)
    print("  WiFi Gaming Monitor - Desktop Overlay")
    print("="*50)
    print("  NOTE: Web dashboard must be running!")
    print("        (python app.py or python run.py)")
    print("="*50)
    print("  Drag anywhere to move")
    print("  Right-click for menu")
    print("  Close button to exit")
    print("="*50 + "\n")

    app = QApplication(sys.argv)

    config = OverlayConfig(
        x_offset=20,
        y_offset=100,
        bg_alpha=230,
        update_interval=1000,
        api_url='http://127.0.0.1:5555/api/metrics'
    )

    overlay = GamingOverlay(config)
    overlay.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()

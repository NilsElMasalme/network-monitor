"""
WiFi Gaming Monitor - Desktop Overlay
Transparent, always-on-top network status overlay for gaming
"""

import tkinter as tk
from tkinter import font as tkfont
import threading
import time
from dataclasses import dataclass
from typing import Optional
import ctypes

# Import the network monitor
from network_monitor import NetworkMonitor, NetworkMetrics


@dataclass
class OverlayConfig:
    """Configuration for the overlay"""
    # Position (from bottom-right corner)
    x_offset: int = 20
    y_offset: int = 100

    # Appearance
    bg_color: str = '#0a0a0f'
    bg_alpha: float = 0.85

    # Colors
    text_color: str = '#ffffff'
    good_color: str = '#10b981'
    warning_color: str = '#f59e0b'
    critical_color: str = '#ef4444'
    muted_color: str = '#606070'

    # Size
    width: int = 200
    compact_mode: bool = False

    # Update interval (ms)
    update_interval: int = 1000


class GamingOverlay:
    """
    Transparent overlay window showing network metrics
    """

    def __init__(self, config: Optional[OverlayConfig] = None):
        self.config = config or OverlayConfig()
        self.monitor = NetworkMonitor()
        self.running = False

        # Create window
        self.root = tk.Tk()
        self.root.title("WiFi Monitor")

        # Remove window decorations
        self.root.overrideredirect(True)

        # Always on top
        self.root.attributes('-topmost', True)

        # Transparency (Windows)
        self.root.attributes('-alpha', self.config.bg_alpha)

        # Make window click-through when not focused (optional)
        # self._set_click_through()

        # Configure window
        self.root.configure(bg=self.config.bg_color)

        # Position window
        self._position_window()

        # Create UI
        self._create_ui()

        # Bind events
        self._bind_events()

        # Start monitoring
        self._start_monitoring()

    def _position_window(self):
        """Position window in bottom-right corner"""
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()

        x = screen_width - self.config.width - self.config.x_offset
        y = screen_height - 300 - self.config.y_offset  # Approximate height

        self.root.geometry(f'{self.config.width}x300+{x}+{y}')

    def _create_ui(self):
        """Create the overlay UI"""
        # Main frame with rounded appearance
        self.main_frame = tk.Frame(
            self.root,
            bg=self.config.bg_color,
            padx=12,
            pady=10
        )
        self.main_frame.pack(fill='both', expand=True)

        # Title bar with drag handle
        title_frame = tk.Frame(self.main_frame, bg=self.config.bg_color)
        title_frame.pack(fill='x', pady=(0, 8))

        # Drag handle indicator
        self.drag_label = tk.Label(
            title_frame,
            text=":: WiFi Monitor ::",
            font=('Consolas', 8),
            fg=self.config.muted_color,
            bg=self.config.bg_color,
            cursor='fleur'
        )
        self.drag_label.pack(side='left')

        # Close button
        close_btn = tk.Label(
            title_frame,
            text="X",
            font=('Consolas', 8, 'bold'),
            fg=self.config.muted_color,
            bg=self.config.bg_color,
            cursor='hand2'
        )
        close_btn.pack(side='right')
        close_btn.bind('<Button-1>', lambda e: self.close())
        close_btn.bind('<Enter>', lambda e: close_btn.configure(fg=self.config.critical_color))
        close_btn.bind('<Leave>', lambda e: close_btn.configure(fg=self.config.muted_color))

        # Quality score
        self.quality_frame = tk.Frame(self.main_frame, bg=self.config.bg_color)
        self.quality_frame.pack(fill='x', pady=(0, 10))

        self.quality_label = tk.Label(
            self.quality_frame,
            text="--",
            font=('Consolas', 36, 'bold'),
            fg=self.config.good_color,
            bg=self.config.bg_color
        )
        self.quality_label.pack()

        self.quality_status = tk.Label(
            self.quality_frame,
            text="CONNECTING",
            font=('Consolas', 9),
            fg=self.config.muted_color,
            bg=self.config.bg_color
        )
        self.quality_status.pack()

        # Metrics
        self.metrics_frame = tk.Frame(self.main_frame, bg=self.config.bg_color)
        self.metrics_frame.pack(fill='x')

        # Create metric rows
        self.ping_row = self._create_metric_row("PING", "--", "ms")
        self.jitter_row = self._create_metric_row("JITTER", "--", "ms")
        self.loss_row = self._create_metric_row("LOSS", "--", "%")
        self.signal_row = self._create_metric_row("SIGNAL", "--", "%")

        # SSID
        self.ssid_label = tk.Label(
            self.main_frame,
            text="",
            font=('Consolas', 8),
            fg=self.config.muted_color,
            bg=self.config.bg_color
        )
        self.ssid_label.pack(pady=(10, 0))

        # Status bar
        self.status_bar = tk.Frame(self.main_frame, bg=self.config.bg_color, height=3)
        self.status_bar.pack(fill='x', pady=(10, 0))

        self.status_indicator = tk.Frame(
            self.status_bar,
            bg=self.config.good_color,
            height=3,
            width=self.config.width
        )
        self.status_indicator.pack(fill='x')

    def _create_metric_row(self, label: str, value: str, unit: str):
        """Create a metric display row"""
        row = tk.Frame(self.metrics_frame, bg=self.config.bg_color)
        row.pack(fill='x', pady=2)

        label_widget = tk.Label(
            row,
            text=label,
            font=('Consolas', 9),
            fg=self.config.muted_color,
            bg=self.config.bg_color,
            width=8,
            anchor='w'
        )
        label_widget.pack(side='left')

        value_widget = tk.Label(
            row,
            text=value,
            font=('Consolas', 14, 'bold'),
            fg=self.config.text_color,
            bg=self.config.bg_color,
            width=6,
            anchor='e'
        )
        value_widget.pack(side='left', padx=(5, 0))

        unit_widget = tk.Label(
            row,
            text=unit,
            font=('Consolas', 9),
            fg=self.config.muted_color,
            bg=self.config.bg_color,
            anchor='w'
        )
        unit_widget.pack(side='left', padx=(2, 0))

        return {'frame': row, 'value': value_widget}

    def _bind_events(self):
        """Bind window events"""
        # Drag functionality
        self.drag_label.bind('<Button-1>', self._start_drag)
        self.drag_label.bind('<B1-Motion>', self._on_drag)

        # Right-click menu
        self.root.bind('<Button-3>', self._show_context_menu)

        # Keyboard shortcuts
        self.root.bind('<Escape>', lambda e: self.close())
        self.root.bind('<c>', lambda e: self._toggle_compact())

    def _start_drag(self, event):
        """Start window drag"""
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _on_drag(self, event):
        """Handle window dragging"""
        x = self.root.winfo_x() + event.x - self._drag_start_x
        y = self.root.winfo_y() + event.y - self._drag_start_y
        self.root.geometry(f'+{x}+{y}')

    def _show_context_menu(self, event):
        """Show right-click context menu"""
        menu = tk.Menu(self.root, tearoff=0, bg='#1a1a24', fg='white')
        menu.add_command(label="Compact Mode", command=self._toggle_compact)
        menu.add_separator()
        menu.add_command(label="Close", command=self.close)
        menu.post(event.x_root, event.y_root)

    def _toggle_compact(self):
        """Toggle compact mode"""
        self.config.compact_mode = not self.config.compact_mode
        # TODO: Implement compact view
        pass

    def _start_monitoring(self):
        """Start the background monitoring thread"""
        self.running = True

        def update_loop():
            while self.running:
                try:
                    metrics = self.monitor.collect_metrics()
                    self.root.after(0, lambda m=metrics: self._update_display(m))
                except Exception as e:
                    print(f"Monitoring error: {e}")
                time.sleep(self.config.update_interval / 1000)

        self.monitor_thread = threading.Thread(target=update_loop, daemon=True)
        self.monitor_thread.start()

    def _update_display(self, metrics: NetworkMetrics):
        """Update the display with new metrics"""
        # Quality score
        self.quality_label.configure(text=str(metrics.quality_score))
        self.quality_status.configure(text=metrics.quality_status.upper())

        # Quality color
        if metrics.quality_score >= 75:
            color = self.config.good_color
        elif metrics.quality_score >= 50:
            color = self.config.warning_color
        else:
            color = self.config.critical_color

        self.quality_label.configure(fg=color)
        self.status_indicator.configure(bg=color)

        # Ping
        if metrics.ping_ms is not None:
            self.ping_row['value'].configure(
                text=f"{metrics.ping_ms:.0f}",
                fg=self._get_metric_color(metrics.ping_ms, 50, 100)
            )
        else:
            self.ping_row['value'].configure(text="--", fg=self.config.muted_color)

        # Jitter
        if metrics.jitter_ms is not None:
            self.jitter_row['value'].configure(
                text=f"{metrics.jitter_ms:.1f}",
                fg=self._get_metric_color(metrics.jitter_ms, 10, 30)
            )
        else:
            self.jitter_row['value'].configure(text="--", fg=self.config.muted_color)

        # Packet Loss
        self.loss_row['value'].configure(
            text=f"{metrics.packet_loss_percent:.1f}",
            fg=self._get_metric_color(metrics.packet_loss_percent, 1, 5)
        )

        # Signal
        if metrics.signal_percent is not None:
            self.signal_row['value'].configure(
                text=str(metrics.signal_percent),
                fg=self._get_signal_color(metrics.signal_percent)
            )
        else:
            self.signal_row['value'].configure(text="--", fg=self.config.muted_color)

        # SSID
        if metrics.ssid:
            self.ssid_label.configure(text=metrics.ssid)

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

    def run(self):
        """Start the overlay"""
        print("\n" + "="*50)
        print("  WiFi Gaming Monitor - Desktop Overlay")
        print("="*50)
        print("  Drag the title bar to move")
        print("  Right-click for menu")
        print("  Press ESC to close")
        print("="*50 + "\n")

        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.close()

    def close(self):
        """Close the overlay"""
        self.running = False
        self.root.quit()
        self.root.destroy()


def main():
    """Main entry point"""
    config = OverlayConfig(
        x_offset=20,
        y_offset=100,
        bg_alpha=0.9,
        update_interval=1000
    )

    overlay = GamingOverlay(config)
    overlay.run()


if __name__ == '__main__':
    main()

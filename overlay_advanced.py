"""
WiFi Gaming Monitor - Advanced Desktop Overlay
Sleek, minimal overlay optimized for gaming with spike detection
"""

import tkinter as tk
from tkinter import ttk
import threading
import time
from collections import deque
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from network_monitor import NetworkMonitor, NetworkMetrics


class AdvancedGamingOverlay:
    """
    Minimal, sleek gaming overlay with spike detection and mini-graph
    """

    # Color scheme
    COLORS = {
        'bg': '#0d0d12',
        'bg_light': '#16161d',
        'text': '#ffffff',
        'text_dim': '#6b7280',
        'good': '#22c55e',
        'warning': '#eab308',
        'critical': '#ef4444',
        'accent': '#6366f1',
        'border': '#1f1f2e'
    }

    def __init__(self, position='bottom-right', compact=False):
        self.position = position
        self.compact = compact
        self.monitor = NetworkMonitor()
        self.running = False

        # History for mini-graph
        self.ping_history = deque(maxlen=30)
        self.spike_count = 0
        self.last_spike_time = None

        # Create window
        self.root = tk.Tk()
        self.root.title("Net Monitor")
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.92)
        self.root.configure(bg=self.COLORS['bg'])

        # Calculate size based on mode
        self.width = 180 if compact else 220
        self.height = 120 if compact else 320

        self._setup_window()
        self._create_ui()
        self._bind_events()

    def _setup_window(self):
        """Position window based on preference"""
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()

        margin = 20
        taskbar_height = 50

        positions = {
            'top-left': (margin, margin),
            'top-right': (screen_w - self.width - margin, margin),
            'bottom-left': (margin, screen_h - self.height - margin - taskbar_height),
            'bottom-right': (screen_w - self.width - margin, screen_h - self.height - margin - taskbar_height),
        }

        x, y = positions.get(self.position, positions['bottom-right'])
        self.root.geometry(f'{self.width}x{self.height}+{x}+{y}')

    def _create_ui(self):
        """Create the overlay UI"""
        # Main container
        self.container = tk.Frame(
            self.root,
            bg=self.COLORS['bg'],
            highlightbackground=self.COLORS['border'],
            highlightthickness=1
        )
        self.container.pack(fill='both', expand=True)

        # Header with drag handle
        header = tk.Frame(self.container, bg=self.COLORS['bg_light'], height=24)
        header.pack(fill='x')
        header.pack_propagate(False)

        self.title = tk.Label(
            header,
            text="NET",
            font=('Segoe UI', 8, 'bold'),
            fg=self.COLORS['accent'],
            bg=self.COLORS['bg_light']
        )
        self.title.pack(side='left', padx=8, pady=4)

        # Status dot
        self.status_dot = tk.Canvas(
            header,
            width=8, height=8,
            bg=self.COLORS['bg_light'],
            highlightthickness=0
        )
        self.status_dot.pack(side='left', pady=4)
        self.dot_id = self.status_dot.create_oval(0, 0, 8, 8, fill=self.COLORS['good'], outline='')

        # Close button
        close_btn = tk.Label(
            header,
            text="x",
            font=('Segoe UI', 9),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg_light'],
            cursor='hand2'
        )
        close_btn.pack(side='right', padx=8, pady=4)
        close_btn.bind('<Button-1>', lambda e: self.close())
        close_btn.bind('<Enter>', lambda e: close_btn.configure(fg=self.COLORS['critical']))
        close_btn.bind('<Leave>', lambda e: close_btn.configure(fg=self.COLORS['text_dim']))

        # Drag bindings
        header.bind('<Button-1>', self._start_drag)
        header.bind('<B1-Motion>', self._on_drag)
        self.title.bind('<Button-1>', self._start_drag)
        self.title.bind('<B1-Motion>', self._on_drag)

        # Content area
        content = tk.Frame(self.container, bg=self.COLORS['bg'])
        content.pack(fill='both', expand=True, padx=10, pady=8)

        if self.compact:
            self._create_compact_ui(content)
        else:
            self._create_full_ui(content)

    def _create_compact_ui(self, parent):
        """Create compact single-line display"""
        row = tk.Frame(parent, bg=self.COLORS['bg'])
        row.pack(fill='x')

        # Ping
        self.ping_value = tk.Label(
            row, text="--",
            font=('Consolas', 14, 'bold'),
            fg=self.COLORS['good'],
            bg=self.COLORS['bg']
        )
        self.ping_value.pack(side='left')

        tk.Label(
            row, text="ms",
            font=('Consolas', 8),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg']
        ).pack(side='left', padx=(2, 10))

        # Jitter
        self.jitter_value = tk.Label(
            row, text="--",
            font=('Consolas', 11),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg']
        )
        self.jitter_value.pack(side='left')

        tk.Label(
            row, text="j",
            font=('Consolas', 8),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg']
        ).pack(side='left', padx=(2, 10))

        # Loss
        self.loss_value = tk.Label(
            row, text="0%",
            font=('Consolas', 11),
            fg=self.COLORS['good'],
            bg=self.COLORS['bg']
        )
        self.loss_value.pack(side='left')

        # Placeholders for full mode elements
        self.signal_value = None
        self.quality_value = None
        self.graph_canvas = None
        self.spike_label = None
        self.ssid_label = None
        self.download_value = None
        self.upload_value = None

    def _create_full_ui(self, parent):
        """Create full detailed display"""
        # Quality score (large)
        quality_frame = tk.Frame(parent, bg=self.COLORS['bg'])
        quality_frame.pack(fill='x', pady=(0, 10))

        self.quality_value = tk.Label(
            quality_frame,
            text="--",
            font=('Segoe UI', 32, 'bold'),
            fg=self.COLORS['good'],
            bg=self.COLORS['bg']
        )
        self.quality_value.pack(side='left')

        quality_label = tk.Label(
            quality_frame,
            text="/100",
            font=('Segoe UI', 12),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg']
        )
        quality_label.pack(side='left', anchor='s', pady=(0, 6))

        # Metrics grid
        metrics_frame = tk.Frame(parent, bg=self.COLORS['bg'])
        metrics_frame.pack(fill='x')

        # Row 1: Ping & Jitter
        row1 = tk.Frame(metrics_frame, bg=self.COLORS['bg'])
        row1.pack(fill='x', pady=2)

        self.ping_value = self._create_metric(row1, "PING", "--", "ms", 'left')
        self.jitter_value = self._create_metric(row1, "JITTER", "--", "ms", 'right')

        # Row 2: Loss & Signal
        row2 = tk.Frame(metrics_frame, bg=self.COLORS['bg'])
        row2.pack(fill='x', pady=2)

        self.loss_value = self._create_metric(row2, "LOSS", "0", "%", 'left')
        self.signal_value = self._create_metric(row2, "SIGNAL", "--", "%", 'right')

        # Row 3: Download & Upload (actual Mbit/s)
        row3 = tk.Frame(metrics_frame, bg=self.COLORS['bg'])
        row3.pack(fill='x', pady=2)

        self.download_value = self._create_metric(row3, "DOWN", "0.0", "Mb/s", 'left')
        self.upload_value = self._create_metric(row3, "UP", "0.0", "Mb/s", 'right')

        # Mini graph
        graph_frame = tk.Frame(parent, bg=self.COLORS['bg'])
        graph_frame.pack(fill='x', pady=(10, 5))

        tk.Label(
            graph_frame,
            text="PING HISTORY",
            font=('Segoe UI', 7),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg']
        ).pack(anchor='w')

        self.graph_canvas = tk.Canvas(
            graph_frame,
            width=self.width - 30,
            height=40,
            bg=self.COLORS['bg_light'],
            highlightthickness=0
        )
        self.graph_canvas.pack(fill='x', pady=(2, 0))

        # Spike counter
        spike_frame = tk.Frame(parent, bg=self.COLORS['bg'])
        spike_frame.pack(fill='x', pady=(5, 0))

        self.spike_label = tk.Label(
            spike_frame,
            text="Spikes: 0",
            font=('Segoe UI', 8),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg']
        )
        self.spike_label.pack(side='left')

        # SSID
        self.ssid_label = tk.Label(
            spike_frame,
            text="",
            font=('Segoe UI', 8),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg']
        )
        self.ssid_label.pack(side='right')

    def _create_metric(self, parent, label, value, unit, side):
        """Create a metric display widget"""
        frame = tk.Frame(parent, bg=self.COLORS['bg'])
        frame.pack(side=side, expand=True, anchor='w' if side == 'left' else 'e')

        tk.Label(
            frame,
            text=label,
            font=('Segoe UI', 7),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg']
        ).pack(anchor='w')

        value_frame = tk.Frame(frame, bg=self.COLORS['bg'])
        value_frame.pack(anchor='w')

        value_label = tk.Label(
            value_frame,
            text=value,
            font=('Consolas', 14, 'bold'),
            fg=self.COLORS['text'],
            bg=self.COLORS['bg']
        )
        value_label.pack(side='left')

        tk.Label(
            value_frame,
            text=unit,
            font=('Consolas', 8),
            fg=self.COLORS['text_dim'],
            bg=self.COLORS['bg']
        ).pack(side='left', padx=(2, 0))

        return value_label

    def _bind_events(self):
        """Bind window events"""
        self.root.bind('<Escape>', lambda e: self.close())
        self.root.bind('<c>', lambda e: self._toggle_compact())
        self.root.bind('<r>', lambda e: self._reset_spikes())

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        x = self.root.winfo_x() + event.x - self._drag_x
        y = self.root.winfo_y() + event.y - self._drag_y
        self.root.geometry(f'+{x}+{y}')

    def _toggle_compact(self):
        """Toggle between compact and full mode"""
        self.compact = not self.compact
        self.root.destroy()
        self.__init__(position=self.position, compact=self.compact)
        self.start()

    def _reset_spikes(self):
        """Reset spike counter"""
        self.spike_count = 0
        if self.spike_label:
            self.spike_label.configure(text="Spikes: 0")

    def _update_graph(self):
        """Update the mini ping graph"""
        if not self.graph_canvas or not self.ping_history:
            return

        self.graph_canvas.delete('all')

        width = self.graph_canvas.winfo_width()
        height = self.graph_canvas.winfo_height()

        if len(self.ping_history) < 2:
            return

        # Calculate scale
        max_ping = max(max(self.ping_history), 100)
        min_ping = 0

        # Draw graph
        points = []
        bar_width = width / len(self.ping_history)

        for i, ping in enumerate(self.ping_history):
            x = i * bar_width + bar_width / 2
            y = height - (ping / max_ping) * (height - 5)

            # Color based on value
            if ping > 100:
                color = self.COLORS['critical']
            elif ping > 50:
                color = self.COLORS['warning']
            else:
                color = self.COLORS['good']

            # Draw bar
            self.graph_canvas.create_rectangle(
                x - bar_width/3, height,
                x + bar_width/3, y,
                fill=color, outline=''
            )

        # Draw threshold line at 50ms
        threshold_y = height - (50 / max_ping) * (height - 5)
        self.graph_canvas.create_line(
            0, threshold_y, width, threshold_y,
            fill=self.COLORS['warning'], dash=(2, 2)
        )

    def _update_display(self, metrics: NetworkMetrics):
        """Update the display with new metrics"""
        # Determine status color
        if metrics.quality_score >= 75:
            status_color = self.COLORS['good']
        elif metrics.quality_score >= 50:
            status_color = self.COLORS['warning']
        else:
            status_color = self.COLORS['critical']

        # Update status dot
        self.status_dot.itemconfig(self.dot_id, fill=status_color)

        # Update quality score
        if self.quality_value:
            self.quality_value.configure(
                text=str(metrics.quality_score),
                fg=status_color
            )

        # Ping
        if metrics.ping_ms is not None:
            ping_color = self._get_color(metrics.ping_ms, 50, 100)
            self.ping_value.configure(text=f"{metrics.ping_ms:.0f}", fg=ping_color)

            # Track for graph
            self.ping_history.append(metrics.ping_ms)

            # Detect spike
            if metrics.ping_ms > 100:
                self.spike_count += 1
                self.last_spike_time = datetime.now()
        else:
            self.ping_value.configure(text="--", fg=self.COLORS['text_dim'])

        # Jitter
        if metrics.jitter_ms is not None:
            jitter_color = self._get_color(metrics.jitter_ms, 10, 30)
            self.jitter_value.configure(text=f"{metrics.jitter_ms:.1f}", fg=jitter_color)
        else:
            self.jitter_value.configure(text="--", fg=self.COLORS['text_dim'])

        # Packet Loss
        loss_color = self._get_color(metrics.packet_loss_percent, 1, 5)
        self.loss_value.configure(text=f"{metrics.packet_loss_percent:.0f}", fg=loss_color)

        # Signal
        if self.signal_value and metrics.signal_percent is not None:
            signal_color = self._get_signal_color(metrics.signal_percent)
            self.signal_value.configure(text=str(metrics.signal_percent), fg=signal_color)

        # Download/Upload throughput
        if self.download_value:
            self.download_value.configure(text=f"{metrics.download_mbps:.1f}", fg=self.COLORS['text'])
        if self.upload_value:
            self.upload_value.configure(text=f"{metrics.upload_mbps:.1f}", fg=self.COLORS['text'])

        # SSID
        if self.ssid_label and metrics.ssid:
            self.ssid_label.configure(text=metrics.ssid[:15])

        # Spike counter
        if self.spike_label:
            spike_text = f"Spikes: {self.spike_count}"
            if self.last_spike_time:
                age = (datetime.now() - self.last_spike_time).seconds
                if age < 60:
                    spike_text += f" ({age}s ago)"
            self.spike_label.configure(text=spike_text)

        # Update graph
        self._update_graph()

    def _get_color(self, value, warning, critical):
        """Get color for metric (higher = worse)"""
        if value >= critical:
            return self.COLORS['critical']
        elif value >= warning:
            return self.COLORS['warning']
        return self.COLORS['good']

    def _get_signal_color(self, value):
        """Get color for signal (higher = better)"""
        if value >= 70:
            return self.COLORS['good']
        elif value >= 50:
            return self.COLORS['warning']
        return self.COLORS['critical']

    def start(self):
        """Start the overlay and monitoring"""
        self.running = True

        def update_loop():
            while self.running:
                try:
                    metrics = self.monitor.collect_metrics()
                    self.root.after(0, lambda m=metrics: self._update_display(m))
                except Exception as e:
                    print(f"Error: {e}")
                time.sleep(1)

        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()

        print("\n" + "="*50)
        print("  Advanced Gaming Overlay")
        print("="*50)
        print("  Drag header to move")
        print("  Press C to toggle compact mode")
        print("  Press R to reset spike counter")
        print("  Press ESC to close")
        print("="*50 + "\n")

        self.root.mainloop()

    def close(self):
        """Close the overlay"""
        self.running = False
        self.root.quit()
        self.root.destroy()


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Gaming Network Overlay')
    parser.add_argument('--position', '-p', default='bottom-right',
                        choices=['top-left', 'top-right', 'bottom-left', 'bottom-right'],
                        help='Window position')
    parser.add_argument('--compact', '-c', action='store_true',
                        help='Start in compact mode')
    args = parser.parse_args()

    overlay = AdvancedGamingOverlay(position=args.position, compact=args.compact)
    overlay.start()


if __name__ == '__main__':
    main()

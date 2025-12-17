"""
Network Monitoring Service
Collects WiFi and network metrics for gaming diagnostics
"""

import subprocess
import re
import time
import statistics
import socket
import struct
import threading
import os
import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from collections import deque
import logging

# Try to import psutil for throughput measurement
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class PingResult:
    """Single ping measurement result"""
    timestamp: datetime
    latency_ms: Optional[float]
    success: bool
    target: str


@dataclass
class NetworkMetrics:
    """Current network metrics snapshot"""
    timestamp: datetime

    # WiFi metrics
    signal_strength_dbm: Optional[int] = None
    signal_percent: Optional[int] = None
    link_speed_mbps: Optional[int] = None
    channel: Optional[int] = None
    frequency_ghz: Optional[float] = None
    ssid: Optional[str] = None
    bssid: Optional[str] = None

    # Latency metrics
    ping_ms: Optional[float] = None
    ping_min_ms: Optional[float] = None
    ping_max_ms: Optional[float] = None
    ping_avg_ms: Optional[float] = None
    jitter_ms: Optional[float] = None

    # Packet loss
    packet_loss_percent: float = 0.0
    packets_sent: int = 0
    packets_received: int = 0

    # Connection status
    is_connected: bool = False
    adapter_name: Optional[str] = None

    # Throughput (actual speed in Mbit/s)
    download_mbps: float = 0.0
    upload_mbps: float = 0.0

    # Quality score (0-100)
    quality_score: int = 0
    quality_status: str = "Unknown"


class ThroughputMonitor:
    """Measures actual network throughput using psutil"""

    def __init__(self):
        self._last_bytes_recv = 0
        self._last_bytes_sent = 0
        self._last_time = time.time()
        self._initialized = False

    def get_throughput(self) -> tuple:
        """Get current download/upload speed in Mbit/s"""
        if not HAS_PSUTIL:
            return 0.0, 0.0

        try:
            net_io = psutil.net_io_counters()
            current_time = time.time()

            if not self._initialized:
                self._last_bytes_recv = net_io.bytes_recv
                self._last_bytes_sent = net_io.bytes_sent
                self._last_time = current_time
                self._initialized = True
                return 0.0, 0.0

            time_delta = current_time - self._last_time
            if time_delta <= 0:
                return 0.0, 0.0

            # Calculate bytes per second
            bytes_recv_delta = net_io.bytes_recv - self._last_bytes_recv
            bytes_sent_delta = net_io.bytes_sent - self._last_bytes_sent

            # Convert to Mbit/s
            download_mbps = (bytes_recv_delta * 8) / (time_delta * 1_000_000)
            upload_mbps = (bytes_sent_delta * 8) / (time_delta * 1_000_000)

            # Update last values
            self._last_bytes_recv = net_io.bytes_recv
            self._last_bytes_sent = net_io.bytes_sent
            self._last_time = current_time

            return round(download_mbps, 2), round(upload_mbps, 2)

        except Exception as e:
            logger.error(f"Throughput measurement error: {e}")
            return 0.0, 0.0


class NetworkMonitor:
    """
    Monitors network metrics including WiFi signal, latency, jitter, and packet loss
    """

    # Ping targets - Game servers and reliable hosts
    DEFAULT_PING_TARGETS = [
        ("8.8.8.8", "Google DNS"),
        ("1.1.1.1", "Cloudflare DNS"),
        ("208.67.222.222", "OpenDNS"),
    ]

    def __init__(self, ping_target: str = "8.8.8.8", history_size: int = 300):
        self.ping_target = ping_target
        self.history_size = history_size

        # History storage (last 5 minutes at 1/sec)
        self.ping_history: deque = deque(maxlen=history_size)
        self.metrics_history: deque = deque(maxlen=history_size)

        # Throughput monitor for real Mbit/s
        self.throughput_monitor = ThroughputMonitor()

        # Current state
        self.current_metrics: Optional[NetworkMetrics] = None
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None

        # Alert thresholds
        self.thresholds = {
            'ping_warning': 50,      # ms
            'ping_critical': 100,    # ms
            'jitter_warning': 10,    # ms
            'jitter_critical': 30,   # ms
            'packet_loss_warning': 1,  # %
            'packet_loss_critical': 5, # %
            'signal_warning': -70,   # dBm
            'signal_critical': -80,  # dBm
        }

        # Event log
        self.events: deque = deque(maxlen=100)

    def get_wifi_info_windows(self) -> Dict[str, Any]:
        """Get WiFi information using netsh on Windows"""
        wifi_info = {}

        try:
            # Get interface info
            result = subprocess.run(
                ['netsh', 'wlan', 'show', 'interfaces'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            if result.returncode == 0:
                output = result.stdout

                # Parse SSID
                ssid_match = re.search(r'SSID\s*:\s*(.+)', output)
                if ssid_match:
                    wifi_info['ssid'] = ssid_match.group(1).strip()

                # Parse BSSID
                bssid_match = re.search(r'BSSID\s*:\s*(.+)', output)
                if bssid_match:
                    wifi_info['bssid'] = bssid_match.group(1).strip()

                # Parse Signal strength
                signal_match = re.search(r'Signal\s*:\s*(\d+)%', output)
                if signal_match:
                    percent = int(signal_match.group(1))
                    wifi_info['signal_percent'] = percent
                    # Convert to approximate dBm (rough conversion)
                    wifi_info['signal_dbm'] = self._percent_to_dbm(percent)

                # Parse Radio type / Channel
                channel_match = re.search(r'Channel\s*:\s*(\d+)', output)
                if channel_match:
                    wifi_info['channel'] = int(channel_match.group(1))

                # Parse Link speed (Receive/Transmit rate)
                rx_match = re.search(r'Receive rate \(Mbps\)\s*:\s*([\d.]+)', output)
                tx_match = re.search(r'Transmit rate \(Mbps\)\s*:\s*([\d.]+)', output)
                if rx_match:
                    wifi_info['link_speed'] = float(rx_match.group(1))
                elif tx_match:
                    wifi_info['link_speed'] = float(tx_match.group(1))

                # Parse adapter name
                name_match = re.search(r'Name\s*:\s*(.+)', output)
                if name_match:
                    wifi_info['adapter_name'] = name_match.group(1).strip()

                # Check connection state
                state_match = re.search(r'State\s*:\s*(.+)', output)
                if state_match:
                    wifi_info['connected'] = 'connected' in state_match.group(1).lower()

                # Parse frequency band
                band_match = re.search(r'Radio type\s*:\s*(.+)', output)
                if band_match:
                    radio = band_match.group(1).strip()
                    if '5' in radio or 'ac' in radio.lower() or 'ax' in radio.lower():
                        wifi_info['frequency_ghz'] = 5.0
                    else:
                        wifi_info['frequency_ghz'] = 2.4

        except subprocess.TimeoutExpired:
            logger.warning("WiFi info command timed out")
        except Exception as e:
            logger.error(f"Error getting WiFi info: {e}")

        return wifi_info

    def _percent_to_dbm(self, percent: int) -> int:
        """Convert signal percentage to approximate dBm"""
        # Windows reports signal as percentage
        # Rough conversion: 100% ≈ -30dBm, 0% ≈ -100dBm
        return int(-100 + (percent * 0.7))

    def ping(self, target: str = None, count: int = 1, timeout: int = 1000) -> List[PingResult]:
        """
        Perform ping measurement using Windows ping command
        Returns list of PingResult objects
        """
        target = target or self.ping_target
        results = []

        try:
            # Windows ping command
            cmd = ['ping', '-n', str(count), '-w', str(timeout), target]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=timeout/1000 * count + 2,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            output = result.stdout

            # Parse individual ping times (supports German "Zeit=" and English "time=")
            time_matches = re.findall(r'(?:time|Zeit)[=<](\d+)\s*ms', output, re.IGNORECASE)

            for time_str in time_matches:
                results.append(PingResult(
                    timestamp=datetime.now(),
                    latency_ms=float(time_str),
                    success=True,
                    target=target
                ))

            # Check for packet loss (supports German and English)
            loss_match = re.search(r'\((\d+)%\s*(?:loss|Verlust)\)', output, re.IGNORECASE)
            if loss_match:
                loss_percent = int(loss_match.group(1))
                lost_count = int(count * loss_percent / 100)

                # Add failed pings
                for _ in range(lost_count):
                    results.append(PingResult(
                        timestamp=datetime.now(),
                        latency_ms=None,
                        success=False,
                        target=target
                    ))

        except subprocess.TimeoutExpired:
            results.append(PingResult(
                timestamp=datetime.now(),
                latency_ms=None,
                success=False,
                target=target
            ))
        except Exception as e:
            logger.error(f"Ping error: {e}")
            results.append(PingResult(
                timestamp=datetime.now(),
                latency_ms=None,
                success=False,
                target=target
            ))

        return results

    def calculate_jitter(self, latencies: List[float]) -> float:
        """
        Calculate jitter as the average deviation between consecutive pings
        This is the metric that matters most for gaming!
        """
        if len(latencies) < 2:
            return 0.0

        differences = []
        for i in range(1, len(latencies)):
            diff = abs(latencies[i] - latencies[i-1])
            differences.append(diff)

        return statistics.mean(differences) if differences else 0.0

    def collect_metrics(self) -> NetworkMetrics:
        """Collect all network metrics"""
        metrics = NetworkMetrics(timestamp=datetime.now())

        # Get WiFi info
        wifi_info = self.get_wifi_info_windows()

        if wifi_info:
            metrics.ssid = wifi_info.get('ssid')
            metrics.bssid = wifi_info.get('bssid')
            metrics.signal_strength_dbm = wifi_info.get('signal_dbm')
            metrics.signal_percent = wifi_info.get('signal_percent')
            metrics.link_speed_mbps = wifi_info.get('link_speed')
            metrics.channel = wifi_info.get('channel')
            metrics.frequency_ghz = wifi_info.get('frequency_ghz')
            metrics.adapter_name = wifi_info.get('adapter_name')
            metrics.is_connected = wifi_info.get('connected', False)

        # Perform ping burst (5 pings for jitter calculation)
        ping_results = self.ping(count=5, timeout=1000)

        successful_pings = [p for p in ping_results if p.success]
        latencies = [p.latency_ms for p in successful_pings if p.latency_ms]

        metrics.packets_sent = len(ping_results)
        metrics.packets_received = len(successful_pings)

        if ping_results:
            metrics.packet_loss_percent = round(
                (1 - len(successful_pings) / len(ping_results)) * 100, 1
            )

        if latencies:
            metrics.ping_ms = latencies[-1]  # Most recent
            metrics.ping_min_ms = min(latencies)
            metrics.ping_max_ms = max(latencies)
            metrics.ping_avg_ms = statistics.mean(latencies)
            metrics.jitter_ms = round(self.calculate_jitter(latencies), 2)

        # Get actual throughput (Mbit/s)
        metrics.download_mbps, metrics.upload_mbps = self.throughput_monitor.get_throughput()

        # Store in history
        self.ping_history.extend(ping_results)

        # Calculate quality score
        metrics.quality_score, metrics.quality_status = self._calculate_quality(metrics)

        # Check for alerts
        self._check_alerts(metrics)

        self.current_metrics = metrics
        self.metrics_history.append(metrics)

        return metrics

    def _calculate_quality(self, m: NetworkMetrics) -> tuple:
        """Calculate overall connection quality score (0-100)"""
        score = 100

        # Ping penalty
        if m.ping_ms:
            if m.ping_ms > 150:
                score -= 40
            elif m.ping_ms > 100:
                score -= 25
            elif m.ping_ms > 50:
                score -= 10
            elif m.ping_ms > 30:
                score -= 5

        # Jitter penalty (most important for gaming!)
        if m.jitter_ms:
            if m.jitter_ms > 50:
                score -= 40
            elif m.jitter_ms > 30:
                score -= 30
            elif m.jitter_ms > 15:
                score -= 20
            elif m.jitter_ms > 5:
                score -= 10

        # Packet loss penalty (critical!)
        if m.packet_loss_percent > 10:
            score -= 50
        elif m.packet_loss_percent > 5:
            score -= 35
        elif m.packet_loss_percent > 2:
            score -= 25
        elif m.packet_loss_percent > 0:
            score -= 15

        # Signal penalty
        if m.signal_strength_dbm:
            if m.signal_strength_dbm < -80:
                score -= 25
            elif m.signal_strength_dbm < -70:
                score -= 15
            elif m.signal_strength_dbm < -60:
                score -= 5

        score = max(0, min(100, score))

        # Status text
        if score >= 90:
            status = "Excellent"
        elif score >= 75:
            status = "Good"
        elif score >= 50:
            status = "Fair"
        elif score >= 25:
            status = "Poor"
        else:
            status = "Critical"

        return score, status

    def _check_alerts(self, m: NetworkMetrics):
        """Check metrics against thresholds and log events"""
        now = datetime.now()

        # Ping spike
        if m.ping_ms and m.ping_ms > self.thresholds['ping_critical']:
            self.events.append({
                'time': now,
                'type': 'critical',
                'metric': 'ping',
                'message': f'High ping spike: {m.ping_ms:.0f}ms'
            })

        # Jitter spike
        if m.jitter_ms and m.jitter_ms > self.thresholds['jitter_critical']:
            self.events.append({
                'time': now,
                'type': 'critical',
                'metric': 'jitter',
                'message': f'High jitter: {m.jitter_ms:.1f}ms'
            })

        # Packet loss
        if m.packet_loss_percent > self.thresholds['packet_loss_critical']:
            self.events.append({
                'time': now,
                'type': 'critical',
                'metric': 'packet_loss',
                'message': f'Packet loss: {m.packet_loss_percent:.1f}%'
            })

        # Signal drop
        if m.signal_strength_dbm and m.signal_strength_dbm < self.thresholds['signal_critical']:
            self.events.append({
                'time': now,
                'type': 'warning',
                'metric': 'signal',
                'message': f'Weak signal: {m.signal_strength_dbm}dBm'
            })

    def get_history_data(self, seconds: int = 60) -> Dict[str, List]:
        """Get historical data for charts"""
        cutoff = datetime.now().timestamp() - seconds

        data = {
            'timestamps': [],
            'ping': [],
            'jitter': [],
            'packet_loss': [],
            'signal': [],
        }

        for m in self.metrics_history:
            if m.timestamp.timestamp() > cutoff:
                data['timestamps'].append(m.timestamp.strftime('%H:%M:%S'))
                data['ping'].append(m.ping_ms or 0)
                data['jitter'].append(m.jitter_ms or 0)
                data['packet_loss'].append(m.packet_loss_percent)
                data['signal'].append(m.signal_percent or 0)

        return data

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistical summary of recent metrics"""
        recent = list(self.metrics_history)[-60:]  # Last 60 samples

        if not recent:
            return {}

        pings = [m.ping_ms for m in recent if m.ping_ms]
        jitters = [m.jitter_ms for m in recent if m.jitter_ms]
        losses = [m.packet_loss_percent for m in recent]

        stats = {
            'sample_count': len(recent),
            'time_span_seconds': 60,
        }

        if pings:
            stats['ping'] = {
                'min': round(min(pings), 1),
                'max': round(max(pings), 1),
                'avg': round(statistics.mean(pings), 1),
                'std': round(statistics.stdev(pings), 1) if len(pings) > 1 else 0,
            }

        if jitters:
            stats['jitter'] = {
                'min': round(min(jitters), 1),
                'max': round(max(jitters), 1),
                'avg': round(statistics.mean(jitters), 1),
            }

        if losses:
            stats['packet_loss'] = {
                'total_percent': round(statistics.mean(losses), 2),
                'spikes': sum(1 for l in losses if l > 0),
            }

        return stats

    def start_monitoring(self, interval: float = 1.0, history_storage=None):
        """Start continuous monitoring in background thread"""
        if self._running:
            return

        self._running = True
        self._history_storage = history_storage

        def monitor_loop():
            while self._running:
                try:
                    metrics = self.collect_metrics()

                    # Intelligently save to history (checks for changes/events)
                    if self._history_storage:
                        self._history_storage.save_metrics(metrics)
                except Exception as e:
                    logger.error(f"Monitoring error: {e}")
                time.sleep(interval)

        self._monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("Network monitoring started")

    def stop_monitoring(self):
        """Stop background monitoring"""
        self._running = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        logger.info("Network monitoring stopped")


class HistoryStorage:
    """Intelligent persistent storage for long-term network metrics history"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_file = os.path.join(data_dir, 'network_history.json')
        self._ensure_file_exists()

        # State tracking
        self._last_saved_metrics = None
        self._last_regular_save_time = None
        self._write_lock = threading.Lock()

        # Regular save interval (seconds) - for continuous chart data
        self.regular_save_interval = 5

    def _ensure_file_exists(self):
        """Create the data file if it doesn't exist"""
        if not os.path.exists(self.data_file):
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({'records': []}, f)

    def detect_critical_event(self, metrics: NetworkMetrics) -> str:
        """
        Check if this is a critical event that should be saved immediately.
        Returns event type or None.
        """
        if self._last_saved_metrics is None:
            return None

        # Disconnection/Reconnection
        if not metrics.is_connected and self._last_saved_metrics.is_connected:
            return "disconnected"
        if metrics.is_connected and not self._last_saved_metrics.is_connected:
            return "reconnected"

        # Packet loss start/end
        if metrics.packet_loss_percent > 0 and self._last_saved_metrics.packet_loss_percent == 0:
            return "packet_loss_start"
        if metrics.packet_loss_percent == 0 and self._last_saved_metrics.packet_loss_percent > 0:
            return "packet_loss_end"

        # Ping timeout
        if metrics.ping_ms is None and self._last_saved_metrics.ping_ms is not None:
            return "ping_timeout"
        if metrics.ping_ms is not None and self._last_saved_metrics.ping_ms is None:
            return "ping_recovered"

        # High packet loss (>5%)
        if metrics.packet_loss_percent >= 5:
            return "high_packet_loss"

        # Ping spike >100ms
        if metrics.ping_ms and metrics.ping_ms > 100:
            if self._last_saved_metrics.ping_ms and self._last_saved_metrics.ping_ms <= 100:
                return "ping_spike"

        return None

    def save_metrics(self, metrics: NetworkMetrics):
        """
        Save metrics to history.
        - Always saves on critical events (immediately)
        - Regular saves every X seconds for continuous data
        """
        now = datetime.now()
        reason = "regular"

        # Check for critical events first
        critical_event = self.detect_critical_event(metrics)
        if critical_event:
            reason = critical_event

        # Check if it's time for regular save
        is_regular_save_time = False
        if self._last_regular_save_time is None:
            is_regular_save_time = True
            reason = "initial"
        else:
            elapsed = (now - self._last_regular_save_time).total_seconds()
            if elapsed >= self.regular_save_interval:
                is_regular_save_time = True

        # Only save if critical event OR regular interval reached
        if not critical_event and not is_regular_save_time:
            return False

        try:
            record = {
                'timestamp': metrics.timestamp.isoformat(),
                'ping_ms': metrics.ping_ms,
                'jitter_ms': metrics.jitter_ms,
                'packet_loss_percent': metrics.packet_loss_percent,
                'signal_percent': metrics.signal_percent,
                'signal_dbm': metrics.signal_strength_dbm,
                'quality_score': metrics.quality_score,
                'download_mbps': metrics.download_mbps,
                'upload_mbps': metrics.upload_mbps,
                'connected': metrics.is_connected,
                'reason': reason,
            }

            with self._write_lock:
                data = self._read_data()
                data['records'].append(record)

                # Keep max 100000 records
                if len(data['records']) > 100000:
                    data['records'] = data['records'][-100000:]

                with open(self.data_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f)

            self._last_saved_metrics = metrics
            self._last_regular_save_time = now

            if critical_event:
                logger.warning(f"[EVENT] {reason}: ping={metrics.ping_ms}ms, loss={metrics.packet_loss_percent}%, connected={metrics.is_connected}")
            else:
                logger.debug(f"History saved: ping={metrics.ping_ms}ms, loss={metrics.packet_loss_percent}%")

            return True

        except Exception as e:
            logger.error(f"Error saving metrics: {e}")
            return False

    def _read_data(self) -> Dict:
        """Read data from file"""
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {'records': []}

    def get_history(self, period: str = 'day') -> Dict[str, List]:
        """
        Get historical data for a specific period.
        period: 'day' (last 24h), 'week' (last 7 days), 'month' (last 30 days)
        """
        data = self._read_data()
        records = data.get('records', [])

        now = datetime.now()
        if period == 'day':
            cutoff = now - timedelta(hours=24)
            aggregate = False  # Show ALL records for day view
        elif period == 'week':
            cutoff = now - timedelta(days=7)
            aggregate = True
            interval_minutes = 5  # 5 min intervals for week
        elif period == 'month':
            cutoff = now - timedelta(days=30)
            aggregate = True
            interval_minutes = 30  # 30 min intervals for month
        else:
            cutoff = now - timedelta(hours=24)
            aggregate = False

        cutoff_iso = cutoff.isoformat()

        # Filter records by time
        filtered = [r for r in records if r['timestamp'] >= cutoff_iso]

        # Aggregate if needed (but preserve max values for packet_loss!)
        if aggregate:
            filtered = self._aggregate_records_smart(filtered, interval_minutes)

        # Build response
        result = {
            'timestamps': [],
            'ping': [],
            'jitter': [],
            'packet_loss': [],
            'signal': [],
            'quality': [],
            'download': [],
            'upload': [],
        }

        for r in filtered:
            # Format timestamp based on period
            try:
                ts = datetime.fromisoformat(r['timestamp'])
                if period == 'day':
                    ts_str = ts.strftime('%H:%M:%S')  # Include seconds for precision
                elif period == 'week':
                    ts_str = ts.strftime('%a %H:%M')
                else:
                    ts_str = ts.strftime('%d.%m %H:%M')
            except:
                ts_str = r['timestamp']

            result['timestamps'].append(ts_str)
            result['ping'].append(r.get('ping_ms') or 0)
            result['jitter'].append(r.get('jitter_ms') or 0)
            result['packet_loss'].append(r.get('packet_loss_percent') or 0)
            result['signal'].append(r.get('signal_percent') or 0)
            result['quality'].append(r.get('quality_score') or 0)
            result['download'].append(r.get('download_mbps') or 0)
            result['upload'].append(r.get('upload_mbps') or 0)

        return result

    def _aggregate_records_smart(self, records: List[Dict], interval_minutes: int) -> List[Dict]:
        """
        Aggregate records but preserve important events.
        Uses MAX for packet_loss (don't hide spikes!) and AVG for others.
        """
        if not records:
            return []

        aggregated = []
        bucket = []
        bucket_start = None

        for r in records:
            try:
                ts = datetime.fromisoformat(r['timestamp'])
            except:
                continue

            if bucket_start is None:
                bucket_start = ts

            if (ts - bucket_start).total_seconds() < interval_minutes * 60:
                bucket.append(r)
            else:
                if bucket:
                    aggregated.append(self._smart_bucket(bucket))
                bucket = [r]
                bucket_start = ts

        if bucket:
            aggregated.append(self._smart_bucket(bucket))

        return aggregated

    def calculate_longterm_score(self, period: str = 'day') -> Dict:
        """
        Calculate a long-term connection quality score based on historical data.

        Factors weighted by importance for gaming/stability:
        - Packet Loss Events (40%) - Most critical
        - Ping Stability (25%) - Average and spikes
        - Connection Stability (20%) - Disconnects/reconnects
        - Jitter (15%) - Consistency

        Returns dict with score, grade, and detailed breakdown.
        """
        data = self._read_data()
        records = data.get('records', [])

        if not records:
            return {
                'score': 0,
                'grade': 'N/A',
                'message': 'Keine Daten verfügbar',
                'details': {},
                'period': period,
                'record_count': 0
            }

        # Filter by period
        now = datetime.now()
        if period == 'day':
            cutoff = now - timedelta(hours=24)
            period_label = "24 Stunden"
        elif period == 'week':
            cutoff = now - timedelta(days=7)
            period_label = "7 Tage"
        elif period == 'month':
            cutoff = now - timedelta(days=30)
            period_label = "30 Tage"
        else:
            cutoff = now - timedelta(hours=24)
            period_label = "24 Stunden"

        cutoff_iso = cutoff.isoformat()
        filtered = [r for r in records if r['timestamp'] >= cutoff_iso]

        if not filtered:
            return {
                'score': 0,
                'grade': 'N/A',
                'message': f'Keine Daten für {period_label}',
                'details': {},
                'period': period,
                'record_count': 0
            }

        # Extract metrics
        pings = [r.get('ping_ms') for r in filtered if r.get('ping_ms') is not None]
        jitters = [r.get('jitter_ms') for r in filtered if r.get('jitter_ms') is not None]
        losses = [r.get('packet_loss_percent', 0) for r in filtered]
        qualities = [r.get('quality_score', 100) for r in filtered]

        # Count events
        disconnect_count = sum(1 for r in filtered if r.get('reason') == 'disconnected')
        packet_loss_events = sum(1 for r in filtered if r.get('reason') in ['packet_loss_start', 'high_packet_loss'])
        ping_spike_events = sum(1 for r in filtered if r.get('reason') == 'ping_spike')

        # Calculate time span in hours
        try:
            first_ts = datetime.fromisoformat(filtered[0]['timestamp'])
            last_ts = datetime.fromisoformat(filtered[-1]['timestamp'])
            hours_span = max((last_ts - first_ts).total_seconds() / 3600, 1)
        except:
            hours_span = 1

        # ============ SCORING ============

        # 1. PACKET LOSS SCORE (40% weight)
        # Perfect: 0 events, Terrible: >10 events per 24h
        loss_events_per_day = (packet_loss_events / hours_span) * 24
        if loss_events_per_day == 0:
            packet_loss_score = 100
        elif loss_events_per_day <= 1:
            packet_loss_score = 90
        elif loss_events_per_day <= 3:
            packet_loss_score = 75
        elif loss_events_per_day <= 5:
            packet_loss_score = 60
        elif loss_events_per_day <= 10:
            packet_loss_score = 40
        else:
            packet_loss_score = max(0, 20 - loss_events_per_day)

        # Also factor in average loss percentage
        avg_loss = sum(losses) / len(losses) if losses else 0
        if avg_loss > 5:
            packet_loss_score = min(packet_loss_score, 30)
        elif avg_loss > 2:
            packet_loss_score = min(packet_loss_score, 50)
        elif avg_loss > 0.5:
            packet_loss_score = min(packet_loss_score, 70)

        # 2. PING STABILITY SCORE (25% weight)
        if pings:
            avg_ping = sum(pings) / len(pings)
            max_ping = max(pings)
            ping_std = (sum((p - avg_ping) ** 2 for p in pings) / len(pings)) ** 0.5

            # Base score from average ping
            if avg_ping <= 20:
                ping_score = 100
            elif avg_ping <= 30:
                ping_score = 95
            elif avg_ping <= 50:
                ping_score = 85
            elif avg_ping <= 80:
                ping_score = 70
            elif avg_ping <= 100:
                ping_score = 55
            else:
                ping_score = max(0, 40 - (avg_ping - 100) / 5)

            # Penalty for high variance (unstable ping)
            if ping_std > 50:
                ping_score -= 30
            elif ping_std > 30:
                ping_score -= 20
            elif ping_std > 15:
                ping_score -= 10

            # Penalty for extreme spikes
            spike_ratio = ping_spike_events / max(len(filtered), 1) * 100
            if spike_ratio > 5:
                ping_score -= 25
            elif spike_ratio > 2:
                ping_score -= 15
            elif spike_ratio > 0.5:
                ping_score -= 5

            ping_score = max(0, min(100, ping_score))
        else:
            ping_score = 0
            avg_ping = 0
            max_ping = 0
            ping_std = 0

        # 3. CONNECTION STABILITY SCORE (20% weight)
        disconnects_per_day = (disconnect_count / hours_span) * 24
        if disconnects_per_day == 0:
            connection_score = 100
        elif disconnects_per_day <= 0.5:
            connection_score = 90
        elif disconnects_per_day <= 1:
            connection_score = 75
        elif disconnects_per_day <= 2:
            connection_score = 60
        elif disconnects_per_day <= 5:
            connection_score = 40
        else:
            connection_score = max(0, 20 - disconnects_per_day * 2)

        # 4. JITTER SCORE (15% weight)
        if jitters:
            avg_jitter = sum(jitters) / len(jitters)
            max_jitter = max(jitters)

            if avg_jitter <= 3:
                jitter_score = 100
            elif avg_jitter <= 5:
                jitter_score = 95
            elif avg_jitter <= 10:
                jitter_score = 85
            elif avg_jitter <= 20:
                jitter_score = 70
            elif avg_jitter <= 30:
                jitter_score = 50
            else:
                jitter_score = max(0, 30 - avg_jitter)

            # Penalty for extreme jitter spikes
            if max_jitter > 100:
                jitter_score -= 20
            elif max_jitter > 50:
                jitter_score -= 10

            jitter_score = max(0, min(100, jitter_score))
        else:
            jitter_score = 0
            avg_jitter = 0
            max_jitter = 0

        # ============ FINAL SCORE ============
        final_score = int(
            packet_loss_score * 0.40 +
            ping_score * 0.25 +
            connection_score * 0.20 +
            jitter_score * 0.15
        )

        # Determine grade
        if final_score >= 95:
            grade = 'A+'
            message = 'Exzellente Verbindung'
        elif final_score >= 90:
            grade = 'A'
            message = 'Sehr gute Verbindung'
        elif final_score >= 85:
            grade = 'B+'
            message = 'Gute Verbindung'
        elif final_score >= 80:
            grade = 'B'
            message = 'Solide Verbindung'
        elif final_score >= 70:
            grade = 'C+'
            message = 'Akzeptable Verbindung'
        elif final_score >= 60:
            grade = 'C'
            message = 'Mäßige Verbindung'
        elif final_score >= 50:
            grade = 'D'
            message = 'Problematische Verbindung'
        elif final_score >= 30:
            grade = 'E'
            message = 'Schlechte Verbindung'
        else:
            grade = 'F'
            message = 'Unbrauchbare Verbindung'

        return {
            'score': final_score,
            'grade': grade,
            'message': message,
            'period': period,
            'period_label': period_label,
            'record_count': len(filtered),
            'hours_analyzed': round(hours_span, 1),
            'details': {
                'packet_loss': {
                    'score': int(packet_loss_score),
                    'weight': '40%',
                    'events': packet_loss_events,
                    'events_per_day': round(loss_events_per_day, 1),
                    'avg_percent': round(avg_loss, 2)
                },
                'ping': {
                    'score': int(ping_score),
                    'weight': '25%',
                    'avg_ms': round(avg_ping, 1),
                    'max_ms': round(max_ping, 1) if pings else 0,
                    'std_dev': round(ping_std, 1) if pings else 0,
                    'spike_events': ping_spike_events
                },
                'connection': {
                    'score': int(connection_score),
                    'weight': '20%',
                    'disconnects': disconnect_count,
                    'disconnects_per_day': round(disconnects_per_day, 1)
                },
                'jitter': {
                    'score': int(jitter_score),
                    'weight': '15%',
                    'avg_ms': round(avg_jitter, 1) if jitters else 0,
                    'max_ms': round(max_jitter, 1) if jitters else 0
                }
            }
        }

    def _smart_bucket(self, records: List[Dict]) -> Dict:
        """
        Smart aggregation: MAX for problems, AVG for normal metrics.
        """
        if not records:
            return {}

        def safe_avg(values):
            valid = [v for v in values if v is not None]
            return round(sum(valid) / len(valid), 2) if valid else 0

        def safe_max(values):
            valid = [v for v in values if v is not None]
            return max(valid) if valid else 0

        def safe_min(values):
            valid = [v for v in values if v is not None]
            return min(valid) if valid else 0

        return {
            'timestamp': records[len(records)//2]['timestamp'],
            'ping_ms': safe_max([r.get('ping_ms') for r in records]),  # MAX - show worst
            'jitter_ms': safe_max([r.get('jitter_ms') for r in records]),  # MAX
            'packet_loss_percent': safe_max([r.get('packet_loss_percent') for r in records]),  # MAX - critical!
            'signal_percent': safe_min([r.get('signal_percent') for r in records]),  # MIN - show worst
            'quality_score': safe_min([r.get('quality_score') for r in records]),  # MIN - show worst
            'download_mbps': safe_avg([r.get('download_mbps') for r in records]),
            'upload_mbps': safe_avg([r.get('upload_mbps') for r in records]),
        }



# Singleton instance
_monitor_instance: Optional[NetworkMonitor] = None
_history_storage: Optional[HistoryStorage] = None

def get_monitor() -> NetworkMonitor:
    """Get or create the network monitor singleton"""
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = NetworkMonitor()
    return _monitor_instance

def get_history_storage() -> HistoryStorage:
    """Get or create the history storage singleton"""
    global _history_storage
    if _history_storage is None:
        _history_storage = HistoryStorage()
    return _history_storage


if __name__ == "__main__":
    # Test the monitor
    monitor = NetworkMonitor()

    print("Testing WiFi info...")
    wifi = monitor.get_wifi_info_windows()
    print(f"WiFi: {wifi}")

    print("\nTesting ping...")
    results = monitor.ping(count=5)
    for r in results:
        print(f"  {r}")

    print("\nCollecting full metrics...")
    metrics = monitor.collect_metrics()
    print(f"Signal: {metrics.signal_percent}% ({metrics.signal_strength_dbm}dBm)")
    print(f"Ping: {metrics.ping_ms}ms (jitter: {metrics.jitter_ms}ms)")
    print(f"Packet Loss: {metrics.packet_loss_percent}%")
    print(f"Quality: {metrics.quality_score}/100 ({metrics.quality_status})")

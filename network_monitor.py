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

    def start_monitoring(self, interval: float = 1.0):
        """Start continuous monitoring in background thread"""
        if self._running:
            return

        self._running = True

        def monitor_loop():
            while self._running:
                try:
                    self.collect_metrics()
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
    """Persistent storage for long-term network metrics history"""

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            data_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_file = os.path.join(data_dir, 'network_history.json')
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create the data file if it doesn't exist"""
        if not os.path.exists(self.data_file):
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump({'records': []}, f)

    def save_metrics(self, metrics: NetworkMetrics):
        """Save a metrics snapshot to persistent storage"""
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
            }

            # Read existing data
            data = self._read_data()
            data['records'].append(record)

            # Keep only last 30 days of data (assuming ~1 record per minute = ~43200 records)
            max_records = 43200
            if len(data['records']) > max_records:
                data['records'] = data['records'][-max_records:]

            # Write back
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f)

        except Exception as e:
            logger.error(f"Error saving metrics to history: {e}")

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
            interval_minutes = 1  # Show every record
        elif period == 'week':
            cutoff = now - timedelta(days=7)
            interval_minutes = 15  # Aggregate every 15 minutes
        elif period == 'month':
            cutoff = now - timedelta(days=30)
            interval_minutes = 60  # Aggregate every hour
        else:
            cutoff = now - timedelta(hours=24)
            interval_minutes = 1

        cutoff_iso = cutoff.isoformat()

        # Filter records by time
        filtered = [r for r in records if r['timestamp'] >= cutoff_iso]

        # Aggregate if needed
        if interval_minutes > 1:
            filtered = self._aggregate_records(filtered, interval_minutes)

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
                    ts_str = ts.strftime('%H:%M')
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

    def _aggregate_records(self, records: List[Dict], interval_minutes: int) -> List[Dict]:
        """Aggregate records into intervals"""
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

            # Check if still in same bucket
            if (ts - bucket_start).total_seconds() < interval_minutes * 60:
                bucket.append(r)
            else:
                # Finalize bucket
                if bucket:
                    aggregated.append(self._average_bucket(bucket))
                bucket = [r]
                bucket_start = ts

        # Don't forget last bucket
        if bucket:
            aggregated.append(self._average_bucket(bucket))

        return aggregated

    def _average_bucket(self, records: List[Dict]) -> Dict:
        """Calculate average values for a bucket of records"""
        if not records:
            return {}

        def safe_avg(values):
            valid = [v for v in values if v is not None]
            return round(sum(valid) / len(valid), 2) if valid else None

        return {
            'timestamp': records[len(records)//2]['timestamp'],  # Use middle timestamp
            'ping_ms': safe_avg([r.get('ping_ms') for r in records]),
            'jitter_ms': safe_avg([r.get('jitter_ms') for r in records]),
            'packet_loss_percent': safe_avg([r.get('packet_loss_percent') for r in records]),
            'signal_percent': safe_avg([r.get('signal_percent') for r in records]),
            'quality_score': safe_avg([r.get('quality_score') for r in records]),
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

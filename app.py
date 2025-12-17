"""
WiFi Gaming Monitor - Flask Web Application
Professional network monitoring dashboard for gaming diagnostics
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template, jsonify, request, Response
from network_monitor import get_monitor, get_history_storage, NetworkMonitor

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Initialize monitor and history storage
monitor = get_monitor()
history_storage = get_history_storage()


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('index.html')


@app.route('/api/metrics')
def api_metrics():
    """Get current metrics as JSON"""
    metrics = monitor.current_metrics
    if not metrics:
        metrics = monitor.collect_metrics()

    return jsonify({
        'timestamp': metrics.timestamp.isoformat(),
        'wifi': {
            'ssid': metrics.ssid,
            'signal_percent': metrics.signal_percent,
            'signal_dbm': metrics.signal_strength_dbm,
            'link_speed': metrics.link_speed_mbps,
            'channel': metrics.channel,
            'frequency': metrics.frequency_ghz,
            'connected': metrics.is_connected,
        },
        'latency': {
            'ping': metrics.ping_ms,
            'ping_min': metrics.ping_min_ms,
            'ping_max': metrics.ping_max_ms,
            'ping_avg': metrics.ping_avg_ms,
            'jitter': metrics.jitter_ms,
        },
        'packets': {
            'sent': metrics.packets_sent,
            'received': metrics.packets_received,
            'loss_percent': metrics.packet_loss_percent,
        },
        'quality': {
            'score': metrics.quality_score,
            'status': metrics.quality_status,
        }
    })


@app.route('/api/history')
def api_history():
    """Get historical data for charts"""
    seconds = request.args.get('seconds', 60, type=int)
    data = monitor.get_history_data(seconds=seconds)
    return jsonify(data)


@app.route('/api/statistics')
def api_statistics():
    """Get statistical summary"""
    stats = monitor.get_statistics()
    return jsonify(stats)


@app.route('/api/long-term-history')
def api_long_term_history():
    """Get long-term historical data for charts"""
    period = request.args.get('period', 'day')  # day, week, month
    if period not in ['day', 'week', 'month']:
        period = 'day'
    data = history_storage.get_history(period=period)
    return jsonify(data)


@app.route('/api/events')
def api_events():
    """Get recent events/alerts"""
    events = list(monitor.events)[-20:]  # Last 20 events
    return jsonify([{
        'time': e['time'].strftime('%H:%M:%S'),
        'type': e['type'],
        'metric': e['metric'],
        'message': e['message']
    } for e in events])


@app.route('/api/ping-target', methods=['POST'])
def set_ping_target():
    """Update ping target"""
    data = request.get_json()
    target = data.get('target', '8.8.8.8')
    monitor.ping_target = target
    return jsonify({'status': 'ok', 'target': target})


# HTMX Partials

@app.route('/partials/metrics')
def partial_metrics():
    """HTMX partial: Current metrics cards"""
    metrics = monitor.current_metrics
    if not metrics:
        metrics = monitor.collect_metrics()
    return render_template('partials/metrics.html', metrics=metrics)


@app.route('/partials/quality')
def partial_quality():
    """HTMX partial: Quality indicator"""
    metrics = monitor.current_metrics
    if not metrics:
        metrics = monitor.collect_metrics()
    return render_template('partials/quality.html', metrics=metrics)


@app.route('/partials/events')
def partial_events():
    """HTMX partial: Event log"""
    events = list(monitor.events)[-10:]
    return render_template('partials/events.html', events=events)


@app.route('/partials/stats')
def partial_stats():
    """HTMX partial: Statistics summary"""
    stats = monitor.get_statistics()
    return render_template('partials/stats.html', stats=stats)


# SSE for real-time updates
@app.route('/stream')
def stream():
    """Server-Sent Events for real-time metric updates"""
    def generate():
        while True:
            metrics = monitor.current_metrics
            if metrics:
                data = {
                    'ping': metrics.ping_ms,
                    'jitter': metrics.jitter_ms,
                    'loss': metrics.packet_loss_percent,
                    'signal': metrics.signal_percent,
                    'quality': metrics.quality_score,
                    'status': metrics.quality_status,
                }
                yield f"data: {json.dumps(data)}\n\n"

            import time
            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream')


def start_server(host='127.0.0.1', port=5555, debug=False):
    """Start the Flask server and monitoring"""
    # Start background monitoring with history storage
    monitor.start_monitoring(interval=1.0, history_storage=history_storage)

    # Save initial metrics immediately for testing
    import time
    time.sleep(2)  # Wait for first metrics
    if monitor.current_metrics:
        history_storage.save_metrics(monitor.current_metrics)
        print("  [OK] Initial metrics saved to history")

    print(f"\n{'='*60}")
    print("  WiFi Gaming Monitor - Web Dashboard")
    print(f"{'='*60}")
    print(f"  Dashboard: http://{host}:{port}")
    print(f"  API:       http://{host}:{port}/api/metrics")
    print(f"{'='*60}\n")

    try:
        app.run(host=host, port=port, debug=debug, threaded=True)
    finally:
        monitor.stop_monitoring()


if __name__ == '__main__':
    start_server(debug=True)

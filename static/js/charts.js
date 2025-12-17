/**
 * WiFi Gaming Monitor - Chart Configuration
 */

// Chart.js defaults for dark theme
Chart.defaults.color = '#a0a0b0';
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.05)';
Chart.defaults.font.family = "'Inter', sans-serif";

// Latency & Jitter Chart
let latencyChart;
let lossChart;

const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
        duration: 300
    },
    interaction: {
        intersect: false,
        mode: 'index'
    },
    plugins: {
        legend: {
            position: 'top',
            labels: {
                boxWidth: 12,
                padding: 15,
                usePointStyle: true
            }
        },
        tooltip: {
            backgroundColor: 'rgba(26, 26, 36, 0.95)',
            titleColor: '#ffffff',
            bodyColor: '#a0a0b0',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            padding: 12,
            cornerRadius: 8
        }
    },
    scales: {
        x: {
            grid: {
                display: false
            },
            ticks: {
                maxTicksLimit: 10,
                font: {
                    size: 10
                }
            }
        },
        y: {
            beginAtZero: true,
            grid: {
                color: 'rgba(255, 255, 255, 0.03)'
            },
            ticks: {
                font: {
                    size: 10
                }
            }
        }
    }
};

function initCharts() {
    // Latency Chart
    const latencyCtx = document.getElementById('latencyChart');
    if (latencyCtx) {
        latencyChart = new Chart(latencyCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Ping (ms)',
                        data: [],
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    },
                    {
                        label: 'Jitter (ms)',
                        data: [],
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4
                    }
                ]
            },
            options: {
                ...chartOptions,
                scales: {
                    ...chartOptions.scales,
                    y: {
                        ...chartOptions.scales.y,
                        title: {
                            display: true,
                            text: 'Milliseconds',
                            font: { size: 11 }
                        }
                    }
                }
            }
        });
    }

    // Packet Loss Chart
    const lossCtx = document.getElementById('lossChart');
    if (lossCtx) {
        lossChart = new Chart(lossCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Packet Loss (%)',
                        data: [],
                        backgroundColor: function(context) {
                            const value = context.raw || 0;
                            if (value > 5) return 'rgba(239, 68, 68, 0.8)';
                            if (value > 1) return 'rgba(245, 158, 11, 0.8)';
                            if (value > 0) return 'rgba(245, 158, 11, 0.5)';
                            return 'rgba(16, 185, 129, 0.3)';
                        },
                        borderRadius: 4,
                        barThickness: 'flex',
                        maxBarThickness: 8
                    }
                ]
            },
            options: {
                ...chartOptions,
                plugins: {
                    ...chartOptions.plugins,
                    legend: {
                        display: false
                    }
                },
                scales: {
                    ...chartOptions.scales,
                    y: {
                        ...chartOptions.scales.y,
                        max: 10,
                        title: {
                            display: true,
                            text: 'Percent',
                            font: { size: 11 }
                        }
                    }
                }
            }
        });
    }
}

async function updateCharts() {
    try {
        const response = await fetch('/api/history?seconds=60');
        const data = await response.json();

        if (latencyChart && data.timestamps.length > 0) {
            latencyChart.data.labels = data.timestamps;
            latencyChart.data.datasets[0].data = data.ping;
            latencyChart.data.datasets[1].data = data.jitter;
            latencyChart.update('none');
        }

        if (lossChart && data.timestamps.length > 0) {
            lossChart.data.labels = data.timestamps;
            lossChart.data.datasets[0].data = data.packet_loss;
            lossChart.update('none');
        }
    } catch (error) {
        console.error('Error updating charts:', error);
    }
}

// Long-term history charts
let historyPingChart;
let historyQualityChart;
let historyLossChart;
let historySignalChart;
let currentPeriod = 'day';

const historyChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    animation: {
        duration: 500
    },
    interaction: {
        intersect: false,
        mode: 'index'
    },
    plugins: {
        legend: {
            position: 'top',
            labels: {
                boxWidth: 12,
                padding: 10,
                usePointStyle: true,
                font: { size: 10 }
            }
        },
        tooltip: {
            backgroundColor: 'rgba(26, 26, 36, 0.95)',
            titleColor: '#ffffff',
            bodyColor: '#a0a0b0',
            borderColor: 'rgba(255, 255, 255, 0.1)',
            borderWidth: 1,
            padding: 10,
            cornerRadius: 6
        }
    },
    scales: {
        x: {
            grid: { display: false },
            ticks: {
                maxTicksLimit: 8,
                font: { size: 9 },
                maxRotation: 45
            }
        },
        y: {
            beginAtZero: true,
            grid: { color: 'rgba(255, 255, 255, 0.03)' },
            ticks: { font: { size: 9 } }
        }
    }
};

function initHistoryCharts() {
    // Ping & Jitter History Chart
    const pingCtx = document.getElementById('historyPingChart');
    if (pingCtx) {
        historyPingChart = new Chart(pingCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Ping (ms)',
                        data: [],
                        borderColor: '#6366f1',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0
                    },
                    {
                        label: 'Jitter (ms)',
                        data: [],
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.05)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0
                    }
                ]
            },
            options: historyChartOptions
        });
    }

    // Quality Score History Chart
    const qualityCtx = document.getElementById('historyQualityChart');
    if (qualityCtx) {
        historyQualityChart = new Chart(qualityCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Quality Score',
                        data: [],
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                ...historyChartOptions,
                scales: {
                    ...historyChartOptions.scales,
                    y: {
                        ...historyChartOptions.scales.y,
                        max: 100,
                        min: 0
                    }
                }
            }
        });
    }

    // Packet Loss History Chart
    const lossCtx = document.getElementById('historyLossChart');
    if (lossCtx) {
        historyLossChart = new Chart(lossCtx, {
            type: 'bar',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Packet Loss (%)',
                        data: [],
                        backgroundColor: function(context) {
                            const value = context.raw || 0;
                            if (value > 5) return 'rgba(239, 68, 68, 0.8)';
                            if (value > 1) return 'rgba(245, 158, 11, 0.8)';
                            if (value > 0) return 'rgba(245, 158, 11, 0.5)';
                            return 'rgba(16, 185, 129, 0.3)';
                        },
                        borderRadius: 2,
                        barThickness: 'flex'
                    }
                ]
            },
            options: {
                ...historyChartOptions,
                plugins: {
                    ...historyChartOptions.plugins,
                    legend: { display: false }
                }
            }
        });
    }

    // Signal Strength History Chart
    const signalCtx = document.getElementById('historySignalChart');
    if (signalCtx) {
        historySignalChart = new Chart(signalCtx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [
                    {
                        label: 'Signal (%)',
                        data: [],
                        borderColor: '#3b82f6',
                        backgroundColor: 'rgba(59, 130, 246, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                ...historyChartOptions,
                scales: {
                    ...historyChartOptions.scales,
                    y: {
                        ...historyChartOptions.scales.y,
                        max: 100,
                        min: 0
                    }
                }
            }
        });
    }
}

async function updateHistoryCharts(period = null) {
    if (period) {
        currentPeriod = period;
    }

    try {
        const response = await fetch(`/api/long-term-history?period=${currentPeriod}`);
        const data = await response.json();

        if (historyPingChart && data.timestamps.length > 0) {
            historyPingChart.data.labels = data.timestamps;
            historyPingChart.data.datasets[0].data = data.ping;
            historyPingChart.data.datasets[1].data = data.jitter;
            historyPingChart.update('none');
        }

        if (historyQualityChart && data.timestamps.length > 0) {
            historyQualityChart.data.labels = data.timestamps;
            historyQualityChart.data.datasets[0].data = data.quality;
            historyQualityChart.update('none');
        }

        if (historyLossChart && data.timestamps.length > 0) {
            historyLossChart.data.labels = data.timestamps;
            historyLossChart.data.datasets[0].data = data.packet_loss;
            historyLossChart.update('none');
        }

        if (historySignalChart && data.timestamps.length > 0) {
            historySignalChart.data.labels = data.timestamps;
            historySignalChart.data.datasets[0].data = data.signal;
            historySignalChart.update('none');
        }
    } catch (error) {
        console.error('Error updating history charts:', error);
    }
}

async function updateLongtermScore(period = null) {
    if (period) {
        currentPeriod = period;
    }

    try {
        const response = await fetch(`/api/longterm-score?period=${currentPeriod}`);
        const data = await response.json();

        // Update grade
        const gradeEl = document.getElementById('lt-grade');
        gradeEl.textContent = data.grade;
        gradeEl.className = 'score-grade';
        if (data.grade.startsWith('A')) gradeEl.classList.add('grade-a');
        else if (data.grade.startsWith('B')) gradeEl.classList.add('grade-b');
        else if (data.grade.startsWith('C')) gradeEl.classList.add('grade-c');
        else if (data.grade === 'D') gradeEl.classList.add('grade-d');
        else gradeEl.classList.add('grade-e');

        // Update score
        document.getElementById('lt-score').textContent = data.score;
        document.getElementById('lt-message').textContent = data.message;

        // Update detail bars
        if (data.details) {
            updateDetailBar('lt-loss', data.details.packet_loss?.score || 0);
            updateDetailBar('lt-ping', data.details.ping?.score || 0);
            updateDetailBar('lt-conn', data.details.connection?.score || 0);
            updateDetailBar('lt-jitter', data.details.jitter?.score || 0);
        }

        // Update stats
        const statsEl = document.getElementById('lt-stats');
        if (data.details) {
            statsEl.innerHTML = `
                <div><strong>${data.record_count}</strong> Messungen</div>
                <div><strong>${data.hours_analyzed}h</strong> analysiert</div>
                <div>Ping: <strong>${data.details.ping?.avg_ms || 0}ms</strong> avg</div>
                <div>Loss Events: <strong>${data.details.packet_loss?.events || 0}</strong></div>
            `;
        }
    } catch (error) {
        console.error('Error updating longterm score:', error);
    }
}

function updateDetailBar(prefix, score) {
    const bar = document.getElementById(`${prefix}-bar`);
    const value = document.getElementById(`${prefix}-score`);

    if (bar && value) {
        bar.style.width = `${score}%`;
        value.textContent = score;

        bar.className = 'detail-fill';
        if (score >= 80) bar.classList.add('score-high');
        else if (score >= 50) bar.classList.add('score-mid');
        else bar.classList.add('score-low');
    }
}

function initPeriodSelector() {
    const buttons = document.querySelectorAll('.period-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', function() {
            // Update active state
            buttons.forEach(b => b.classList.remove('active'));
            this.classList.add('active');

            // Update charts AND score
            const period = this.dataset.period;
            updateHistoryCharts(period);
            updateLongtermScore(period);
        });
    });
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initCharts();
    initHistoryCharts();
    initPeriodSelector();

    // Update real-time charts every second
    setInterval(updateCharts, 1000);

    // Update history charts and score every 60 seconds
    setInterval(function() {
        updateHistoryCharts();
        updateLongtermScore();
    }, 60000);

    // Initial updates
    setTimeout(updateCharts, 500);
    setTimeout(updateHistoryCharts, 1000);
    setTimeout(updateLongtermScore, 1500);
});

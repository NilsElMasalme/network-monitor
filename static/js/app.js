/**
 * WiFi Gaming Monitor - Application Logic
 */

// Update current time in footer
function updateTime() {
    const timeElement = document.getElementById('current-time');
    if (timeElement) {
        const now = new Date();
        timeElement.textContent = now.toLocaleTimeString('de-DE');
    }
}

// Update ping target
async function updatePingTarget(target) {
    try {
        const response = await fetch('/api/ping-target', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ target: target })
        });
        const data = await response.json();
        console.log('Ping target updated:', data.target);
    } catch (error) {
        console.error('Error updating ping target:', error);
    }
}

// Launch desktop overlay
function launchOverlay() {
    alert('To launch the desktop overlay, run:\n\npython overlay.py\n\nfrom the command line.');
}

// Sound alert for critical events (optional)
let audioContext = null;

function playAlertSound() {
    if (!audioContext) {
        audioContext = new (window.AudioContext || window.webkitAudioContext)();
    }

    const oscillator = audioContext.createOscillator();
    const gainNode = audioContext.createGain();

    oscillator.connect(gainNode);
    gainNode.connect(audioContext.destination);

    oscillator.frequency.value = 440;
    oscillator.type = 'sine';

    gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
    gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.3);

    oscillator.start(audioContext.currentTime);
    oscillator.stop(audioContext.currentTime + 0.3);
}

// Monitor for critical events
let lastQualityScore = 100;

function checkForAlerts(score) {
    if (lastQualityScore >= 50 && score < 50) {
        // Quality dropped below 50 - play alert
        // playAlertSound(); // Uncomment to enable
        console.warn('Connection quality dropped to:', score);
    }
    lastQualityScore = score;
}

// HTMX event listeners
document.addEventListener('htmx:afterSwap', function(event) {
    // Check for quality changes
    const qualityScore = document.querySelector('.quality-score');
    if (qualityScore && event.target.id === 'quality-display') {
        const score = parseInt(qualityScore.textContent) || 100;
        checkForAlerts(score);
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', function(event) {
    // R - Refresh metrics
    if (event.key === 'r' && !event.ctrlKey && !event.metaKey) {
        htmx.trigger('#metrics-grid', 'htmx:trigger');
    }

    // O - Open overlay info
    if (event.key === 'o' && !event.ctrlKey && !event.metaKey) {
        launchOverlay();
    }
});

// Initialize
document.addEventListener('DOMContentLoaded', function() {
    // Update time every second
    updateTime();
    setInterval(updateTime, 1000);

    // Log startup
    console.log('WiFi Gaming Monitor initialized');
    console.log('Keyboard shortcuts: R = Refresh, O = Overlay info');
});

// Handle visibility change (pause updates when tab is hidden)
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        console.log('Tab hidden - updates continue in background');
    } else {
        console.log('Tab visible - resuming normal updates');
        // Force refresh when tab becomes visible again
        htmx.trigger('#metrics-grid', 'htmx:trigger');
    }
});

/**
 * 🤖 ml_signals.js — ML Signal Integration for Frontend
 * =============================================================================
 * Integrates ML signals from Python backend into the chart:
 * - Fetches signals from get_ml_signal() endpoint
 * - Displays on chart via SignalBus
 * - Provides UI for model training
 *
 * Dependencies: eel.js, signals.js (SignalBus), datafeed.js (AppState)
 */

const MLSignals = {
    enabled: true,
    training: false,
    updateInterval: null,
    updateFrequency: 10000, // 10 seconds

    /**
     * Start monitoring ML signals.
     * Called once on page load.
     */
    async init() {
        console.log('🤖 ML Signals module initialized');
        this.startUpdating();
    },

    /**
     * Start periodic ML signal updates.
     */
    startUpdating() {
        if (this.updateInterval) return;

        this.updateInterval = setInterval(() => {
            this.updateSignal();
        }, this.updateFrequency);

        // Also do one immediate update
        this.updateSignal();
    },

    /**
     * Stop periodic updates.
     */
    stopUpdating() {
        if (this.updateInterval) {
            clearInterval(this.updateInterval);
            this.updateInterval = null;
        }
    },

    /**
     * Fetch and display latest ML signal (async, non-blocking).
     */
    updateSignal() {
        if (!this.enabled || !window.eel) return;

        // Fire async request in background
        try {
            eel.get_ml_signal()();

            // Poll for cached result (non-blocking)
            setTimeout(() => {
                eel.get_last_ml_signal()(signal => {
                    if (signal) {
                        this.onSignalReceived(signal);
                    }
                });
            }, 50);  // Small delay to let backend finish
        } catch (e) {
            if (e !== 'eel') {
                console.warn('⚠️ Failed to request ML signal:', e);
            }
        }
    },

    /**
     * Process ML signal from backend (async result).
     */
    onSignalReceived(signal) {
        if (!signal || typeof signal !== 'object') return;

        // Publish to SignalBus for persistence and display
        const published = SignalBus.publish({
            side: signal.side,
            confidence: signal.confidence,
            reason: signal.reason || `ML (${signal.method})`,
            indicator: 'ML-' + (signal.method || 'ensemble'),
            time: signal.timestamp ? Math.floor(signal.timestamp) : undefined
        });

        if (published) {
            const conf = (published.confidence * 100).toFixed(0);
            console.log(`📊 ML Signal: ${published.side} @ ${conf}%`);

            // Update UI if signals panel is visible
            if (document.getElementById('signalsList')) {
                renderSignalsList();
            }
        }
    },

    /**
     * Train ML model with current chart data (async, non-blocking).
     * Polls for result in background.
     */
    train() {
        if (!window.eel || this.training) return;

        this.training = true;
        const trainBtn = document.getElementById('trainMLBtn');

        // Show loading state
        if (trainBtn) {
            trainBtn.disabled = true;
            trainBtn.textContent = '⏳ Training...';
        }

        console.log('🚀 Async ML training started (non-blocking)');

        // Fire async training
        try {
            eel.train_ml_signals()();

            // Poll for cached result
            this.pollTrainingResult(trainBtn, 0);
        } catch (e) {
            console.error('❌ Failed to start training:', e);
            this.showTrainingNotification('Failed to start training: ' + String(e), 'error');
            this.training = false;
            if (trainBtn) {
                trainBtn.disabled = false;
                trainBtn.textContent = '🤖 Train ML Model';
            }
        }
    },

    /**
     * Poll for training result (up to 35 seconds).
     */
    pollTrainingResult(trainBtn, attempts = 0) {
        const MAX_ATTEMPTS = 700;  // 35 seconds at 50ms interval

        if (attempts >= MAX_ATTEMPTS) {
            console.error('❌ Training timeout after 35 seconds');
            this.showTrainingNotification('Training timeout', 'error');
            this.training = false;
            if (trainBtn) {
                trainBtn.disabled = false;
                trainBtn.textContent = '🤖 Train ML Model';
            }
            return;
        }

        eel.get_ml_training_result()(result => {
            if (result) {
                // Result is ready
                this.training = false;
                if (trainBtn) {
                    trainBtn.disabled = false;
                    trainBtn.textContent = '🤖 Train ML Model';
                }
                this.handleTrainingResult(result);
            } else {
                // Keep polling
                setTimeout(() => {
                    this.pollTrainingResult(trainBtn, attempts + 1);
                }, 50);
            }
        });
    },

    /**
     * Handle training completion.
     */
    handleTrainingResult(result) {
        if (result.error) {
            console.error('❌ Training error:', result.error);
            this.showTrainingNotification('Error: ' + result.error, 'error');
            return;
        }

        console.log('✅ ML training complete:', result);

        const msg = `Model trained: ${result.accuracy}% accuracy on ${result.samples} samples (${result.features} features)`;
        this.showTrainingNotification(msg, 'success');

        // Update UI with metrics if present
        const metricsEl = document.getElementById('mlMetrics');
        if (metricsEl) {
            const importance = result.feature_importance || {};
            const topFeatures = Object.entries(importance)
                .sort((a, b) => b[1] - a[1])
                .slice(0, 3)
                .map(([name, score]) => `${name}: ${(score * 100).toFixed(1)}%`)
                .join(', ');

            metricsEl.innerHTML = `
                <strong>Last Training:</strong><br/>
                Accuracy: ${(result.accuracy * 100).toFixed(1)}%<br/>
                Top Features: ${topFeatures}
            `;
        }

        // Resume signal updates now that model is trained
        this.startUpdating();
    },

    /**
     * Show toast notification for training.
     */
    showTrainingNotification(message, type = 'info') {
        if (typeof toast === 'function') {
            toast(message, type);
        } else {
            console.log(`[${type.toUpperCase()}] ${message}`);
        }
    },

    /**
     * Toggle ML signals on/off.
     */
    toggle() {
        this.enabled = !this.enabled;
        if (this.enabled) {
            this.startUpdating();
            console.log('✅ ML signals enabled');
        } else {
            this.stopUpdating();
            console.log('❌ ML signals disabled');
        }
    }
};

// Auto-init on page load if eel is available
document.addEventListener('DOMContentLoaded', () => {
    if (window.eel) {
        MLSignals.init();
    } else {
        console.warn('⚠️ Eel not available — ML signals disabled');
        MLSignals.enabled = false;
    }
});

// Export for use in other modules
window.MLSignals = MLSignals;

console.log('✅ ml_signals.js v2.0 loaded — Async ML signal integration ready');

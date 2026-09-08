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
     * Fetch and display latest ML signal.
     */
    async updateSignal() {
        if (!this.enabled || !window.eel) return;

        try {
            const signal = await new Promise((resolve, reject) => {
                eel.get_ml_signal()(
                    result => resolve(result),
                    error => reject(error)
                );
            });

            if (!signal) return;

            // Publish to SignalBus for persistence and display
            const published = SignalBus.publish({
                side: signal.side,
                confidence: signal.confidence,
                reason: signal.reason || `ML (${signal.method})`,
                indicator: 'ML-' + (signal.method || 'ensemble'),
                time: signal.timestamp ? Math.floor(signal.timestamp) : undefined
            });

            if (published) {
                console.log(`📊 ML Signal: ${published.side} @ ${(published.confidence * 100).toFixed(0)}%`);

                // Update UI if signals panel is visible
                if (document.getElementById('signalsList')) {
                    renderSignalsList();
                }
            }
        } catch (e) {
            if (e !== 'eel') { // Ignore eel not available
                console.warn('⚠️ ML signal fetch error:', e);
            }
        }
    },

    /**
     * Train ML model with current chart data.
     * Updates UI with training progress.
     */
    async train() {
        if (!window.eel || this.training) return;

        this.training = true;

        try {
            // Show loading state
            const trainBtn = document.getElementById('trainMLBtn');
            if (trainBtn) {
                trainBtn.disabled = true;
                trainBtn.textContent = 'Training...';
            }

            const result = await new Promise((resolve, reject) => {
                eel.train_ml_signals()(
                    result => resolve(result),
                    error => reject(error)
                );
            });

            this.handleTrainingResult(result);
        } catch (e) {
            console.error('❌ ML training error:', e);
            this.showTrainingNotification('Training failed: ' + String(e), 'error');
        } finally {
            this.training = false;
            const trainBtn = document.getElementById('trainMLBtn');
            if (trainBtn) {
                trainBtn.disabled = false;
                trainBtn.textContent = 'Train ML Model';
            }
        }
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

console.log('✅ ml_signals.js v1.0 loaded — ML signal integration ready');

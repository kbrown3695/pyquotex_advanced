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
     * Poll for training result (up to 200 seconds for Phase B gradient boosting).
     */
    pollTrainingResult(trainBtn, attempts = 0) {
        const MAX_ATTEMPTS = 2000;  // 200 seconds at 100ms interval

        if (attempts >= MAX_ATTEMPTS) {
            console.error('❌ Training timeout after 200 seconds');
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
                }, 100);
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

// =============================================================================
// 🔹 Phase B: Multi-Asset Signal Panel
// =============================================================================

let currentSignalPair = "AUD/CAD (OTC)";
let signalPairPollInterval = null;

/**
 * Open the multi-asset signal panel (Phase B).
 */
function openSignalPairs() {
    const panel = document.getElementById('signal-pairs-panel');
    if (panel) {
        panel.style.display = 'block';
        startSignalPairPolling();
    }
}

/**
 * Close the multi-asset signal panel.
 */
function closeSignalPairs() {
    const panel = document.getElementById('signal-pairs-panel');
    if (panel) {
        panel.style.display = 'none';
        stopSignalPairPolling();
    }
}

/**
 * Switch to a different pair in the signal panel.
 */
function switchSignalPair(pair) {
    currentSignalPair = pair;

    // Update active tab
    document.querySelectorAll('.signal-pair-tab').forEach(tab => {
        if (tab.dataset.pair === pair) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });

    // Update display
    updateSignalPairDisplay();
}

/**
 * Update the signal display for the current pair.
 */
function updateSignalPairDisplay() {
    if (!currentSignalPair) return;

    eel.get_signal_for_asset(currentSignalPair, "1m")(signal => {
        const display = document.getElementById('signalPairDisplay');
        if (!display) return;

        console.log(`[updateSignalPairDisplay] Pair: ${currentSignalPair}, Signal:`, signal);

        if (signal) {
            const buyColor = signal.side === 'BUY' ? '#00C510' : '#ff0000';
            const sideClass = signal.side === 'BUY' ? 'signal-pair-buy' : 'signal-pair-sell';

            // Format components
            let componentsHTML = '';
            if (signal.components) {
                componentsHTML = '<div class="signal-pair-components"><strong>Components:</strong><br>';
                for (const [key, value] of Object.entries(signal.components)) {
                    if (typeof value === 'object' && value.p_up !== undefined) {
                        componentsHTML += `${key}: ${(value.p_up * 100).toFixed(0)}% | `;
                    } else if (typeof value === 'number') {
                        componentsHTML += `${key}: ${value.toFixed(4)} | `;
                    }
                }
                componentsHTML += '</div>';
            }

            display.innerHTML = `
                <div style="text-align: center;">
                    <div class="signal-pair-value ${sideClass}">
                        ${signal.side}
                    </div>
                    <div class="signal-pair-confidence">
                        Confidence: ${(signal.confidence * 100).toFixed(1)}%
                    </div>
                    <div class="signal-pair-reason">
                        <strong>Reason:</strong> ${signal.reason}
                    </div>
                    ${componentsHTML}
                </div>
            `;
        } else {
            display.innerHTML = '<div style="text-align: center; color: #999;">Waiting for signal...</div>';
        }
    });
}

/**
 * Start polling for signal updates (every 500ms).
 */
function startSignalPairPolling() {
    if (signalPairPollInterval) return;

    signalPairPollInterval = setInterval(() => {
        updateSignalPairDisplay();
    }, 500);

    // Immediate update
    updateSignalPairDisplay();
}

/**
 * Stop polling for signal updates.
 */
function stopSignalPairPolling() {
    if (signalPairPollInterval) {
        clearInterval(signalPairPollInterval);
        signalPairPollInterval = null;
    }
}

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

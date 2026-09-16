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

        // Restore saved pair preferences from backend first, then localStorage fallback
        if (window.eel) {
            eel.get_signal_pairs()(pairs => {
                if (pairs && Array.isArray(pairs) && pairs.length > 0) {
                    selectedPairs = pairs;
                    console.log(`✅ Loaded ${pairs.length} signal pairs from backend:`, pairs);
                } else {
                    console.warn('⚠️ No pairs from backend, using localStorage or defaults');
                    loadPairPreferences();
                }
                renderPairTabs();
            });
        } else {
            loadPairPreferences();
            renderPairTabs();
        }

        // Start signal generation for all restored pairs
        selectedPairs.forEach(pair => {
            console.log(`🔄 Re-initializing signals for ${pair}...`);
            startSignalsForPair(pair);
        });

        // Load available assets for pair selector (in background)
        if (window.eel) {
            eel.get_available_assets()(assets => {
                if (assets && Array.isArray(assets)) {
                    allAvailableAssets = assets.sort();
                    console.log(`✅ Pre-loaded ${assets.length} available assets`);
                } else {
                    console.warn('⚠️ No assets returned from backend');
                }
            });
        }

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

        // Fire async request for current asset
        const asset = window.AppState?.currentAsset;
        const timeframe = window.AppState?.currentTimeframe || "1m";

        if (asset) {
            try {
                eel.get_signal_for_asset(asset, timeframe)(signal => {
                    if (signal) {
                        this.onSignalReceived(signal);
                    }
                });
            } catch (e) {
                if (e !== 'eel') {
                    console.warn('⚠️ Failed to request ML signal:', e);
                }
            }
        }
    },

    /**
     * Update signal immediately for current asset (called on asset/timeframe change).
     */
    updateSignalForCurrentAsset() {
        if (!this.enabled || !window.eel) return;

        const asset = window.AppState?.currentAsset;
        const timeframe = window.AppState?.currentTimeframe || "1m";

        if (asset) {
            console.log(`🔄 Fetching ML signal for ${asset}/${timeframe}...`);
            eel.get_signal_for_asset(asset, timeframe)(signal => {
                if (signal) {
                    console.log(`📊 Got signal for ${asset}: ${signal.side} @ ${signal.confidence.toFixed(2)}`);
                    this.onSignalReceived(signal);
                } else {
                    console.log(`⏳ No signal available yet for ${asset}/${timeframe}`);
                }
            });
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

let currentSignalPair = null;
let signalPairPollInterval = null;
let selectedPairs = ["AUD/CAD (OTC)", "EUR/USD (OTC)", "USD/PKR (OTC)", "GBP/USD (OTC)"];  // Default pairs
let allAvailableAssets = [];  // Will be loaded from backend
let recentPairs = [];  // Recently used pairs for quick access

/**
 * Open the multi-asset signal panel (Phase B).
 */
function openSignalPairs() {
    console.log("🔓 openSignalPairs() called");
    const panel = document.getElementById('signal-pairs-panel');
    if (panel) {
        // Fetch pairs from backend
        if (window.eel) {
            eel.get_signal_pairs()(pairs => {
                if (pairs && Array.isArray(pairs) && pairs.length > 0) {
                    selectedPairs = pairs;
                    console.log(`✅ Refreshed ${pairs.length} signal pairs from backend`);
                } else {
                    loadPairPreferences();
                }
                renderPairTabs();
            });
        } else {
            loadPairPreferences();
            renderPairTabs();
        }
        panel.style.display = 'block';
        console.log("📊 Panel displayed, starting polling...");
        if (selectedPairs.length > 0 && !currentSignalPair) {
            currentSignalPair = selectedPairs[0];
        }
        startSignalPairPolling();
    } else {
        console.error("❌ signal-pairs-panel element not found");
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
        tab.classList.remove('active');
    });

    const activeTab = document.querySelector(`[data-pair="${pair}"]`);
    if (activeTab) {
        activeTab.classList.add('active');
    }

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
        if (!display) {
            console.error('❌ signalPairDisplay element not found!');
            return;
        }

        console.log(`📊 [${currentSignalPair}] Signal received:`, signal);

        if (signal && signal.side && signal.confidence !== undefined) {
            const sideClass = signal.side === 'BUY' ? 'signal-pair-buy' : 'signal-pair-sell';
            const confidence = typeof signal.confidence === 'number' ? signal.confidence : 0;

            // Format components
            let componentsHTML = '';
            if (signal.components && typeof signal.components === 'object') {
                componentsHTML = '<div class="signal-pair-components"><strong>Components:</strong><br>';
                try {
                    for (const [key, value] of Object.entries(signal.components)) {
                        if (value && typeof value === 'object' && value.p_up !== undefined) {
                            componentsHTML += `${key}: ${(value.p_up * 100).toFixed(0)}% | `;
                        } else if (typeof value === 'number') {
                            componentsHTML += `${key}: ${value.toFixed(4)} | `;
                        }
                    }
                } catch (e) {
                    console.warn('⚠️ Error formatting components:', e);
                }
                componentsHTML += '</div>';
            }

            display.innerHTML = `
                <div style="text-align: center;">
                    <div class="signal-pair-value ${sideClass}">
                        ${signal.side}
                    </div>
                    <div class="signal-pair-confidence">
                        Confidence: ${(confidence * 100).toFixed(1)}%
                    </div>
                    <div class="signal-pair-reason">
                        <strong>Reason:</strong> ${signal.reason || 'ML Ensemble'}
                    </div>
                    ${componentsHTML}
                </div>
            `;
            console.log(`✅ Signal displayed for ${currentSignalPair}`);
        } else {
            console.warn(`⚠️ Invalid signal for ${currentSignalPair}:`, signal);
            display.innerHTML = '<div style="text-align: center; color: #999;">Waiting for signal...</div>';
        }
    });
}

/**
 * Start polling for signal updates (every 500ms).
 */
function startSignalPairPolling() {
    console.log("⏱️ startSignalPairPolling() called");
    if (signalPairPollInterval) {
        console.warn("⚠️ Poll already running, skipping");
        return;
    }

    console.log(`📡 Starting poll every 500ms for pair: ${currentSignalPair}`);
    signalPairPollInterval = setInterval(() => {
        updateSignalPairDisplay();
    }, 500);

    // Immediate update
    console.log("🔄 Immediate signal check...");
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

/**
 * Add a pair to the monitoring list.
 */
function addPairToMonitor(pair) {
    if (!selectedPairs.includes(pair)) {
        selectedPairs.push(pair);
        addToRecentPairs(pair);
        savePairPreferences();
        renderPairTabs();

        console.log(`📡 Adding ${pair} to monitoring (loading candles)...`);
        startSignalsForPair(pair);  // This will load candles in background
    }
}

/**
 * Add pair to recently used list (max 10).
 */
function addToRecentPairs(pair) {
    // Remove if already exists, then add to front
    recentPairs = recentPairs.filter(p => p !== pair);
    recentPairs.unshift(pair);

    // Keep only last 10
    if (recentPairs.length > 10) {
        recentPairs = recentPairs.slice(0, 10);
    }

    localStorage.setItem('recentSignalPairs', JSON.stringify(recentPairs));
}

/**
 * Load recent pairs from localStorage.
 */
function loadRecentPairs() {
    try {
        const saved = localStorage.getItem('recentSignalPairs');
        if (saved) {
            recentPairs = JSON.parse(saved);
        }
    } catch (e) {
        console.warn('⚠️ Failed to load recent pairs:', e);
    }
}

/**
 * Remove a pair from the monitoring list.
 */
function removePairFromMonitor(pair) {
    selectedPairs = selectedPairs.filter(p => p !== pair);
    savePairPreferences();
    stopSignalsForPair(pair);

    // Switch to first pair if current was removed
    if (currentSignalPair === pair) {
        currentSignalPair = selectedPairs[0] || null;
    }

    renderPairTabs();
    updateSignalPairDisplay();
    console.log(`❌ Removed ${pair} from monitoring`);
}

/**
 * Start signal generation for a pair.
 */
function startSignalsForPair(pair) {
    eel.start_signals_for_asset(pair, "1m")(result => {
        console.log(`✅ Started signals for ${pair}:`, result);
    });
}

/**
 * Stop signal generation for a pair.
 */
function stopSignalsForPair(pair) {
    eel.stop_signals_for_asset(pair, "1m")(result => {
        console.log(`⏹️ Stopped signals for ${pair}:`, result);
    });
}

/**
 * Save pair preferences to localStorage.
 */
function savePairPreferences() {
    localStorage.setItem('selectedSignalPairs', JSON.stringify(selectedPairs));
}

/**
 * Load pair preferences from localStorage.
 */
function loadPairPreferences() {
    try {
        const saved = localStorage.getItem('selectedSignalPairs');
        if (saved) {
            selectedPairs = JSON.parse(saved);
            console.log('📋 Loaded saved pairs:', selectedPairs);
        }
    } catch (e) {
        console.warn('⚠️ Failed to load preferences:', e);
    }
}

/**
 * Render pair tabs dynamically.
 */
function renderPairTabs() {
    const container = document.getElementById('signalPairTabs');
    if (!container) return;

    container.innerHTML = '';

    selectedPairs.forEach((pair, index) => {
        const tab = document.createElement('button');
        tab.className = `signal-pair-tab ${index === 0 ? 'active' : ''}`;
        tab.dataset.pair = pair;

        // Extract pair name
        const pairName = pair.replace(' (OTC)', '');

        tab.innerHTML = `
            <span onclick="switchSignalPair('${pair}')">${pairName}</span>
            <span class="pair-tab-remove" onclick="removePairFromMonitor('${pair}')" title="Remove">✕</span>
        `;

        tab.onclick = (e) => {
            if (!e.target.classList.contains('pair-tab-remove')) {
                switchSignalPair(pair);
            }
        };

        container.appendChild(tab);
    });

    // Set first pair as current
    if (selectedPairs.length > 0 && !currentSignalPair) {
        currentSignalPair = selectedPairs[0];
    }
}

/**
 * Open pair selector modal.
 */
function openPairSelector() {
    const modal = document.getElementById('pairSelectorModal');
    if (!modal) return;

    loadRecentPairs();  // Load recently used pairs

    // Load assets if not already loaded
    if (allAvailableAssets.length === 0) {
        console.log("📡 Loading available assets...");
        eel.get_available_assets()(assets => {
            if (assets && Array.isArray(assets)) {
                allAvailableAssets = assets.sort();
                console.log(`✅ Loaded ${assets.length} available assets`);
                renderPairSelectorContent();
            } else {
                console.error("❌ Failed to load assets:", assets);
            }
        });
    } else {
        renderPairSelectorContent();
    }

    modal.style.display = 'block';

    // Add search functionality
    const searchInput = document.getElementById('pairSearch');
    if (searchInput) {
        searchInput.value = '';  // Clear search
        searchInput.oninput = () => renderPairSelectorContent(searchInput.value);
        searchInput.focus();  // Focus on search input
    }
}

/**
 * Close pair selector modal.
 */
function closePairSelector() {
    const modal = document.getElementById('pairSelectorModal');
    if (modal) modal.style.display = 'none';
}

/**
 * Render available pairs in selector.
 */
function renderPairSelectorContent(filter = '') {
    const content = document.getElementById('pairSelectorContent');
    if (!content) return;

    if (allAvailableAssets.length === 0) {
        content.innerHTML = '<div style="padding: 20px; text-align: center; color: #999;">📡 Loading assets...</div>';
        return;
    }

    let html = '';

    // Show recent pairs first (if no filter)
    if (!filter && recentPairs.length > 0) {
        html += '<div style="padding: 8px 12px; font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px;">⏱️ Recent</div>';
        html += recentPairs.map(pair => `
            <div class="pair-selector-item ${selectedPairs.includes(pair) ? 'selected' : ''}"
                 onclick="togglePairSelection('${pair}')">
                ${pair}
            </div>
        `).join('');
        html += '<div style="height: 1px; background: rgba(59, 130, 246, 0.2); margin: 8px 0;"></div>';
    }

    // Show all assets (filtered if search)
    const filteredAssets = allAvailableAssets.filter(asset =>
        asset.toLowerCase().includes(filter.toLowerCase())
    );

    if (filteredAssets.length === 0) {
        if (!html) {
            content.innerHTML = '<div style="padding: 20px; text-align: center; color: #999;">No pairs found</div>';
        } else {
            content.innerHTML = html;
        }
        return;
    }

    html += filteredAssets.map(asset => `
        <div class="pair-selector-item ${selectedPairs.includes(asset) ? 'selected' : ''}"
             onclick="togglePairSelection('${asset}')">
            ${asset}
        </div>
    `).join('');

    content.innerHTML = html;
}

/**
 * Toggle pair selection in modal.
 */
function togglePairSelection(pair) {
    if (selectedPairs.includes(pair)) {
        removePairFromMonitor(pair);
    } else {
        addPairToMonitor(pair);
    }
    renderPairSelectorContent(document.getElementById('pairSearch')?.value || '');
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

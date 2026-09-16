/**
 * 📡 signals.js — v1.0 (Signal Bus + Log Panel)
 * =============================================================================
 * Structured signal layer for indicator scripts, modeled on the signal
 * architecture of a larger trading system:
 *   indicator script → emitSignal({side, confidence, reason})
 *                    → SignalBus.publish() (validate → dedup → persist)
 *                    → subscribers + signal log panel
 *
 * Signals are DATA, not pixels: a signal entry is
 *   { side, confidence, reason, time, indicator, asset, timeframe }
 * and survives indicator stop/restart and app reloads (localStorage).
 *
 * Dependencies: datafeed.js (AppState — runtime only, optional-guarded),
 *               editor.js (closeModal, toast — runtime only, optional-guarded).
 */

// =============================================================================
// ⚙️ CONFIGURATION
// =============================================================================
const SIGNALS_CONFIG = {
    STORAGE_KEY: 'qx_signals_v1',
    MAX_SIGNALS: 200,          // Ring buffer cap (oldest dropped)
    VALID_SIDES: ['BUY', 'SELL']
};

// =============================================================================
// 💾 STORAGE (own key — safeSaveStorage/safeLoadStorage are hardwired to the
// editor's 'qx_data_v1' key and would corrupt editor files if reused here)
// =============================================================================
function _saveSignalsStorage(data) {
    try {
        localStorage.setItem(SIGNALS_CONFIG.STORAGE_KEY, JSON.stringify(data));
        return true;
    } catch (e) {
        console.warn('⚠️ Signal history save failed:', e);
        return false;
    }
}

function _loadSignalsStorage() {
    try {
        const raw = localStorage.getItem(SIGNALS_CONFIG.STORAGE_KEY);
        return raw ? JSON.parse(raw) : null;
    } catch (e) {
        console.warn('⚠️ Signal history load failed:', e);
        return null;
    }
}

// =============================================================================
// 🚌 SIGNAL BUS
// =============================================================================
const SignalBus = {
    _signals: [],
    _subscribers: [],
    _seenKeys: new Set(),
    _unread: 0,

    /** Load persisted signal history on startup. */
    init() {
        const data = _loadSignalsStorage();
        if (Array.isArray(data?.signals)) {
            this._signals = data.signals.slice(-SIGNALS_CONFIG.MAX_SIGNALS);
            this._signals.forEach(s => this._seenKeys.add(this._key(s)));
        }
    },

    _persist() {
        _saveSignalsStorage({ signals: this._signals });
    },

    /** Dedup key: one signal per indicator per side per candle time. */
    _key(sig) {
        return `${sig.indicator}|${sig.side}|${sig.time}`;
    },

    /**
     * Validate + record a signal. Returns the stored signal, or null when
     * rejected (invalid side) or deduplicated.
     */
    publish(raw) {
        if (!raw || typeof raw !== 'object') return null;

        const side = String(raw.side || '').toUpperCase();
        if (!SIGNALS_CONFIG.VALID_SIDES.includes(side)) {
            console.warn(`⚠️ emitSignal rejected: side must be BUY or SELL (got "${raw.side}")`);
            return null;
        }

        const candles = window.AppState?.currentCandles || [];
        const lastCandle = candles[candles.length - 1];

        const sig = {
            side,
            confidence: Math.min(1, Math.max(0, Number(raw.confidence) || 0.5)),
            reason: String(raw.reason || ''),
            time: Number(raw.time) || (lastCandle ? lastCandle.time : Math.floor(Date.now() / 1000)),
            indicator: String(raw.indicator || 'Unknown'),
            asset: String(raw.asset || window.AppState?.currentAsset || ''),
            timeframe: String(raw.timeframe || window.AppState?.currentTimeframe || '')
        };

        const key = this._key(sig);
        if (this._seenKeys.has(key)) return null; // already recorded this candle

        this._seenKeys.add(key);
        this._signals.push(sig);
        if (this._signals.length > SIGNALS_CONFIG.MAX_SIGNALS) {
            const dropped = this._signals.shift();
            this._seenKeys.delete(this._key(dropped));
        }
        this._persist();

        this._unread++;
        this._updateBadge();
        this._notify(sig);
        return sig;
    },

    _notify(sig) {
        this._subscribers.forEach(fn => {
            try { fn(sig); } catch (e) { console.warn('⚠️ Signal subscriber error:', e); }
        });
    },

    /** Register a listener for new signals. Returns an unsubscribe function. */
    subscribe(fn) {
        if (typeof fn !== 'function') return () => {};
        this._subscribers.push(fn);
        return () => {
            this._subscribers = this._subscribers.filter(f => f !== fn);
        };
    },

    getSignals() {
        return [...this._signals];
    },

    clear() {
        this._signals = [];
        this._seenKeys.clear();
        this._unread = 0;
        this._persist();
        this._updateBadge();
        renderSignalsList();
    },

    markRead() {
        this._unread = 0;
        this._updateBadge();
    },

    _updateBadge() {
        const badge = document.getElementById('signalsBadge');
        if (!badge) return;
        if (this._unread > 0) {
            badge.textContent = this._unread > 99 ? '99+' : String(this._unread);
            badge.style.display = 'flex';
        } else {
            badge.style.display = 'none';
        }
    }
};

// =============================================================================
// 📋 SIGNAL LOG PANEL
// =============================================================================
function _formatSignalTime(unixSec) {
    try {
        return new Date(unixSec * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (e) {
        return String(unixSec);
    }
}

function renderSignalsList() {
    const list = document.getElementById('signalsList');
    if (!list) return;

    const signals = SignalBus.getSignals().slice().reverse(); // newest first
    const fragment = document.createDocumentFragment();

    if (!signals.length) {
        const empty = document.createElement('div');
        empty.className = 'sig-empty';
        empty.textContent = 'No signals yet — call this.emitSignal({side:\'BUY\', confidence:0.8, reason:\'...\'}) inside your indicator\'s update().';
        fragment.appendChild(empty);
    }

    signals.forEach(sig => {
        const row = document.createElement('div');
        row.className = 'sig-row';

        const time = document.createElement('span');
        time.className = 'sig-time';
        time.textContent = _formatSignalTime(sig.time);

        const meta = document.createElement('span');
        meta.className = 'sig-meta';
        meta.textContent = `${sig.asset || '—'} · ${sig.timeframe || '—'} · ${sig.indicator}`;

        const side = document.createElement('span');
        side.className = `sig-side ${sig.side.toLowerCase()}`;
        side.textContent = sig.side === 'BUY' ? '▲ BUY' : '▼ SELL';

        const conf = document.createElement('span');
        conf.className = 'sig-conf';
        const confBar = document.createElement('span');
        confBar.className = 'sig-conf-bar';
        confBar.style.width = Math.round(sig.confidence * 100) + '%';
        confBar.style.background = sig.confidence >= 0.6 ? '#00C510' : '#d4af37';
        const confText = document.createElement('span');
        confText.textContent = Math.round(sig.confidence * 100) + '%';
        conf.append(confBar, confText);

        const reason = document.createElement('span');
        reason.className = 'sig-reason';
        reason.textContent = sig.reason || '—';
        reason.title = sig.reason || '';

        row.append(time, meta, side, conf, reason);
        fragment.appendChild(row);
    });

    list.innerHTML = '';
    list.appendChild(fragment);
}

function openSignalsModal() {
    SignalBus.markRead();
    renderSignalsList();
    const modal = document.getElementById('signalsModal');
    if (modal) modal.style.display = 'flex';
}

function clearSignals() {
    SignalBus.clear();
}

function signalsCSV() {
    const signals = SignalBus.getSignals();
    if (!signals.length) {
        if (typeof toast === 'function') toast('No signals to export', 'error');
        return;
    }
    const header = 'Time,Asset,Timeframe,Indicator,Side,Confidence,Reason';
    const rows = signals.map(s =>
        [s.time, s.asset, s.timeframe, s.indicator, s.side, s.confidence, '"' + String(s.reason).replace(/"/g, '""') + '"'].join(',')
    );
    const csv = [header].concat(rows).join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'signals_' + (window.AppState?.currentAsset || 'chart').replace(/[^a-z0-9]/gi, '_') + '.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    if (typeof toast === 'function') toast('Signals CSV exported', 'success');
}

// =============================================================================
// 📊 CHART MARKER DISPLAY (Signal Visualization)
// =============================================================================

const SignalMarkers = {
    _markers: new Map(),  // Track markers by signal key

    /**
     * Display a signal as a marker on the chart.
     * Adds a visual marker at the signal's time with BUY (↑) or SELL (↓).
     */
    displaySignalOnChart(signal) {
        if (!signal || !window.CM || !window.candleSeries) return;

        try {
            const marker = {
                time: signal.time,
                position: signal.side === 'BUY' ? 'belowBar' : 'aboveBar',
                color: signal.side === 'BUY' ? '#00C510' : '#ff0000',
                shape: signal.side === 'BUY' ? 'arrowUp' : 'arrowDown',
                text: signal.side === 'BUY' ? '↑' : '↓',
                title: `${signal.side} (${signal.indicator})\nConfidence: ${(signal.confidence * 100).toFixed(0)}%\n${signal.reason}`
            };

            // Add marker via chart manager if available
            if (window.CM && typeof window.CM.addMarker === 'function') {
                const markerId = window.CM.addMarker(marker);

                // Track marker for cleanup
                const signalKey = `${signal.indicator}|${signal.side}|${signal.time}`;
                this._markers.set(signalKey, markerId);

                console.log(`✅ Signal marker displayed: ${signal.side} @ ${signal.confidence.toFixed(2)}`);
            }
        } catch (e) {
            console.warn('⚠️ Failed to display signal marker:', e);
        }
    },

    /**
     * Clear all signal markers from the chart.
     */
    clearAllMarkers() {
        try {
            this._markers.forEach((markerId, key) => {
                if (window.CM && typeof window.CM.removeMarker === 'function') {
                    window.CM.removeMarker(markerId);
                }
            });
            this._markers.clear();
            console.log('🧹 All signal markers cleared');
        } catch (e) {
            console.warn('⚠️ Failed to clear signal markers:', e);
        }
    },

    /**
     * Redraw all signal markers when timeframe/asset changes.
     */
    redrawSignalsForCurrentChart() {
        const asset = window.AppState?.currentAsset;
        const timeframe = window.AppState?.currentTimeframe;

        if (!asset || !timeframe) return;

        // Get all signals for current asset
        const allSignals = SignalBus.getSignals();
        const relevantSignals = allSignals.filter(s =>
            s.asset === asset && s.timeframe === timeframe
        );

        // Clear old markers
        this.clearAllMarkers();

        // Redraw markers for current view
        relevantSignals.forEach(signal => {
            this.displaySignalOnChart(signal);
        });

        console.log(`🔄 Redrawn ${relevantSignals.length} signals for ${asset}/${timeframe}`);
    }
};

/**
 * Subscribe to signal bus to automatically display signals on chart.
 * This is called during initialization to keep markers in sync.
 */
function initSignalChartDisplay() {
    SignalBus.subscribe(signal => {
        // Display new signals on chart
        const asset = window.AppState?.currentAsset;
        const timeframe = window.AppState?.currentTimeframe;

        // Only display if signal matches current view
        if (signal.asset === asset && signal.timeframe === timeframe) {
            SignalMarkers.displaySignalOnChart(signal);
        }
    });

    console.log('✅ Signal chart display initialized');
}

// =============================================================================
// 🌍 GLOBAL EXPORTS & INIT
// =============================================================================
window.SignalBus = SignalBus;
window.SignalMarkers = SignalMarkers;
window.renderSignalsList = renderSignalsList;
window.openSignalsModal = openSignalsModal;
window.clearSignals = clearSignals;
window.signalsCSV = signalsCSV;
window.initSignalChartDisplay = initSignalChartDisplay;

SignalBus.init();
initSignalChartDisplay();

// Toolbar button + modal wiring (guarded — this file may load before the DOM
// finishes, and modal-close delegation lives in editor.js's initEditor).
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('signalsBtn');
    if (btn) btn.addEventListener('click', openSignalsModal);

    const modal = document.getElementById('signalsModal');
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target.classList.contains('modal-overlay')) closeModal('signalsModal');
        });
    }
    SignalBus._updateBadge();
});

console.log('✅ signals.js v1.0 loaded — Signal bus + log panel ready');

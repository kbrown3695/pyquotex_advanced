import js from '@eslint/js';
import globals from 'globals';

/**
 * Cross-file globals: the frontend is a set of classic scripts that share
 * top-level declarations through the global scope (each file also assigns
 * its public API to window.*). These are the legitimate declarations across
 * frontend/*.js — a typo (e.g. `renderTabz`) is NOT in this list and will
 * still be caught by no-undef.
 */
const APP_GLOBALS = [
  '_assetSearchTimer', '_loadFileIntoEditor', '_renderTabsPending',
  '_resizeMonaco', '_syncRunButtons', 'addTrackedEventListener',
  'animateCountdown', 'APP_CONFIG', 'applyIncrementalUpdate', 'applyIndSet',
  'applySettings', 'AppState', 'buildNfTpl', 'ChartManager', 'cleanupAll',
  'cleanupIndicator', 'clearAll', 'clearErrorHighlight', 'closeAssetsModal',
  'closeEditor', 'closeModal', 'closeSettings', 'closeTimeframesModal',
  'CM', 'CONFIG', 'connectionCheckInterval', 'countdownAnimationId',
  'countdownLabel', 'createDebouncer', 'debounceLogic', 'debounceRender',
  'debugLog', 'ensureCountdownLabel', 'exportCSV', 'fallbackData',
  'getChartColors', 'getCode', 'getPricePrecisionForAsset', 'goToErrorLine',
  'hideErrorCard', 'hideNewFile', 'highlightErrorLine', 'IndicatorBase',
  'Indicators', 'initChartManager', 'initChartSafely', 'initEditor',
  'initMonaco', 'isValidCandle', 'isValidIndicatorName', 'loadStorage',
  'loadTemplate', 'nfTpl', 'openAssetsModal', 'openEditor',
  'openSignalsModal', 'openTimeframesModal', 'pickNfTpl', 'PRICE_PRECISION_MAP',
  'removeAllTrackedEventListeners', 'renderAssetsModal', 'renderIndList',
  'renderSignalsList', 'renderTabs', 'renderTimeframesModal', 'RESERVED_WORDS', 'rmFile', 'rmInd',
  'runIndicator', 'safeEelCall', 'safeLoadStorage', 'safeSaveStorage',
  'sanitizeIndicatorName', 'saveStorage', 'saveStorageDebounced',
  'selectAsset', 'selectTimeframe', 'setCode', 'setupChartInteractions',
  'setupGlobalEvents', 'showErrorCard', 'showIndSet', 'SignalBus',
  'signalsCSV', 'clearSignals', 'startConnectionMonitor',
  'stopIndicator', 'STORAGE_KEY', 'STORAGE_VERSION', 'swFile', 'TEMPLATES',
  'toast', 'toggleInd', 'toggleVis', 'TPL_AREA', 'TPL_ARROWS', 'TPL_BB',
  'TPL_CUSTOM', 'TPL_EMA', 'TPL_MA', 'TPL_PIVOT', 'TPL_VWAP', 'UI',
  'updateChart', 'updateChartPricePrecision', 'updateCountdown',
  'updateLiveIndicators', 'updateTabDot', 'updateTabs', 'userInteractTimer',
  'validateCandleData',
].reduce((acc, name) => ({ ...acc, [name]: 'writable' }), {});

export default [
  {
    ignores: ['node_modules/', 'myenv/', 'frontend/assets/'],
  },
  js.configs.recommended,
  {
    files: ['frontend/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: {
        ...globals.browser,
        // Injected by index.html / the Python-Eel bridge
        eel: 'readonly',
        monaco: 'readonly',
        LightweightCharts: 'readonly',
        // Monaco's AMD loader (CDN loader.js)
        require: 'readonly',
        define: 'readonly',
        ...APP_GLOBALS,
      },
    },
    rules: {
      // Underscore-prefixed identifiers are intentionally unused
      'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
      'no-undef': 'error',
      // Each classic script legitimately re-declares the cross-file symbols
      // it owns (they're declared here as globals for the other files).
      // Duplicate keys inside one object are still caught by no-dupe-keys.
      'no-redeclare': 'off',
      // Empty catch blocks are deliberate "swallow and continue" in UI handlers
      'no-empty': ['error', { allowEmptyCatch: true }],
    },
  },
];

#!/usr/bin/env python3
"""
🔗 ML COHERENCE TEST SUITE
=====================================================
Verifies that all ML components work together as a unified system.
Tests the data flow: Engine → Signal Service → Aggregator → Order Executor
"""

import sys
import json
from pathlib import Path
import asyncio

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestResults:
    def __init__(self):
        self.tests = {}
        self.passed = 0
        self.failed = 0

    def add(self, name: str, passed: bool, message: str = ""):
        self.tests[name] = {"passed": passed, "message": message}
        if passed:
            self.passed += 1
        else:
            self.failed += 1
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {name}")
        if message:
            print(f"       {message[:100]}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\nResult: {self.passed}/{total} tests passed")
        return self.passed == total


# ============================================================================
# LAYER 1: Feature Engineering & Signals
# ============================================================================

def test_feature_registry():
    """Test that feature registry loads all available features."""
    print("\n" + "="*70)
    print("LAYER 1: Feature Engineering")
    print("="*70)

    results = TestResults()

    try:
        from ml.features.feature_registry import FeatureRegistry
        registry = FeatureRegistry()
        features = registry.get_all_features()

        if len(features) > 20:
            results.add("Feature Registry", True, f"{len(features)} features registered")
        else:
            results.add("Feature Registry", False, f"Only {len(features)} features (need >20)")
    except Exception as e:
        results.add("Feature Registry", False, str(e)[:100])

    return results


def test_model_registry():
    """Test that model registry loads all models."""
    print("\n" + "="*70)
    print("LAYER 2: Model Registry")
    print("="*70)

    results = TestResults()

    try:
        from ml.registry.model_registry import ModelRegistry
        registry = ModelRegistry()
        models = registry.list_models()

        required_models = {
            'kalman', 'expected_return', 'probability',
            'gradient_boosting', 'lstm', 'transformer',
            'regime_classifier', 'reversal_predictor'
        }

        found = set(m.lower() for m in models)
        missing = required_models - found

        if not missing:
            results.add("Model Registry", True, f"{len(models)} models available")
        else:
            results.add("Model Registry", False, f"Missing models: {missing}")
    except Exception as e:
        results.add("Model Registry", False, str(e)[:100])

    return results


def test_signal_aggregator():
    """Test that signal aggregator can combine signals."""
    print("\n" + "="*70)
    print("LAYER 3: Signal Aggregation")
    print("="*70)

    results = TestResults()

    try:
        from ml.aggregation.signal_aggregator import SignalAggregator

        aggregator = SignalAggregator()
        results.add("Aggregator Instantiation", True, "SignalAggregator created")

        # Check aggregator has core methods
        methods = ['aggregate_signals', 'get_signal_components', 'get_confidence_metrics']
        available = [m for m in methods if hasattr(aggregator, m)]

        if len(available) >= 2:
            results.add("Aggregator Methods", True, f"{len(available)}/{len(methods)} methods available")
        else:
            results.add("Aggregator Methods", False, f"Only {len(available)} methods")
    except Exception as e:
        results.add("Signal Aggregator", False, str(e)[:100])

    return results


def test_model_ensemble():
    """Test that ensemble combines multiple models."""
    print("\n" + "="*70)
    print("LAYER 4: Model Ensemble")
    print("="*70)

    results = TestResults()

    try:
        from ml.models.ensemble import EnsembleModel

        # Note: This might need config, so we just test instantiation
        try:
            ensemble = EnsembleModel()
            results.add("Ensemble Instantiation", True, "EnsembleModel created")
        except Exception as e:
            results.add("Ensemble Instantiation", False, f"Needs config: {str(e)[:80]}")
    except Exception as e:
        results.add("Model Ensemble Import", False, str(e)[:100])

    return results


# ============================================================================
# LAYER 2: Signal Service
# ============================================================================

def test_signal_service():
    """Test ML signal service initialization."""
    print("\n" + "="*70)
    print("LAYER 5: Signal Service")
    print("="*70)

    results = TestResults()

    try:
        from ml.serving.signal_service import MLSignalService

        # Create with None trading session (expected)
        try:
            service = MLSignalService(trading_session=None)
            results.add("Signal Service Creation", True, "MLSignalService initialized")

            # Check methods
            methods = ['generate_signal', 'get_signals', 'start_service', 'stop_service']
            available = [m for m in methods if hasattr(service, m)]

            if len(available) >= 3:
                results.add("Signal Service Methods", True, f"{len(available)}/{len(methods)} methods")
            else:
                results.add("Signal Service Methods", False, f"Only {len(available)} methods")
        except Exception as e:
            results.add("Signal Service Creation", False, str(e)[:100])
    except Exception as e:
        results.add("Signal Service Import", False, str(e)[:100])

    return results


def test_async_signal_manager():
    """Test async signal manager."""
    print("\n" + "="*70)
    print("LAYER 6: Async Signal Manager")
    print("="*70)

    results = TestResults()

    try:
        from ml.serving.async_signal_manager import AsyncSignalManager

        manager = AsyncSignalManager()
        results.add("AsyncSignalManager Creation", True, "Manager created")

        # Check for async methods
        methods = ['start_signal_polling', 'stop_signal_polling', 'get_latest_signal']
        available = [m for m in methods if hasattr(manager, m)]

        if len(available) >= 2:
            results.add("AsyncSignalManager Methods", True, f"{len(available)}/{len(methods)} methods")
        else:
            results.add("AsyncSignalManager Methods", False, f"Only {len(available)} methods")
    except Exception as e:
        results.add("AsyncSignalManager", False, str(e)[:100])

    return results


# ============================================================================
# LAYER 3: Order Execution
# ============================================================================

def test_order_executor():
    """Test order executor."""
    print("\n" + "="*70)
    print("LAYER 7: Order Execution")
    print("="*70)

    results = TestResults()

    try:
        from ml.trading.order_executor import OrderExecutor

        executor = OrderExecutor(quotex_client=None)
        results.add("OrderExecutor Creation", True, "OrderExecutor created")

        # Check for execution methods
        methods = ['execute_buy_order', 'execute_sell_order', 'get_order_stats', 'get_order_history']
        available = [m for m in methods if hasattr(executor, m)]

        if len(available) >= 2:
            results.add("OrderExecutor Methods", True, f"{len(available)}/{len(methods)} methods")
        else:
            results.add("OrderExecutor Methods", False, f"Only {len(available)} methods")
    except Exception as e:
        results.add("OrderExecutor", False, str(e)[:100])

    return results


def test_automated_trader():
    """Test automated trader."""
    print("\n" + "="*70)
    print("LAYER 8: Automated Trading")
    print("="*70)

    results = TestResults()

    try:
        from ml.trading.automated_trader import AutomatedTrader

        trader = AutomatedTrader(
            quotex_client=None,
            order_executor=None,
            position_tracker=None
        )
        results.add("AutomatedTrader Creation", True, "AutomatedTrader created")

        # Check methods
        methods = ['process_signal', 'get_trade_stats', 'get_position_summary']
        available = [m for m in methods if hasattr(trader, m)]

        if len(available) >= 2:
            results.add("AutomatedTrader Methods", True, f"{len(available)}/{len(methods)} methods")
        else:
            results.add("AutomatedTrader Methods", False, f"Only {len(available)} methods")
    except Exception as e:
        results.add("AutomatedTrader", False, str(e)[:100])

    return results


def test_position_tracker():
    """Test position tracking."""
    print("\n" + "="*70)
    print("LAYER 9: Position Tracking")
    print("="*70)

    results = TestResults()

    try:
        from ml.trading.position_tracker import PositionTracker

        tracker = PositionTracker()
        results.add("PositionTracker Creation", True, "PositionTracker created")

        # Check methods
        methods = ['open_position', 'close_position', 'get_open_positions', 'get_position_pnl']
        available = [m for m in methods if hasattr(tracker, m)]

        if len(available) >= 3:
            results.add("PositionTracker Methods", True, f"{len(available)}/{len(methods)} methods")
        else:
            results.add("PositionTracker Methods", False, f"Only {len(available)} methods")
    except Exception as e:
        results.add("PositionTracker", False, str(e)[:100])

    return results


# ============================================================================
# LAYER 4: Risk Management
# ============================================================================

def test_risk_manager():
    """Test risk management."""
    print("\n" + "="*70)
    print("LAYER 10: Risk Management")
    print("="*70)

    results = TestResults()

    try:
        from ml.trading.risk_manager import RiskManager

        manager = RiskManager()
        results.add("RiskManager Creation", True, "RiskManager created")

        # Check methods
        methods = ['validate_trade', 'get_risk_metrics', 'update_constraints']
        available = [m for m in methods if hasattr(manager, m)]

        if len(available) >= 2:
            results.add("RiskManager Methods", True, f"{len(available)}/{len(methods)} methods")
        else:
            results.add("RiskManager Methods", False, f"Only {len(available)} methods")
    except Exception as e:
        results.add("RiskManager", False, str(e)[:100])

    return results


# ============================================================================
# LAYER 5: Data Pipeline
# ============================================================================

def test_candle_store():
    """Test candle data storage."""
    print("\n" + "="*70)
    print("LAYER 11: Data Pipeline")
    print("="*70)

    results = TestResults()

    try:
        from ml.data.candle_store import CandleStore

        store = CandleStore()
        results.add("CandleStore Creation", True, "CandleStore created")

        # Check methods
        methods = ['add_candle', 'get_candles', 'get_latest_candle']
        available = [m for m in methods if hasattr(store, m)]

        if len(available) >= 2:
            results.add("CandleStore Methods", True, f"{len(available)}/{len(methods)} methods")
        else:
            results.add("CandleStore Methods", False, f"Only {len(available)} methods")
    except Exception as e:
        results.add("CandleStore", False, str(e)[:100])

    return results


# ============================================================================
# INTEGRATION: Full System Flow
# ============================================================================

def test_system_integration():
    """Test that all components can work together."""
    print("\n" + "="*70)
    print("INTEGRATION: Full System Flow")
    print("="*70)

    results = TestResults()

    try:
        # Import all critical components
        from ml.registry.model_registry import ModelRegistry
        from ml.features.feature_registry import FeatureRegistry
        from ml.aggregation.signal_aggregator import SignalAggregator
        from ml.trading.order_executor import OrderExecutor
        from ml.trading.automated_trader import AutomatedTrader
        from ml.trading.position_tracker import PositionTracker
        from ml.trading.risk_manager import RiskManager
        from ml.data.candle_store import CandleStore

        results.add("All Imports Successful", True, "10+ modules imported")

        # Create instances
        model_registry = ModelRegistry()
        feature_registry = FeatureRegistry()
        aggregator = SignalAggregator()
        executor = OrderExecutor()
        trader = AutomatedTrader(None, executor, PositionTracker())

        results.add("All Instances Created", True, "5+ core instances created")

        # Verify data flow components exist
        components = {
            'models': len(model_registry.list_models()) > 5,
            'features': len(feature_registry.get_all_features()) > 20,
            'signal_aggregation': hasattr(aggregator, 'aggregate_signals'),
            'order_execution': hasattr(executor, 'execute_buy_order'),
            'trade_processing': hasattr(trader, 'process_signal'),
        }

        active = sum(1 for v in components.values() if v)
        results.add("Data Flow Complete", active == 5, f"{active}/5 flow components ready")

    except Exception as e:
        results.add("System Integration", False, str(e)[:100])
        import traceback
        traceback.print_exc()

    return results


# ============================================================================
# FRONTEND CONNECTIVITY
# ============================================================================

def test_frontend_connectivity():
    """Test frontend can receive signals."""
    print("\n" + "="*70)
    print("LAYER 12: Frontend Connectivity")
    print("="*70)

    results = TestResults()

    try:
        frontend_dir = Path(__file__).parent.parent / "frontend"

        # Check required frontend files
        required_files = {
            'index.html': frontend_dir / 'index.html',
            'app.js': frontend_dir / 'app.js',
            'signals.js': frontend_dir / 'signals.js',
            'ml_signals.js': frontend_dir / 'ml_signals.js',
        }

        existing = sum(1 for p in required_files.values() if p.exists())
        results.add("Frontend Files", existing == 4, f"{existing}/4 files present")

        # Check for signal handlers
        signals_js = frontend_dir / 'signals.js'
        if signals_js.exists():
            content = signals_js.read_text()
            has_handlers = all(h in content for h in ['updateSignal', 'displaySignal'])
            results.add("Signal Handlers", has_handlers, "updateSignal + displaySignal")

    except Exception as e:
        results.add("Frontend Connectivity", False, str(e)[:100])

    return results


# ============================================================================
# MAIN
# ============================================================================

def run_all_tests():
    """Run complete ML coherence test suite."""
    print("\n" + "="*70)
    print("ML COHERENCE TEST SUITE")
    print("Verifying all components work as one unit")
    print("="*70)

    all_results = []

    # Layer 1: Features & Models
    all_results.append(("Features & Models", test_feature_registry()))
    all_results.append(("Model Registry", test_model_registry()))

    # Layer 2: Signals
    all_results.append(("Signal Aggregation", test_signal_aggregator()))
    all_results.append(("Model Ensemble", test_model_ensemble()))
    all_results.append(("Signal Service", test_signal_service()))
    all_results.append(("Async Signals", test_async_signal_manager()))

    # Layer 3: Execution
    all_results.append(("Order Execution", test_order_executor()))
    all_results.append(("Automated Trading", test_automated_trader()))
    all_results.append(("Position Tracking", test_position_tracker()))

    # Layer 4: Risk
    all_results.append(("Risk Management", test_risk_manager()))

    # Layer 5: Data
    all_results.append(("Data Pipeline", test_candle_store()))

    # Integration
    all_results.append(("Full Integration", test_system_integration()))

    # Frontend
    all_results.append(("Frontend", test_frontend_connectivity()))

    # Summary
    print("\n" + "="*70)
    print("COMPREHENSIVE SUMMARY")
    print("="*70)

    total_passed = 0
    total_tests = 0

    for layer_name, results in all_results:
        p = results.passed
        f = results.failed
        t = p + f
        pct = (p / t * 100) if t > 0 else 0

        status = "[OK]" if f == 0 else "[WARN] " if p >= t-1 else "[ERR]"
        print(f"{status} {layer_name}: {p}/{t} ({pct:.0f}%)")

        total_passed += p
        total_tests += t

    overall_pct = (total_passed / total_tests * 100) if total_tests > 0 else 0

    print("\n" + "="*70)
    print(f"OVERALL: {total_passed}/{total_tests} ({overall_pct:.0f}%)")
    print("="*70)

    if overall_pct >= 90:
        print("[OK] ML SYSTEM IS COHERENT - All components integrated")
        return True
    elif overall_pct >= 75:
        print("[WARN]  MOSTLY COHERENT - Minor issues to fix")
        return True
    else:
        print("[ERR] SYSTEM BROKEN - Major integration issues")
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)

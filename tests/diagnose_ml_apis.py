#!/usr/bin/env python3
"""
API DISCOVERY - Find actual methods in ML components
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def inspect_module(module_name: str, class_name: str):
    """Inspect a class and show available methods."""
    print(f"\n{'='*70}")
    print(f"{module_name}::{class_name}")
    print('='*70)

    try:
        # Import the module
        parts = module_name.rsplit('.', 1)
        if len(parts) == 2:
            module_path, module_file = parts
            exec(f"from {module_path} import {module_file}")
            module = eval(module_file)
        else:
            exec(f"import {module_name}")
            module = eval(module_name)

        # Get the class
        cls = getattr(module, class_name, None)
        if not cls:
            print(f"[ERR] Class {class_name} not found in {module_name}")
            return

        print(f"[OK] Class found: {cls}")
        print(f"\nPublic methods and attributes:")

        members = [m for m in dir(cls) if not m.startswith('_')]
        for member in sorted(members)[:20]:  # First 20
            obj = getattr(cls, member, None)
            if callable(obj):
                print(f"  - {member}() [method]")
            else:
                print(f"  - {member} [property]")

        if len(members) > 20:
            print(f"  ... and {len(members)-20} more")

        # Try to instantiate
        print(f"\nTrying to instantiate...")
        try:
            instance = cls()
            print(f"[OK] {class_name}() works")

            # Show instance methods
            instance_methods = [m for m in dir(instance) if not m.startswith('_') and callable(getattr(instance, m))]
            print(f"\nInstance methods ({len(instance_methods)}):")
            for method in sorted(instance_methods)[:10]:
                print(f"  - {method}()")
            if len(instance_methods) > 10:
                print(f"  ... and {len(instance_methods)-10} more")
        except Exception as e:
            print(f"[WARN] Cannot instantiate: {str(e)[:100]}")

    except Exception as e:
        print(f"[ERR] {str(e)[:200]}")
        import traceback
        traceback.print_exc()


print("INSPECTING ML COMPONENT APIS")
print("="*70)

# Feature Registry
print("\n### FEATURE REGISTRY ###")
try:
    from ml.features.feature_registry import FEATURE_REGISTRY, FeatureRegistry
    print(f"[OK] FEATURE_REGISTRY has {len(FEATURE_REGISTRY)} features")
    for i, f in enumerate(list(FEATURE_REGISTRY)[:5]):
        print(f"  - {f.name}")
    print(f"  ... and {len(FEATURE_REGISTRY)-5} more")
except Exception as e:
    print(f"[ERR] {e}")

# Model Registry
print("\n### MODEL REGISTRY ###")
try:
    from ml.registry.model_registry import ModelRegistry
    mr = ModelRegistry()
    print(f"[OK] ModelRegistry created")
    print(f"    Base dir: {mr.base_dir}")
    print(f"    Available model classes: {len(mr._model_class_map)}")

    # Check available methods
    methods = [m for m in dir(mr) if not m.startswith('_')]
    print(f"    Methods: {', '.join(methods[:5])}")
except Exception as e:
    print(f"[ERR] {e}")

# Signal Aggregation
print("\n### SIGNAL AGGREGATION ###")
try:
    from ml.aggregation.signal_aggregator import signal_aggregator
    print(f"[OK] signal_aggregator imported")
    print(f"    Type: {type(signal_aggregator)}")
except Exception as e:
    print(f"[ERR] SignalAggregator: {e}")

try:
    from ml.aggregation.regime_ensemble_voter import RegimeEnsembleVoter
    print(f"[OK] RegimeEnsembleVoter available")
except Exception as e:
    print(f"[WARN] RegimeEnsembleVoter: {e}")

try:
    from ml.aggregation.multi_timeframe_aggregator import MultiTimeframeAggregator
    print(f"[OK] MultiTimeframeAggregator available")
except Exception as e:
    print(f"[WARN] MultiTimeframeAggregator: {e}")

# ML Signal Service
print("\n### ML SIGNAL SERVICE ###")
try:
    from ml.serving.signal_service import MLSignalService
    service = MLSignalService(trading_session=None)
    print(f"[OK] MLSignalService created")
    methods = [m for m in dir(service) if not m.startswith('_')]
    print(f"    Methods: {', '.join(methods[:8])}")
except Exception as e:
    print(f"[ERR] {e}")

# Async Signal Manager
print("\n### ASYNC SIGNAL MANAGER ###")
try:
    from ml.serving.async_signal_manager import AsyncSignalManager
    print(f"[OK] AsyncSignalManager imported")
    # Check __init__ signature
    import inspect
    sig = inspect.signature(AsyncSignalManager.__init__)
    print(f"    __init__ params: {list(sig.parameters.keys())}")
except Exception as e:
    print(f"[ERR] {e}")

# Automated Trader
print("\n### AUTOMATED TRADER ###")
try:
    from ml.trading.automated_trader import AutomatedTrader
    import inspect
    sig = inspect.signature(AutomatedTrader.__init__)
    print(f"[OK] AutomatedTrader.__init__ params: {list(sig.parameters.keys())}")
except Exception as e:
    print(f"[ERR] {e}")

# Order Executor
print("\n### ORDER EXECUTOR ###")
try:
    from ml.trading.order_executor import OrderExecutor
    import inspect
    sig = inspect.signature(OrderExecutor.__init__)
    print(f"[OK] OrderExecutor.__init__ params: {list(sig.parameters.keys())}")
except Exception as e:
    print(f"[ERR] {e}")

# Risk Manager
print("\n### RISK MANAGER ###")
try:
    from ml.trading.risk_manager import RiskManager
    print(f"[OK] RiskManager imported")
except Exception as e:
    print(f"[WARN] RiskManager not found: {e}")
    # Try to find what's in trading directory
    from pathlib import Path
    trading_dir = Path(__file__).parent.parent / "ml" / "trading"
    print(f"    Available in trading/: {[f.stem for f in trading_dir.glob('*.py') if not f.stem.startswith('_')]}")

print("\n" + "="*70)
print("DIAGNOSIS COMPLETE")

"""Test if models can be loaded"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from ml.registry.model_registry import ModelRegistry

print("Testing model loading...")
print("="*70)

registry = ModelRegistry()

# Check if models exist
models_to_check = [
    ("AUD/CAD (OTC)", "1m", "ensemble"),
    ("AUD/CAD (OTC)", "1m", "kalman"),
    ("AUD/CAD (OTC)", "1m", "expected_return"),
]

for asset, tf, model_key in models_to_check:
    print(f"\nLoading: {asset} {tf} {model_key}")
    try:
        model = registry.get_active_model(asset, tf, model_key=model_key)
        if model:
            print(f"  ✓ Model loaded: {type(model).__name__}")
        else:
            print(f"  ✗ Model is None")
    except Exception as e:
        print(f"  ✗ Error: {str(e)[:100]}")


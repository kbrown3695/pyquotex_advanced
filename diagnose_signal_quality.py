"""Check why signals have low confidence"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from ml.serving.signal_service import MLSignalService
from ml.data.candle_store import CandleStore

print("="*70)
print("SIGNAL QUALITY DIAGNOSIS")
print("="*70)

# Create some dummy candles to test signal generation
candles = [
    {
        'time': 1000 * i,
        'open': 1.0 + (i * 0.001),
        'high': 1.01 + (i * 0.001),
        'low': 0.99 + (i * 0.001),
        'close': 1.005 + (i * 0.001)
    }
    for i in range(100)
]

service = MLSignalService()

try:
    signal = service.generate_signal('TEST/USD', '1m', candles)
    print(f"\nSignal Result:")
    print(f"  Side: {signal.side}")
    print(f"  Confidence: {signal.confidence:.2%}")
    print(f"  Reason: {signal.reason}")
    print(f"  Method: {signal.method}")
    
    if hasattr(signal, 'components') and signal.components:
        print(f"\nComponents:")
        for key, val in list(signal.components.items())[:10]:
            print(f"  {key}: {val}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*70)
print("RECOMMENDATIONS:")
print("="*70)
print("1. If confidence is 0%, models haven't trained yet - wait for auto-training")
print("2. If confidence is 10-40%, lower minConfidence in trading_config.json")
print("3. If models aren't training, check:")
print("   - Need 100+ candles per asset")
print("   - Check model_registry.list_models() output")
print("   - Check for training errors in logs")

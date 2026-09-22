#!/usr/bin/env python3
"""Quick test of Phase D RLAgent implementation."""

import sys
import numpy as np

print("Testing Phase D (RLAgent) Implementation")
print("=" * 60)

# Test 1: Import PyTorch
try:
    import torch
    print(f"✅ PyTorch imported successfully (v{torch.__version__})")
except ImportError as e:
    print(f"❌ PyTorch import failed: {e}")
    sys.exit(1)

# Test 2: Import RLAgent
try:
    from ml.models.rl_agent import RLAgent
    print("✅ RLAgent imported successfully")
except ImportError as e:
    print(f"❌ RLAgent import failed: {e}")
    sys.exit(1)

# Test 3: Create RLAgent instance
try:
    agent = RLAgent(input_dim=13, hidden_dim=64)
    print("✅ RLAgent instance created successfully")
except Exception as e:
    print(f"❌ RLAgent initialization failed: {e}")
    sys.exit(1)

# Test 4: Generate dummy training data and train
try:
    X_train = np.random.randn(100, 13).astype(np.float32)
    y_train = np.random.randint(0, 2, 100)

    print("⏳ Training RLAgent on dummy data...")
    agent.train(X_train, y_train)
    print("✅ RLAgent training completed successfully")
except Exception as e:
    print(f"❌ RLAgent training failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Make predictions
try:
    X_test = np.random.randn(10, 13).astype(np.float32)

    predictions = agent.predict(X_test)
    print(f"✅ Predictions shape: {predictions.shape}")

    proba = agent.predict_proba(X_test)
    print(f"✅ Probability predictions shape: {proba.shape}")
    print(f"   Sample probabilities: {proba[-1]}")
except Exception as e:
    print(f"❌ Prediction failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Get metadata and feature importances
try:
    metadata = agent.get_metadata()
    print(f"✅ Metadata: {metadata['model_type']}, {metadata['algorithm']}")

    importances = agent.get_feature_importances()
    print(f"✅ Feature importances shape: {importances.shape}")
except Exception as e:
    print(f"❌ Metadata/importances failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Test save/load
try:
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = os.path.join(tmpdir, "rl_agent_test.pkl")
        agent.save(model_path)
        print(f"✅ Model saved to {model_path}")

        agent_loaded = RLAgent.load(model_path)
        print("✅ Model loaded successfully")

        proba_loaded = agent_loaded.predict_proba(X_test)
        print(f"✅ Loaded model predictions shape: {proba_loaded.shape}")
except Exception as e:
    print(f"❌ Save/load failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ All Phase D tests passed!")
print("\nPhase D is ready to integrate into the signal service.")
print("Next: Run engine.py and click 'Train ML Model' button.")

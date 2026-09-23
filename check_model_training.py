"""Check which models are being trained"""
import re

# Read signal_service.py
with open('ml/serving/signal_service.py') as f:
    content = f.read()

# Extract all models_trained.append calls
trained = re.findall(r'models_trained\.append\("(.+?)"\)', content)

# Remove duplicates and sort
trained_unique = sorted(set(trained))

print("MODELS BEING TRAINED IN MLSignalService.train_all()")
print("="*60)
for i, model in enumerate(trained_unique, 1):
    print(f"{i:2d}. {model}")

print(f"\nTotal: {len(trained_unique)} unique model types")

# Now check registry
print("\n" + "="*60)
print("MODEL CLASSES IN ModelRegistry")
print("="*60)

with open('ml/registry/model_registry.py') as f:
    for line in f:
        if '": ' in line and 'Model' in line:
            # Extract class name
            match = re.search(r'"([^"]+)":\s*(\w+)', line)
            if match:
                print(f"  {match.group(1):35s} → {match.group(2)}")


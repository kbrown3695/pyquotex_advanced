#!/usr/bin/env python3
"""
Test script to verify engine startup and logging.
Helps diagnose silent exit issues.
"""

import subprocess
import sys
import time
from pathlib import Path

def run_engine_with_timeout(timeout_seconds=30):
    """Run engine.py and capture output."""
    print("=" * 80)
    print("🚀 Starting engine.py with logging...")
    print("=" * 80)

    try:
        proc = subprocess.Popen(
            [sys.executable, "engine.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )

        start_time = time.time()
        lines_received = 0

        # Stream output in real-time
        while True:
            line = proc.stdout.readline()
            if not line:
                break

            print(line.rstrip())
            lines_received += 1

            # Timeout check
            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                print(f"\n⏱️  Timeout after {timeout_seconds}s ({lines_received} lines received)")
                proc.terminate()
                break

        # Check exit code
        returncode = proc.wait(timeout=5)
        if returncode is None:
            proc.kill()
            returncode = proc.wait()

        print("=" * 80)
        print(f"Process exited with code: {returncode}")
        print(f"Total lines received: {lines_received}")
        print("=" * 80)

        return returncode, lines_received

    except Exception as e:
        print(f"❌ Error running engine: {e}")
        return -1, 0

if __name__ == "__main__":
    returncode, lines = run_engine_with_timeout(timeout_seconds=30)

    if returncode == 0:
        print("✅ Engine exited normally")
    elif returncode is None or returncode == -1:
        print("⚠️  Engine was terminated or timed out")
    else:
        print(f"❌ Engine exited with error code: {returncode}")

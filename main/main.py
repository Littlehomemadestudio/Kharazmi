"""
Kharazmi launcher.

Run with:
    python main.py

Or, for the module entry point:
    python -m kharazmi
"""
import sys
import os

# Ensure the parent directory is on the path so `kharazmi` imports resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kharazmi.app import main


if __name__ == "__main__":
    sys.exit(main())

# راه‌انداز RASK — نقطه ورود اصلی
import sys
import os

# Ensure the parent directory is on the path so imports resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kharazmi.app import main


if __name__ == "__main__":
    sys.exit(main())

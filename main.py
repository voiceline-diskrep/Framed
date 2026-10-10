"""Root runner for Loupe Photo Inspection & Culling Workstation."""

import sys
import os

# Add directory to pythonpath
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loupe.app import main

if __name__ == "__main__":
    sys.exit(main())

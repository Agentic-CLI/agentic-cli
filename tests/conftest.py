"""Test bootstrap: put the package under ``src/`` on ``sys.path`` so tests can
``from agentic import ...`` without installing the project."""
import os
import sys

_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

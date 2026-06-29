"""Pytest config — ensure the backend root is importable (services, config, ...)."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

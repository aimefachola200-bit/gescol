# -*- coding: utf-8 -*-
"""Point d'entrée pour un hébergeur Python (PythonAnywhere, etc.)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app as application  # noqa: E402,F401

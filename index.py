import sys
import os

# Make project root importable (VerdictAI modules live in root, not in api/)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import app

import sys
import os

# Make project root importable (VerdictAI modules live in root, not in api/)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from mangum import Mangum
from main import app

# Vercel invokes this handler for every request
handler = Mangum(app, lifespan="off")

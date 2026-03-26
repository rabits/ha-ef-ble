import sys
from pathlib import Path

# add this package directory to resolve absolute proto imports at runtime
sys.path.insert(0, str(Path(__file__).parent))

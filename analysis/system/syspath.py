"""Put the system modules and the vendored code on sys.path (the job runs `python -I`, which adds no script dir).

Order matters: the vendored volmap folder first, so `import core` / `import models` resolve to the byte-identical
copies in analysis/system/vendor/volmap (see vendor/SHA256SUMS).
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (HERE, HERE / "vendor", HERE / "vendor" / "volmap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

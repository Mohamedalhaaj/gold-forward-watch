"""sys.path for lab v2 (SYSTEM_V2_PREREG.md §2.5). FROZEN (lab v2).

The job runs `python -I`, which adds no script directory. Lab v2 imports:
- its own modules from analysis/system/lab_v2 (every name starts with v2_, so none shadows a v1 module);
- the vendored hunt harness and the four seed files by file path (vendor/hunt), never through sys.path;
- these FROZEN v1 modules, read-only: bi5 (the decoder), bars and forecasts (model clock helpers and the NYSE
  holidays), lab.eproc (e-process, promotion, demotion and retirement checks), lab.registry (first_day, states,
  titles, the event log) and lab.execution (the per-day minute arrays), with the vendored volmap core and models they
  import. Their sha256 values are pinned in analysis/system/lab_v2/FROZEN_V2.sha256 as well as in v1's FROZEN.sha256.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
ROOT = HERE.parents[2]
VENDOR = HERE / "vendor"
for _p in (SYSTEM, SYSTEM / "vendor", SYSTEM / "vendor" / "volmap", HERE):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

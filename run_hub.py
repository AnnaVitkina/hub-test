"""Colab / local entrypoint for the RMT Pipeline Hub.

Colab cell example:

    !git clone https://github.com/<you>/rmt-pipeline-hub.git
    import os
    os.chdir('/content/rmt-pipeline-hub')
    !git pull
    from google.colab import drive
    drive.mount('/content/drive')
    !pip install -q -r requirements.txt
    exec(open('/content/rmt-pipeline-hub/run_hub.py').read())
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Support Colab-style: exec(open(...).read()) where __file__ is missing.
if "__file__" in globals():
    _HUB_ROOT = Path(__file__).resolve().parent
else:
    _colab = Path("/content/rmt-pipeline-hub")
    _HUB_ROOT = _colab if _colab.exists() else Path.cwd()

if str(_HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(_HUB_ROOT))

os.chdir(_HUB_ROOT)

from hub.app import launch  # noqa: E402

if __name__ == "__main__" or "__file__" not in globals():
    # share=False → local / Colab proxy URL only (no public Gradio link).
    launch(share=False, server_port=7860)

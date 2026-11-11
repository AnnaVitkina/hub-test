"""Colab / local entrypoint for the RMT Pipeline Hub.

Colab cell:

    !git clone https://github.com/AnnaVitkina/hub-test.git
    import os
    os.chdir('/content/hub-test')
    !git pull
    from google.colab import drive
    drive.mount('/content/drive')
    !pip install -q -r requirements.txt
    exec(open('/content/hub-test/run_hub.py').read())
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _resolve_hub_root() -> Path:
    if "__file__" in globals():
        return Path(__file__).resolve().parent

    # exec(open(...).read()) in Colab: prefer known clone folders, else cwd.
    for candidate in (
        Path.cwd(),
        Path("/content/hub-test"),
        Path("/content/rmt-pipeline-hub"),
    ):
        if (candidate / "hub" / "app.py").exists() and (candidate / "registry.yaml").exists():
            return candidate.resolve()
    return Path.cwd().resolve()


_HUB_ROOT = _resolve_hub_root()
if str(_HUB_ROOT) not in sys.path:
    sys.path.insert(0, str(_HUB_ROOT))
os.chdir(_HUB_ROOT)

print(f"Hub root: {_HUB_ROOT}")

try:
    import gradio  # noqa: F401
    import yaml  # noqa: F401
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. In Colab run:\n"
        "  !pip install -q -r requirements.txt\n"
        f"Then re-run this cell. Original error: {exc}"
    ) from exc

from hub.app import launch  # noqa: E402

if __name__ == "__main__" or "__file__" not in globals():
    # share=False → local / Colab proxy URL only (no public Gradio link).
    launch(share=False, server_port=7860)

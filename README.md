# RMT Pipeline Hub

One Colab Gradio hub that runs existing shipper/flow pipeline repos **without changing them**.
https://colab.research.google.com/drive/1wuNKyDuuiRBtf_UoLuxxGUWOgLjzvuzd#scrollTo=WfEzh9kVkkj7

## What it does

1. You open one Colab cell that clones this hub and mounts Drive.
2. Gradio starts with `share=False` and prints a localhost / Colab proxy link.
3. You pick **Shipper** → **Flow** → **Start**.
4. The hub clones/pulls the matching GitHub repo and runs its entry script.
5. Pipeline `input()` questions appear in the hub UI; you answer there.
6. When finished, result file path(s) are shown.

## Colab cell

```python
!git clone https://github.com/AnnaVitkina/hub-test.git
import os
os.chdir('/content/hub-test')
!git pull
from google.colab import drive
drive.mount('/content/drive')
!pip install -q -r requirements.txt
exec(open('/content/hub-test/run_hub.py').read())
```

`pip install` is required. The cell should stay running and print a local / Colab proxy URL — that is the hub UI.

## Registered pipelines

| Shipper | Flow | Repo | Entry |
|---------|------|------|-------|
| Siemens | Sea | [AnnaVitkina/Siemens-Sea](https://github.com/AnnaVitkina/Siemens-Sea) | `run_pipeline.py` |
| Aptiv | Air | [AnnaVitkina/Aptiv-Air](https://github.com/AnnaVitkina/Aptiv-Air) | `xlsx_to_df.py` |

Add more rows in [`registry.yaml`](registry.yaml). Pipeline GitHub repos are not modified by this hub.

## Local smoke test

```bash
pip install -r requirements.txt
python run_hub.py
```

Repos clone under `./_pipeline_repos/` when `/content` is not present (local Windows/macOS). Drive paths inside the pipelines still expect Colab Shared Drive mounts.

## Notes

- Hub shipper/flow selects the **repository**. Questions inside that pipeline (e.g. Siemens Divisions vs Healthineers, FCL vs LCL) are still asked via the hub question box.
- Mount Google Drive before Start; pipelines write to their configured Shared Drive `input` / `processing` / `output` folders.

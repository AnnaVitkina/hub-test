"""Load shipper/flow → repo mapping from registry.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HUB_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY_PATH = HUB_ROOT / "registry.yaml"


@dataclass(frozen=True)
class FlowConfig:
    shipper: str
    flow: str
    repo_url: str
    clone_dir: str
    entry_script: str


def _load_raw(path: Path | None = None) -> dict[str, Any]:
    registry_path = path or DEFAULT_REGISTRY_PATH
    with registry_path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict) or "shippers" not in data:
        raise ValueError(f"Invalid registry at {registry_path}: missing 'shippers'")
    return data


def list_shippers(path: Path | None = None) -> list[str]:
    data = _load_raw(path)
    return sorted(data["shippers"].keys())


def list_flows(shipper: str, path: Path | None = None) -> list[str]:
    data = _load_raw(path)
    shippers = data["shippers"]
    if shipper not in shippers:
        raise KeyError(f"Unknown shipper: {shipper}")
    return sorted(shippers[shipper].get("flows", {}).keys())


def get_flow_config(shipper: str, flow: str, path: Path | None = None) -> FlowConfig:
    data = _load_raw(path)
    shippers = data["shippers"]
    if shipper not in shippers:
        raise KeyError(f"Unknown shipper: {shipper}")
    flows = shippers[shipper].get("flows", {})
    if flow not in flows:
        raise KeyError(f"Unknown flow '{flow}' for shipper '{shipper}'")
    entry = flows[flow]
    return FlowConfig(
        shipper=shipper,
        flow=flow,
        repo_url=str(entry["repo_url"]),
        clone_dir=str(entry["clone_dir"]),
        entry_script=str(entry["entry_script"]),
    )

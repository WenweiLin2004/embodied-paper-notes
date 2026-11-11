"""Conservative, editable taxonomy; rule matches are suggestions, not facts."""
from __future__ import annotations

from pathlib import Path
import re
from typing import Any

import yaml

DEFAULT_TAGS = {
    "task/manipulation", "task/navigation", "task/locomotion",
    "task/mobile_manipulation", "task/whole_body", "task/planning", "task/perception",
    "method/vla", "method/imitation_learning", "method/reinforcement_learning",
    "method/diffusion_policy", "method/world_model", "method/foundation_model",
    "method/classical_control", "body/single_arm", "body/dual_arm", "body/humanoid",
    "body/quadruped", "body/mobile_robot", "body/hand", "role/dataset", "role/benchmark",
    "role/model", "role/system", "role/survey", "evaluation/simulation", "evaluation/real_world",
}

RULES = {
    "task/manipulation": r"\bmanipulation\b|机器人操作",
    "task/navigation": r"\bnavigation\b|导航",
    "task/locomotion": r"\blocomotion\b|步态",
    "task/mobile_manipulation": r"\bmobile manipulation\b|移动操作",
    "task/whole_body": r"\bwhole[- ]body\b|全身控制",
    "method/vla": r"\bvision[- ]language[- ]action\b|\bvla\b",
    "method/imitation_learning": r"\bimitation learning\b|\bbehavior(?:al)? cloning\b|模仿学习",
    "method/reinforcement_learning": r"\breinforcement learning\b|强化学习",
    "method/diffusion_policy": r"\bdiffusion polic(?:y|ies)\b|扩散策略",
    "method/world_model": r"\bworld models?\b|世界模型",
    "method/foundation_model": r"\bfoundation models?\b|基础模型",
    "body/dual_arm": r"\b(?:dual[- ]arm|bimanual)\b|双臂",
    "body/humanoid": r"\bhumanoid\b|人形机器人",
    "body/quadruped": r"\bquadruped\b|四足",
    "body/hand": r"\bdexterous hands?\b|灵巧手",
    "role/dataset": r"\bdataset\b|数据集",
    "role/benchmark": r"\bbenchmark\b|评测基准",
    "role/survey": r"\bsurvey\b|综述",
}


def as_dict(value: Any) -> dict:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    raise TypeError("Expected a model or dictionary")


def load_taxonomy(root: Path | str | None = None) -> set[str]:
    path = Path(root) / "config" / "taxonomy.yaml" if root is not None else None
    if path is not None and path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        tags = data.get("tags")
        if not isinstance(tags, (list, dict)) or not tags:
            raise ValueError("config/taxonomy.yaml must define non-empty tags")
        if any(not isinstance(tag, str) or not re.fullmatch(r"[a-z][a-z0-9_-]*/[a-z][a-z0-9_-]*", tag) for tag in tags):
            raise ValueError("Taxonomy tags must use namespace/value")
        return set(tags)
    return DEFAULT_TAGS.copy()


def classify(paper: Any, root: Path | str | None = None) -> list[str]:
    """Return conservative title/abstract matches; skip uncertain evaluation claims."""
    data = as_dict(paper)
    haystack = str(data.get("title") or "") + "\n" + str(data.get("abstract") or "")
    allowed = load_taxonomy(root)
    return sorted(tag for tag, pattern in RULES.items() if tag in allowed and re.search(pattern, haystack, re.I))


def validate_tags(tags: Any, allowed: set[str]) -> list[str]:
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError("tags must be a list of taxonomy strings")
    unknown = set(tags) - allowed
    if unknown:
        raise ValueError("Unknown taxonomy tags: " + ", ".join(sorted(unknown)))
    return sorted(set(tags))

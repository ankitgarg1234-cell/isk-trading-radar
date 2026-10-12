"""Read-only verification of the exact pinned research artifacts."""
import hashlib
import json
from pathlib import Path
from .common import ControlError, digest

PINNED_COMMIT = "d59b93d3d9a87d582045b4ae71ff9a6f696a48be"
PINNED_BRANCH = "research/gem-2025-2026-validation-2026-10-11"
ARTIFACT_HASHES = {
    "research_5x/gem_2025_2026_validation/strategy_frozen_spec.md": "528f35a2ef4ae4feb36edb24a03f8bb7cc524c7a7cb8c7d88a7e57be188dc3a3",
    "research_5x/gem_2025_2026_validation/frozen_config.json": "72483dae54bbdf6ffaaf4d353feda5036a20339cdfae7a0fbda9a668862826dc",
    "research_5x/code/run_research.py": "a46271c5436a9fdec93af55705623a270c2888b0124814cf90af873d54ecf7b5",
    "research_5x/code/continuation_engine.py": "bb4d9845bbc58493f8f83f7e57c171e874e0d20cbc048cf6fbb42cb6f3f686d1",
    "scripts/wf3_offline_valuein.py": "521d6327ba932bde5e548b1b44cc2469afbb69c31e0428f13e2260678468b6d8",
}
RULES_HASH = digest({"commit": PINNED_COMMIT, "artifacts": ARTIFACT_HASHES})


def verify_frozen_artifacts(repository_root):
    """Hash bytes only: never import or execute the research/live engines."""
    root = Path(repository_root)
    for relative, expected in ARTIFACT_HASHES.items():
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise ControlError("Missing or symlinked frozen artifact: " + relative)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ControlError("Frozen artifact drift: " + relative)
    config = json.loads((root / "research_5x/gem_2025_2026_validation/frozen_config.json").read_text())
    if config["configuration"] != {"name": "growth_margin5", "n": 5,
                                   "score": "r63", "filter": "growth_margin"}:
        raise ControlError("Wrong GEM variant")
    return {"commit": PINNED_COMMIT, "rules_hash": RULES_HASH,
            "artifact_hashes": dict(ARTIFACT_HASHES)}

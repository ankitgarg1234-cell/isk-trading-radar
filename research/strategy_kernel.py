"""Load only audited pure trial functions; never import trial/app/db or poll."""
from __future__ import annotations

import ast
import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path

from dual_momentum.rules import wilder_atr_series

REPO = Path(__file__).resolve().parents[1]
FUNCTIONS = {"_next_weekday", "_atr", "_momentum", "_sector_and_cap",
             "_positions_value", "_calculate_targets", "_ranking_audit",
             "_estimate_fee", "_execute_pending", "_stop_check", "_daily_risk_check", "_stage", "_stage_decision"}
CONSTANTS = {"CAPITAL", "TRADING_COST_BPS", "SECTOR_CAP", "STOP_MULT", "WEIGHTS", "ETFS"}
MANIFEST = Path(__file__).with_name("strategy_kernel_manifest.json")


def source_manifest():
    source = (REPO / "dual_momentum/trial.py").read_text()
    tree = ast.parse(source)
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in FUNCTIONS]
    constants = {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
                 if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                 and n.targets[0].id in CONSTANTS}
    if {n.name for n in nodes} != FUNCTIONS or constants.keys() != CONSTANTS:
        raise ValueError("Authoritative strategy definition incomplete")
    functions = {n.name: hashlib.sha256(ast.get_source_segment(source, n).encode()).hexdigest() for n in nodes}
    return {"authority": "dual_momentum/trial.py", "functions": functions,
            "constants": json.loads(json.dumps(constants)),
            "atr_source_sha256": hashlib.sha256((REPO / "dual_momentum/rules.py").read_bytes()).hexdigest()}, nodes, constants


def load_kernel():
    manifest, nodes, constants = source_manifest()
    if manifest != json.loads(MANIFEST.read_text()):
        raise RuntimeError("Strategy source drift: audit parity before updating the pinned manifest")
    namespace = dict(math=math, date=date, timedelta=timedelta,
                     wilder_atr_series=wilder_atr_series, **constants)
    # The AST contains only whitelisted existing function definitions. No
    # top-level imports, database classes, decorators or live entrypoints run.
    if any(n.decorator_list for n in nodes):
        raise ValueError("Unexpected decorated strategy function")
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(REPO / "dual_momentum/trial.py"), "exec"), namespace)
    return namespace

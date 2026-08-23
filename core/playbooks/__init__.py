"""ORION Playbooks (P3-P4).

Asset-specific operating procedures that assemble the FULL doctrine
stack for one instrument: context -> session map -> liquidity map ->
range 2.6 -> sweeps -> bias score -> trade quality -> doctrine decision.

Playbooks REPORT; they never invent data and never execute.
"""

from core.playbooks.base import assemble_technicals
from core.playbooks.gold import run_gold_playbook
from core.playbooks.xrp import run_xrp_playbook

__all__ = ["assemble_technicals", "run_gold_playbook", "run_xrp_playbook"]

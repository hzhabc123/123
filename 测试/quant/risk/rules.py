# risk/rules.py

from dataclasses import dataclass


@dataclass
class RiskConfig:

    max_position_ratio: float = 0.3

    max_total_position_ratio: float = 0.9
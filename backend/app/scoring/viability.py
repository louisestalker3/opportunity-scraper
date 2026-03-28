import math
from dataclasses import dataclass
from typing import Any


@dataclass
class ViabilityResult:
    viability_score: float          # 0-100 weighted composite

    market_demand_score: float      # 0-100
    complaint_severity_score: float  # 0-100
    competition_density_score: float  # 0-100
    pricing_gap_score: float        # 0-100
    build_complexity_score: float   # 0-100
    differentiation_score: float    # 0-100

    mention_count: int
    complaint_count: int
    alternative_seeking_count: int


# Scoring weights (must sum to 1.0)
WEIGHTS = {
    "market_demand": 0.25,
    "complaint_severity": 0.25,
    "competition_density": 0.20,
    "pricing_gap": 0.10,
    "build_complexity": 0.10,
    "differentiation": 0.10,
}

# Tuning constants
DEMAND_SATURATION = 500    # mention count at which demand score saturates to ~100
COMPETITOR_SATURATION = 10  # num competitors at which competition density score bottoms out


class ViabilityScorer:
    """
    Scores market opportunities for indie developers on a 0-100 Viability Index.

    Inputs:
        mentions        - list of mention dicts (each with signal_type, sentiment, confidence_score)
        competitor_ids  - list of competitor app profile IDs (used for competition density)
        app_cons        - list of con strings from the app profile (used for differentiation)
        pricing_tiers   - list of pricing tier dicts from the app profile

    Scoring dimensions:
        market_demand_score:      volume-based, grows logarithmically with mention count
        complaint_severity_score: ratio of negative signals (complaints + alt-seeking)
        competition_density_score: inverse of competitor count (fewer competitors = better)
        pricing_gap_score:        ratio of pricing objections to total mentions
        build_complexity_score:   estimated from number of distinct feature requests/cons (inverse)
        differentiation_score:    based on uniqueness / breadth of unmet needs (con count)
    """

    def _market_demand_score(self, mention_count: int) -> float:
        """Logarithmic growth curve: 0 mentions → 0, ~500+ mentions → ~100."""
        if mention_count <= 0:
            return 0.0
        score = 100.0 * math.log1p(mention_count) / math.log1p(DEMAND_SATURATION)
        return min(score, 100.0)

    def _complaint_severity_score(
        self, complaint_count: int, alternative_seeking_count: int, mention_count: int
    ) -> float:
        """Higher ratio of complaints/alternative-seeking = higher score (worse status quo)."""
        if mention_count == 0:
            return 0.0
        negative_count = complaint_count + alternative_seeking_count
        ratio = negative_count / mention_count
        # Apply slight amplification — ratios above 0.5 are very strong signals
        score = min(ratio * 150.0, 100.0)
        return round(score, 2)

    def _competition_density_score(self, num_competitors: int) -> float:
        """Fewer competitors = higher score. 0 competitors → 100, 10+ → ~0."""
        if num_competitors <= 0:
            return 95.0  # Blue ocean, but slight uncertainty
        score = 100.0 * math.exp(-num_competitors / (COMPETITOR_SATURATION / 2.5))
        return max(round(score, 2), 0.0)

    def _pricing_gap_score(self, pricing_objection_count: int, mention_count: int) -> float:
        """Ratio of pricing complaints. >20% is a strong gap signal."""
        if mention_count == 0:
            return 0.0
        ratio = pricing_objection_count / mention_count
        score = min(ratio * 300.0, 100.0)  # 33%+ pricing objections → score caps at 100
        return round(score, 2)

    def _build_complexity_score(self, cons: list[str]) -> float:
        """
        Fewer distinct pain points = simpler build = higher score.
        We estimate complexity from the number of 'cons' (each con ~ a missing feature).
        0 cons → 50 (unknown), 1-3 cons → high score (focused), 10+ cons → low score (complex).
        """
        num_cons = len([c for c in cons if c.strip()])
        if num_cons == 0:
            return 50.0
        # Inverse sigmoid-ish: score decreases as cons grow
        score = 100.0 * math.exp(-num_cons / 5.0)
        return max(round(score, 2), 5.0)

    def _differentiation_score(self, cons: list[str], mention_count: int) -> float:
        """
        Higher when there are clear, specific gaps nobody is filling.
        Combines: presence of cons + mention volume signal.
        """
        num_cons = len([c for c in cons if c.strip()])
        if num_cons == 0 or mention_count == 0:
            return 20.0  # No clear differentiation angle identified

        # More specific cons + decent mention volume = clearer differentiation opportunity
        con_score = min(num_cons * 15.0, 75.0)  # caps at 75
        volume_bonus = min(math.log1p(mention_count) * 5.0, 25.0)
        score = con_score + volume_bonus
        return round(min(score, 100.0), 2)

    def score(
        self,
        mentions: list[dict[str, Any]],
        competitor_ids: list[Any],
        app_cons: list[str],
        pricing_tiers: list[dict],
    ) -> ViabilityResult:
        mention_count = len(mentions)
        complaint_count = sum(1 for m in mentions if m.get("signal_type") == "complaint")
        alternative_seeking_count = sum(
            1 for m in mentions if m.get("signal_type") == "alternative_seeking"
        )
        pricing_objection_count = sum(
            1 for m in mentions if m.get("signal_type") == "pricing_objection"
        )
        num_competitors = len(competitor_ids)

        market_demand = self._market_demand_score(mention_count)
        complaint_severity = self._complaint_severity_score(
            complaint_count, alternative_seeking_count, mention_count
        )
        competition_density = self._competition_density_score(num_competitors)
        pricing_gap = self._pricing_gap_score(pricing_objection_count, mention_count)
        build_complexity = self._build_complexity_score(app_cons)
        differentiation = self._differentiation_score(app_cons, mention_count)

        viability = (
            WEIGHTS["market_demand"] * market_demand
            + WEIGHTS["complaint_severity"] * complaint_severity
            + WEIGHTS["competition_density"] * competition_density
            + WEIGHTS["pricing_gap"] * pricing_gap
            + WEIGHTS["build_complexity"] * build_complexity
            + WEIGHTS["differentiation"] * differentiation
        )

        return ViabilityResult(
            viability_score=round(viability, 2),
            market_demand_score=round(market_demand, 2),
            complaint_severity_score=round(complaint_severity, 2),
            competition_density_score=round(competition_density, 2),
            pricing_gap_score=round(pricing_gap, 2),
            build_complexity_score=round(build_complexity, 2),
            differentiation_score=round(differentiation, 2),
            mention_count=mention_count,
            complaint_count=complaint_count,
            alternative_seeking_count=alternative_seeking_count,
        )

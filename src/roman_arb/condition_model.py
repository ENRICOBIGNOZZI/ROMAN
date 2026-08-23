from __future__ import annotations

from dataclasses import dataclass
import re


_NEGATIVE = {
    "damaged": 0.20, "damage": 0.18, "scratched": 0.12, "scratch": 0.10,
    "cracked": 0.22, "crack": 0.20, "broken": 0.30, "repair": 0.12,
    "parts": 0.24, "missing": 0.14, "stain": 0.10, "worn": 0.08,
    "replica": 0.45, "fake": 0.50, "aftermarket": 0.12, "custom": 0.08,
    "unverified": 0.10, "as-is": 0.18, "untested": 0.16, "read description": 0.08,
}
_POSITIVE = {
    "sealed": -0.05, "unopened": -0.05, "new with tags": -0.04,
    "full set": -0.03, "box and papers": -0.03, "authenticated": -0.04,
    "psa 10": -0.03, "bgs 10": -0.03,
}


@dataclass(frozen=True)
class ConditionEstimate:
    risk: float
    haircut: float
    confidence: float
    flags: tuple[str, ...]


class ConditionRiskModel:
    """Very small text/image-risk model for condition and misclassification.

    It does not attempt to understand images itself.  Instead it accepts an
    optional external ``image_defect_score`` in [0,1], so a future vision model
    can plug in without changing the risk logic.  In the absence of vision data,
    title/description keywords and image count remain conservative signals.
    """

    def __init__(self, max_haircut: float = 0.20):
        self.max_haircut = float(max_haircut)

    @staticmethod
    def _text(title: str, description: str) -> str:
        return re.sub(r"\s+", " ", f"{title or ''} {description or ''}".lower()).strip()

    def score(
        self,
        title: str,
        description: str = "",
        image_count: int | None = None,
        image_defect_score: float | None = None,
    ) -> ConditionEstimate:
        text = self._text(title, description)
        raw = 0.12
        flags: list[str] = []
        evidence = 0
        for phrase, delta in _NEGATIVE.items():
            if phrase in text:
                raw += delta; flags.append(phrase); evidence += 1
        for phrase, delta in _POSITIVE.items():
            if phrase in text:
                raw += delta; flags.append(phrase); evidence += 1

        if image_count is not None:
            n = max(int(image_count), 0)
            if n == 0:
                raw += 0.12; flags.append("no_images")
            elif n <= 2:
                raw += 0.05; flags.append("few_images")
            elif n >= 6:
                raw -= 0.02
            evidence += 1

        if image_defect_score is not None:
            d = max(0.0, min(1.0, float(image_defect_score)))
            raw += 0.35 * d
            if d >= 0.5:
                flags.append("image_defect")
            evidence += 2

        risk = max(0.0, min(1.0, raw))
        haircut = min(self.max_haircut, self.max_haircut * risk)
        confidence = max(0.20, min(1.0, 0.25 + 0.12 * evidence))
        return ConditionEstimate(risk=risk, haircut=haircut, confidence=confidence, flags=tuple(flags))

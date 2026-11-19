"""SM-2 spaced repetition (grades 0–5; UI maps: Nochmal=1, Schwer=3, Gut=4, Leicht=5)."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..db import utcnow
from ..models import Flashcard


def review(card: Flashcard, grade: int, now: datetime | None = None) -> Flashcard:
    now = now or utcnow()
    grade = max(0, min(5, grade))
    if grade < 3:
        card.repetitions = 0
        card.interval_days = 1
        card.lapses = (card.lapses or 0) + 1
        card.due = now + timedelta(minutes=10)
    else:
        card.repetitions = (card.repetitions or 0) + 1
        if card.repetitions == 1:
            card.interval_days = 1
        elif card.repetitions == 2:
            card.interval_days = 6
        else:
            card.interval_days = max(1, round(card.interval_days * card.ease))
        card.due = now + timedelta(days=card.interval_days)
    card.ease = max(1.3, card.ease + (0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02)))
    return card

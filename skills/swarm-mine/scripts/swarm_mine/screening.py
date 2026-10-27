"""Optional phrase screening."""

from collections.abc import Sequence

from swarm_mine.models import Unit


def normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def screen(
    units: Sequence[Unit],
    url: str,
    *,
    blocked: tuple[str, ...],
    required: tuple[tuple[str, ...], ...],
) -> str | None:
    """Require all phrase groups on one unit; URL text only counts for blocking."""
    texts = [normalize(unit.text) for unit in units]
    if any(normalize(term) in text for term in blocked for text in [normalize(url), *texts]):
        return "blocked"
    if required and not any(
        all(any(normalize(phrase) in text for phrase in group) for group in required)
        for text in texts
    ):
        return "missing_required_phrase"
    return None

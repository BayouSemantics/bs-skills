"""Shift identities for the agents mining the source registry.

Every lease, source observation, and coverage row is attributed to an ``agent``
string, and the registry has no way to check who is really calling: it compares
the string and nothing else. Two agents answering to the same string therefore
release each other's leases and file into each other's history, silently.

Randomness, not description, is what prevents that. A name an agent picks for
itself — ``agent-1``, its model name, the shared hostname — collides precisely
when the swarm is busiest, so identities are minted here instead.
"""

from __future__ import annotations

import secrets

AGENT_PREFIX = "agent"
AGENT_ENTROPY_BYTES = 8
"""64 bits: collision-free across any realistic swarm, still short enough to retype."""


def mint_agent_identity() -> str:
    """Mint the identity one agent answers to for one mining shift.

    Returns:
        A random identity of the form ``agent-<16 lowercase hex characters>``.
    """
    return f"{AGENT_PREFIX}-{secrets.token_hex(AGENT_ENTROPY_BYTES)}"

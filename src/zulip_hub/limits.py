from __future__ import annotations

import math
from typing import Any


# Bornes appliquées à tout ce qui vient du serveur ou de la configuration.
# Sans elles, une réponse hostile alloue sans limite, puis se retrouve
# persistée dans l’état local et relue telle quelle par l’interface.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_TEXT = 4096
MAX_COLLECTION = 5000
MAX_MESSAGE_LENGTH = 1_000_000
MAX_TIMEOUT_SECONDS = 600
MAX_BACKOFF_SECONDS = 3600


def bounded_text(value: Any, limit: int = MAX_TEXT) -> str:
    """Chaîne issue du serveur, tronquée et jamais None."""
    if value is None:
        return ""
    return str(value)[:limit]


def bounded_list(value: Any, limit: int = MAX_COLLECTION) -> list[Any]:
    """Liste issue du serveur, tronquée ; toute autre forme devient vide."""
    if not isinstance(value, list):
        return []
    return value[:limit]


def clamped_number(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    """Nombre issu du serveur, ramené dans un intervalle fini.

    Les booléens, les chaînes, ``NaN`` et les infinis retombent sur la valeur
    par défaut : une comparaison avec ``NaN`` est toujours fausse, donc un
    simple test de bornes le laisserait passer.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    if not math.isfinite(value):
        return default
    return min(maximum, max(minimum, value))

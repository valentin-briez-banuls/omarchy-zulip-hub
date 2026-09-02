from __future__ import annotations

import json
import math
from typing import Any


# Bornes appliquées à tout ce qui vient du serveur ou de la configuration.
# Sans elles, une réponse hostile alloue sans limite, puis se retrouve
# persistée dans l’état local et relue telle quelle par l’interface.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
MAX_TEXT = 4096
MAX_COLLECTION = 5000

# Une charge peu volumineuse peut être arbitrairement imbriquée : la borne en
# octets ne dit rien de la profondeur, et l’analyseur JSON entre en récursion
# bien avant d’atteindre le mégaoctet.
MAX_DEPTH = 64

# Bornes de l’annuaire : un nom et une adresse n’ont pas besoin de la taille
# d’un texte libre, et leur produit par le nombre d’entrées doit rester très
# en deçà du budget d’émission.
MAX_DIRECTORY = 500
MAX_NAME = 256

# Corps d’un message récupéré à la demande : borné avant d’être remis à
# l’interface, qui l’analyse d’un seul tenant.
MAX_CONTENT = 128 * 1024

# Taille d’une charge sérialisée, écrite dans l’état ou émise vers
# l’interface. Les bornes par champ ne s’additionnent pas toutes seules.
MAX_PAYLOAD_BYTES = 512 * 1024
MAX_MESSAGE_LENGTH = 1_000_000
MAX_TIMEOUT_SECONDS = 600
MAX_BACKOFF_SECONDS = 3600


def encoded_response(payload: dict[str, Any]) -> str:
    """Ligne de réponse remise à l’interface, tenue dans le budget d’émission.

    Les bornes appliquées champ par champ ne garantissent pas la taille de
    l’ensemble : la vérification porte donc sur la charge sérialisée, et une
    réponse trop volumineuse devient une erreur plutôt qu’un flot.
    """
    data = json.dumps(payload, ensure_ascii=False) + "\n"
    if len(data.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        return json.dumps(
            {"ok": False, "error": "Réponse locale trop volumineuse."},
            ensure_ascii=False,
        ) + "\n"
    return data


def exceeds_depth(raw: bytes, limit: int = MAX_DEPTH) -> bool:
    """Profondeur d’imbrication mesurée sur les octets bruts.

    Le parcours est itératif et ignore les crochets contenus dans les chaînes :
    il doit pouvoir juger une charge hostile sans jamais faire ce que
    l’analyseur ferait, c’est-à-dire récurser.
    """
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x5B, 0x7B):
            depth += 1
            if depth > limit:
                return True
        elif byte in (0x5D, 0x7D):
            depth -= 1
    return False


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

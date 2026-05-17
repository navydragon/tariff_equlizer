"""Константы домена сценариев."""

from scenarios.models import ScenarioPriceChangeSetting

PRICE_CHANGE_PARAMETERS: list[tuple[str, str]] = [
    (choice.value, choice.label)
    for choice in ScenarioPriceChangeSetting.Parameter
]

PRICE_CHANGE_MODES: list[tuple[str, str]] = [
    (choice.value, choice.label)
    for choice in ScenarioPriceChangeSetting.Mode
]

PRICE_CHANGE_PARAMETER_KEYS: frozenset[str] = frozenset(
    key for key, _ in PRICE_CHANGE_PARAMETERS
)

PRICE_CHANGE_MODE_KEYS: frozenset[str] = frozenset(
    key for key, _ in PRICE_CHANGE_MODES
)

DEFAULT_PRICE_CHANGE_MODE = ScenarioPriceChangeSetting.Mode.FIXED

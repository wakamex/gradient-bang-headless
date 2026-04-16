from __future__ import annotations


RESOURCE_VERBOSE_NAMES = {
    "quantum_foam": "Quantum Foam",
    "retro_organics": "Retro Organics",
    "neuro_symbolics": "Neuro Symbolics",
}


def build_trade_order_prompt(
    *,
    trade_type: str,
    quantity: int,
    commodity: str,
    price_per_unit: int,
) -> str:
    normalized_trade_type = trade_type.strip().upper()
    if normalized_trade_type not in {"BUY", "SELL"}:
        raise ValueError(f"unsupported trade_type {trade_type!r}")

    commodity_key = commodity.strip().lower()
    commodity_name = RESOURCE_VERBOSE_NAMES.get(commodity_key)
    if commodity_name is None:
        raise ValueError(f"unsupported commodity {commodity!r}")

    if quantity <= 0:
        raise ValueError("quantity must be > 0")
    if price_per_unit < 0:
        raise ValueError("price_per_unit must be >= 0")

    return (
        f"Place a {normalized_trade_type} trade for {quantity} of "
        f"{commodity_name} at {price_per_unit} CR per unit"
    )


def build_ship_purchase_prompt(
    *,
    ship_display_name: str,
    replace_ship_name: str,
    replace_ship_id: str,
) -> str:
    display_name = ship_display_name.strip()
    replace_name = replace_ship_name.strip()
    replace_id = replace_ship_id.strip()
    if not display_name:
        raise ValueError("ship_display_name is required")
    if not replace_name:
        raise ValueError("replace_ship_name is required")
    if not replace_id:
        raise ValueError("replace_ship_id is required")
    return (
        f"I'd like to purchase a {display_name} to replace "
        f"{replace_name} (ship ID: {replace_id})"
    )


def build_corporation_ship_purchase_prompt(*, ship_display_name: str) -> str:
    display_name = ship_display_name.strip()
    if not display_name:
        raise ValueError("ship_display_name is required")
    return f"I'd like to purchase a {display_name} as a new corporation ship"


def build_corporation_ship_task_prompt(
    *,
    ship_name: str,
    task_description: str,
    ship_id: str | None = None,
) -> str:
    normalized_ship_name = ship_name.strip()
    normalized_task_description = task_description.strip()
    if not normalized_ship_name:
        raise ValueError("ship_name is required")
    if not normalized_task_description:
        raise ValueError("task_description is required")

    ship_ref = normalized_ship_name
    if ship_id:
        normalized_ship_id = ship_id.strip()
        if not normalized_ship_id:
            raise ValueError("ship_id must be non-empty when provided")
        ship_ref = f"{ship_ref} [{normalized_ship_id[:6]}]"

    return f"Have my corporation ship {ship_ref} {normalized_task_description}"


def build_collect_unowned_ship_prompt(*, ship_id: str) -> str:
    normalized_ship_id = ship_id.strip()
    if not normalized_ship_id:
        raise ValueError("ship_id is required")
    return f"collect unowned ship id {normalized_ship_id} in sector"

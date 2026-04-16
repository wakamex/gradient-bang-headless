from __future__ import annotations


RESOURCE_VERBOSE_NAMES = {
    "quantum_foam": "Quantum Foam",
    "retro_organics": "Retro Organics",
    "neuro_symbolics": "Neuro Symbolics",
}


def _commodity_verbose_name(commodity: str) -> str:
    commodity_key = commodity.strip().lower()
    commodity_name = RESOURCE_VERBOSE_NAMES.get(commodity_key)
    if commodity_name is None:
        raise ValueError(f"unsupported commodity {commodity!r}")
    return commodity_name


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

    commodity_name = _commodity_verbose_name(commodity)

    if quantity <= 0:
        raise ValueError("quantity must be > 0")
    if price_per_unit < 0:
        raise ValueError("price_per_unit must be >= 0")

    return (
        f"Place a {normalized_trade_type} trade for {quantity} of "
        f"{commodity_name} at {price_per_unit} CR per unit"
    )


def build_move_to_sector_prompt(*, sector_id: int) -> str:
    if sector_id <= 0:
        raise ValueError("sector_id must be > 0")
    return f"Move to sector {sector_id}, then stop."


def build_buy_max_commodity_prompt(*, commodity: str) -> str:
    commodity_name = _commodity_verbose_name(commodity)
    return f"Buy as much {commodity_name} as possible at this port, then stop."


def build_sell_all_commodity_prompt(*, commodity: str) -> str:
    commodity_name = _commodity_verbose_name(commodity)
    return f"Sell all {commodity_name} at this port, then stop."


def build_recharge_warp_prompt(*, units: int | None = None) -> str:
    if units is None:
        return "Recharge my warp power to full at this mega-port, then stop and report final credits and warp."
    if units <= 0:
        raise ValueError("units must be > 0")
    return (
        f"Recharge {units} units of warp power at this mega-port, "
        "then stop and report final credits and warp."
    )


def build_transfer_credits_prompt(
    *,
    amount: int,
    to_ship_name: str,
    to_ship_id: str | None = None,
) -> str:
    if amount <= 0:
        raise ValueError("amount must be > 0")
    normalized_ship_name = to_ship_name.strip()
    if not normalized_ship_name:
        raise ValueError("to_ship_name is required")

    ship_ref = normalized_ship_name
    if to_ship_id:
        normalized_ship_id = to_ship_id.strip()
        if not normalized_ship_id:
            raise ValueError("to_ship_id must be non-empty when provided")
        ship_ref = f"{ship_ref} [{normalized_ship_id[:6]}]"
    credit_label = "credit" if amount == 1 else "credits"

    return (
        f"Transfer {amount} {credit_label} to {ship_ref} in this sector, "
        "then stop and report final credits."
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


def build_engage_combat_prompt(*, player_name: str) -> str:
    normalized_player_name = player_name.strip()
    if not normalized_player_name:
        raise ValueError("player_name is required")
    return f"engage combat with player with name {normalized_player_name} in this sector"


def build_collect_salvage_prompt(*, salvage_id: str) -> str:
    normalized_salvage_id = salvage_id.strip()
    if not normalized_salvage_id:
        raise ValueError("salvage_id is required")
    return f"collect salvage id {normalized_salvage_id} in sector"


def build_garrison_deploy_prompt(
    *,
    quantity: int,
    mode: str = "offensive",
    toll_amount: int | None = None,
) -> str:
    if quantity <= 0:
        raise ValueError("quantity must be > 0")
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"offensive", "defensive", "toll"}:
        raise ValueError(f"unsupported garrison mode {mode!r}")
    if normalized_mode == "toll":
        if toll_amount is None:
            raise ValueError("toll_amount is required when mode is 'toll'")
        if toll_amount < 0:
            raise ValueError("toll_amount must be >= 0")
        return (
            f"Leave {quantity} fighters behind in this sector as a toll garrison "
            f"charging {toll_amount} credits."
        )
    article = "an" if normalized_mode.startswith("o") else "a"
    return f"Leave {quantity} fighters behind in this sector as {article} {normalized_mode} garrison."


def build_garrison_collect_prompt(*, quantity: int) -> str:
    if quantity <= 0:
        raise ValueError("quantity must be > 0")
    return f"Collect {quantity} fighters from the garrison in this sector."


def build_garrison_update_prompt(*, mode: str, toll_amount: int | None = None) -> str:
    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"offensive", "defensive", "toll"}:
        raise ValueError(f"unsupported garrison mode {mode!r}")
    parts = [f"Update garrison: mode={normalized_mode}"]
    if normalized_mode == "toll":
        if toll_amount is None:
            raise ValueError("toll_amount is required when mode is 'toll'")
        if toll_amount < 0:
            raise ValueError("toll_amount must be >= 0")
        parts.append(f"tollAmount={toll_amount}")
    return ", ".join(parts)


def build_ship_rename_prompt(*, ship_name: str) -> str:
    normalized_ship_name = ship_name.strip()
    if not normalized_ship_name:
        raise ValueError("ship_name is required")
    return f"Please rename my ship to '{normalized_ship_name}'"

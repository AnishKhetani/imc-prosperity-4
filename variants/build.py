"""
R5 Contingency Variant Builder
==============================
Generates 8 self-contained Trader variant files from submission.py.

Each output file is ready to submit to the IMC platform with zero
modifications. The build is purely textual replacement of the
configuration block (constants between
'# CONFIGURATION' and '# PRODUCT TAXONOMY').

Run:
    python variants/build.py            # builds all variants

Output: variants/built/<VARIANT_NAME>.py
"""

from __future__ import annotations

import os
import re
from typing import Dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "submission.py")
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "built")

# ---------------------------------------------------------------------------
# Variant definitions
# Each value is (header_doc, dict of constant overrides, optional post-class
# patch code that runs at module load — used for variants that need behaviour
# changes beyond simple constants).
# ---------------------------------------------------------------------------

VARIANTS: Dict[str, dict] = {
    # ------------------------------------------------------------------
    "CONTINGENCY_BASE": {
        "doc": "Identical to submission.py. Default round-start variant.",
        "overrides": {},
    },
    # ------------------------------------------------------------------
    "CONTINGENCY_P2_OFF": {
        "doc": (
            "Trip: PEBBLES residual std grows beyond 8 (vs base 2.8) OR "
            "P2 strategy MTM crosses -150 by tick 1500. PEBBLES basket "
            "constraint has broken; disable P2 take + MM, retain other "
            "strategies, give other MM strats slightly tighter quotes "
            "to recoup capital allocation."
        ),
        "overrides": {
            "ENABLE_P2": "False",
            "MM_PASSIVE_SIZE": "4",  # +1 — redirect P2 capital to other MM
        },
    },
    # ------------------------------------------------------------------
    "CONTINGENCY_PAIR_OFF": {
        "doc": (
            "Trip: SNACK CHOC+VAN deviation has |z|>2 for 500 consecutive "
            "ticks without mean-reversion (cointegration broken) OR "
            "S1+S2 strategy MTM crosses -150 by tick 1500. Disable pair "
            "stat-arb, fall back to symmetric MM on CHOC and VAN."
        ),
        "overrides": {
            "ENABLE_S1S2": "False",
            "PAIR_TAKE_SIZE": "0",
        },
    },
    # ------------------------------------------------------------------
    "CONTINGENCY_R2_OFF": {
        "doc": (
            "Trip: ROBOT_DISHES or ROBOT_IRONING tick-to-tick autocorr "
            "flips positive (>0.05) over rolling 200-tick window OR "
            "R2 strategy MTM crosses -100 by tick 1500. Roll-bounce "
            "regime confirmed; disable R2 fade entirely."
        ),
        "overrides": {
            "ENABLE_R2": "False",
        },
    },
    # ------------------------------------------------------------------
    "CONTINGENCY_NO_INSIDER": {
        "doc": (
            "Trip: BOTH P2 AND S1+S2 strategy PnLs flat or negative by "
            "tick 2000 (anomalies have been arbitraged out). Switch to "
            "pure-MM-only mode: disable all alpha-style strategies "
            "(P2, S1+S2, R2), widen MM half-spreads by +2 ticks, "
            "halve MM sizes to reduce adverse selection cost."
        ),
        "overrides": {
            "ENABLE_P2": "False",
            "ENABLE_S1S2": "False",
            "ENABLE_R2": "False",
            "MM_PASSIVE_SIZE": "2",
        },
        "post": (
            "# Widen all product half-spreads by +2 ticks (no-insider mode).\n"
            "for _k in list(PRODUCT_HALF_SPREAD.keys()):\n"
            "    PRODUCT_HALF_SPREAD[_k] = PRODUCT_HALF_SPREAD[_k] + 2\n"
        ),
    },
    # ------------------------------------------------------------------
    "CONTINGENCY_REGIME_SHIFT": {
        "doc": (
            "Trip: rolling 200-tick mid-volatility on ANY product exceeds "
            "2x its baseline std OR best-bid/best-ask spread on >=10 "
            "products doubles within 500 ticks. Volatility regime shift; "
            "halve all MM sizes, widen quotes by +3 ticks, raise emergency "
            "brake floor (more sensitive)."
        ),
        "overrides": {
            "MM_PASSIVE_SIZE": "1",
            "MM_TAKE_SIZE": "4",
            "P2_PASSIVE_SIZE": "1",
            "P2_TAKE_SIZE": "4",
            "PAIR_TAKE_SIZE": "3",
            "R2_INVENTORY_CAP": "2",
            "EMERGENCY_BRAKE_PNL": "-120.0",
            "GLOBAL_DD_BRAKE": "-500.0",
            "PEBBLES_TAKE_EDGE": "8.0",          # require larger edge
            "SNACK_PAIR_ENTRY_Z": "2.5",         # require stronger signal
        },
        "post": (
            "# Regime-shift: widen all product half-spreads by +3 ticks.\n"
            "for _k in list(PRODUCT_HALF_SPREAD.keys()):\n"
            "    PRODUCT_HALF_SPREAD[_k] = PRODUCT_HALF_SPREAD[_k] + 3\n"
        ),
    },
    # ------------------------------------------------------------------
    "CONTINGENCY_CROWDED_TRADE": {
        "doc": (
            "Trip: leaderboard movement consistent with another team "
            "running our P2 or S1+S2 strategy (rapid early gains then "
            "compression) OR our P2 fill rate drops below 30% of "
            "baseline at tick 2000. Tighten alpha thresholds, prefer "
            "passive MM over takes, smaller sizes on contested edges."
        ),
        "overrides": {
            "PEBBLES_TAKE_EDGE": "10.0",     # require huge edge to take
            "P2_TAKE_SIZE": "4",
            "SNACK_PAIR_ENTRY_Z": "2.5",
            "PAIR_TAKE_SIZE": "3",
            "MM_PASSIVE_SIZE": "2",          # don't be the marginal MM
        },
    },
    # ------------------------------------------------------------------
    "CONTINGENCY_DEFENSIVE": {
        "doc": (
            "Trip: total MTM drawdown crosses -400 (50% of GLOBAL_DD_BRAKE) "
            "OR any 2 strategies have hit per-strategy emergency brake. "
            "Pre-emptive defensive posture: halve all sizes, tighten "
            "every brake by 33%, suspend R2 (most fragile)."
        ),
        "overrides": {
            "ENABLE_R2": "False",
            "MM_PASSIVE_SIZE": "2",
            "MM_TAKE_SIZE": "4",
            "P2_PASSIVE_SIZE": "2",
            "P2_TAKE_SIZE": "4",
            "PAIR_TAKE_SIZE": "3",
            "EMERGENCY_BRAKE_PNL": "-130.0",
            "GLOBAL_DD_BRAKE": "-550.0",
        },
    },
    # ------------------------------------------------------------------
    "CONTINGENCY_LIQUIDATE": {
        "doc": (
            "Trip: total MTM drawdown crosses -700 (87% of GLOBAL_DD_BRAKE) "
            "OR any single tick MTM swing > 300 negative. Manual hard "
            "liquidation: force global_brake=True at first tick, cross "
            "spreads to flatten everything, post no new MM quotes."
        ),
        "overrides": {
            "ENABLE_P2": "False",
            "ENABLE_S1S2": "False",
            "ENABLE_S2": "False",
            "ENABLE_R2": "False",
            "ENABLE_M1": "False",
            "ENABLE_M3": "False",
            "GLOBAL_DD_BRAKE": "999999.0",  # never naturally trip; we force
        },
        "post": (
            "# Force global liquidation on every tick: monkey-patch _load_state\n"
            "# so the brake is always True regardless of stored traderData.\n"
            "_orig_load = Trader._load_state\n"
            "@staticmethod\n"
            "def _load_state(s):\n"
            "    d = _orig_load(s)\n"
            "    d['global_brake'] = True\n"
            "    return d\n"
            "Trader._load_state = _load_state\n"
        ),
    },
    # ====================================================================
    # V-SERIES — canonical Step-6 (corrected) variants. These have
    # mandated filenames trader_V<N>_<role>.py and map 1:1 to the
    # contingency triggers in the Decision Commander playbook.
    # ====================================================================
    "trader_V1_no_insider": {
        "filename": "trader_V1_no_insider.py",
        "doc": (
            "V1 :: CONTINGENCY_NO_INSIDER. All informed-participant signals "
            "have gone stale (P2 + S1+S2 + R2 each underperforming MC base "
            "at >=20% round). Switch to pure-MM-only mode: every alpha "
            "disabled, half-spreads +2, MM size halved to manage adverse "
            "selection on plain quotes."
        ),
        "overrides": {
            "ENABLE_P2": "False",
            "ENABLE_S1S2": "False",
            "ENABLE_R2": "False",
            "MM_PASSIVE_SIZE": "2",
        },
        "post": (
            "for _k in list(PRODUCT_HALF_SPREAD.keys()):\n"
            "    PRODUCT_HALF_SPREAD[_k] = PRODUCT_HALF_SPREAD[_k] + 2\n"
        ),
    },
    "trader_V2_high_vol": {
        "filename": "trader_V2_high_vol.py",
        "doc": (
            "V2 :: CONTINGENCY_HIGH_VOL. Realised volatility on >=10 "
            "products has crossed 2x its baseline std OR aggregate spread "
            "across MM products has doubled. Halve every size, widen "
            "half-spreads by +3, raise alpha edge thresholds, tighten "
            "every brake, shrink R2 inventory cap."
        ),
        "overrides": {
            "MM_PASSIVE_SIZE": "1",
            "MM_TAKE_SIZE": "4",
            "P2_PASSIVE_SIZE": "1",
            "P2_TAKE_SIZE": "4",
            "PAIR_TAKE_SIZE": "3",
            "R2_INVENTORY_CAP": "2",
            "EMERGENCY_BRAKE_PNL": "-120.0",
            "GLOBAL_DD_BRAKE": "-500.0",
            "PEBBLES_TAKE_EDGE": "8.0",
            "SNACK_PAIR_ENTRY_Z": "2.5",
        },
        "post": (
            "for _k in list(PRODUCT_HALF_SPREAD.keys()):\n"
            "    PRODUCT_HALF_SPREAD[_k] = PRODUCT_HALF_SPREAD[_k] + 3\n"
        ),
    },
    "trader_V3_adversarial": {
        "filename": "trader_V3_adversarial.py",
        "doc": (
            "V3 :: CONTINGENCY_ADVERSARIAL. Our passive orders are being "
            "picked off within 1-2 ticks of placement (post-fill PnL "
            "negative on >=10 fills in last 500 ticks). Solution by first "
            "principles: if every passive is adversely selected, the only "
            "safe quote is no quote. Switch to TAKE-ONLY mode with very "
            "high edge requirements; disable R2 (most exposed); trade "
            "minimum size on confirmed edges only."
        ),
        "overrides": {
            "ENABLE_R2": "False",
            "MM_PASSIVE_SIZE": "0",     # no passive quotes anywhere
            "MM_TAKE_SIZE": "2",        # tiny takes
            "P2_PASSIVE_SIZE": "0",
            "P2_TAKE_SIZE": "2",
            "PAIR_TAKE_SIZE": "2",
            "PEBBLES_TAKE_EDGE": "12.0",     # huge edge gate
            "SNACK_PAIR_ENTRY_Z": "3.0",
            "EMERGENCY_BRAKE_PNL": "-100.0",
        },
        "post": (
            "# Adversarial: force half-spreads to a sentinel that disables\n"
            "# any residual passive quoting code path, in case future\n"
            "# refactor adds a code path bypassing MM_PASSIVE_SIZE=0.\n"
            "for _k in list(PRODUCT_HALF_SPREAD.keys()):\n"
            "    PRODUCT_HALF_SPREAD[_k] = PRODUCT_HALF_SPREAD[_k] + 5\n"
        ),
    },
    "trader_V4_inventory_trap": {
        "filename": "trader_V4_inventory_trap.py",
        "doc": (
            "V4 :: CONTINGENCY_INVENTORY_TRAP. Position limits are being "
            "approached on >=3 products simultaneously and offload fills "
            "are not coming. Priority: liquidation above all else; no new "
            "directional positions until within 50% of limits. Disable "
            "every alpha. MM size minimal so fade-quotes still post on "
            "products with absolute position > 5."
        ),
        "overrides": {
            "ENABLE_P2": "False",
            "ENABLE_S1S2": "False",
            "ENABLE_R2": "False",
            "MM_PASSIVE_SIZE": "1",
            "MM_TAKE_SIZE": "1",
            "EMERGENCY_BRAKE_PNL": "-100.0",
            "GLOBAL_DD_BRAKE": "-400.0",
        },
        "post": (
            "# Inventory-trap: after the base clipper runs, drop any order on\n"
            "# a product whose abs(position) > 5 (50% of limit) if that order\n"
            "# would push the position further from zero.\n"
            "_orig_clip = Trader._clip_orders\n"
            "def _clip_orders(orders_in, positions):\n"
            "    out = _orig_clip(orders_in, positions)\n"
            "    for sym in list(out.keys()):\n"
            "        pos = positions.get(sym, 0)\n"
            "        if abs(pos) <= 5:\n"
            "            continue\n"
            "        bad_sign = 1 if pos > 0 else -1\n"
            "        kept = [o for o in out[sym]\n"
            "                if (1 if o.quantity > 0 else -1) != bad_sign]\n"
            "        if kept:\n"
            "            out[sym] = kept\n"
            "        else:\n"
            "            del out[sym]\n"
            "    return out\n"
            "Trader._clip_orders = staticmethod(_clip_orders)\n"
        ),
    },
    "trader_V5_signal_loss": {
        "filename": "trader_V5_signal_loss.py",
        "doc": (
            "V5 :: CONTINGENCY_SIGNAL_LOSS. Multiple components have "
            "tripped simultaneously OR the monitor cannot read order book "
            "data for >=5 products. Last active-trading variant before "
            "EMERGENCY_BRAKE. Pure MM only, minimum size, maximum spread, "
            "tightest brakes."
        ),
        "overrides": {
            "ENABLE_P2": "False",
            "ENABLE_S1S2": "False",
            "ENABLE_R2": "False",
            "MM_PASSIVE_SIZE": "1",
            "MM_TAKE_SIZE": "2",
            "EMERGENCY_BRAKE_PNL": "-80.0",
            "GLOBAL_DD_BRAKE": "-350.0",
        },
        "post": (
            "for _k in list(PRODUCT_HALF_SPREAD.keys()):\n"
            "    PRODUCT_HALF_SPREAD[_k] = PRODUCT_HALF_SPREAD[_k] + 4\n"
        ),
    },
    "trader_V6_emergency_brake": {
        "filename": "trader_V6_emergency_brake.py",
        "doc": (
            "V6 :: EMERGENCY_BRAKE. Total drawdown has crossed -700 OR a "
            "single-tick swing > 300 has fired. Force global_brake=True "
            "every tick. All alpha disabled. Engine flattens via Level 3 "
            "hard-liquidation logic in the base class. ONE-WAY DOOR — "
            "this variant cannot be reverted; once deployed it runs "
            "to round end."
        ),
        "overrides": {
            "ENABLE_P2": "False",
            "ENABLE_S1S2": "False",
            "ENABLE_S2": "False",
            "ENABLE_R2": "False",
            "ENABLE_M1": "False",
            "ENABLE_M3": "False",
            "GLOBAL_DD_BRAKE": "999999.0",
        },
        "post": (
            "_orig_load = Trader._load_state\n"
            "@staticmethod\n"
            "def _load_state(s):\n"
            "    d = _orig_load(s)\n"
            "    d['global_brake'] = True\n"
            "    return d\n"
            "Trader._load_state = _load_state\n"
        ),
    },
}


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

CONFIG_BLOCK_RE = re.compile(
    r"(# -+\n# CONFIGURATION\n# -+\n)(.*?)(# -+\n# PRODUCT TAXONOMY)",
    re.DOTALL,
)


def _patch_constants(src: str, overrides: Dict[str, str]) -> str:
    """Patch top-level constant assignments anywhere in the source.
    Each override key must already exist (assert on missing)."""
    # Stop at the first occurrence of `class Trader` so we never accidentally
    # patch constants inside method bodies.
    cls_idx = src.find("class Trader")
    if cls_idx < 0:
        raise RuntimeError("could not locate `class Trader`")
    head_src = src[:cls_idx]
    tail_src = src[cls_idx:]
    for name, new_value in overrides.items():
        pat = re.compile(
            r"^(" + re.escape(name) + r"(?:\s*:\s*[^=]+?)?\s*=\s*)([^\n#]+?)(\s*(#.*)?)$",
            re.MULTILINE,
        )
        if not pat.search(head_src):
            raise RuntimeError(f"constant {name} not found in module-level config")
        head_src = pat.sub(r"\g<1>" + new_value + r"\g<3>", head_src, count=1)
    return head_src + tail_src


def build_variant(name: str, spec: dict, base_src: str) -> str:
    overrides = dict(spec.get("overrides", {}))
    out = _patch_constants(base_src, overrides)
    # Inject variant marker INSIDE the existing top-of-file docstring so
    # `from __future__ import annotations` remains the first real statement.
    marker = (
        f"R5 CONTINGENCY VARIANT: {name}\n"
        f"{'=' * (24 + len(name))}\n\n"
        f"{spec['doc']}\n\n"
        f"Generated by variants/build.py — DO NOT edit by hand.\n\n"
        f"--- ORIGINAL HEADER FOLLOWS ---\n"
    )
    # Replace the first line of the existing module docstring with our marker.
    out = re.sub(
        r'^"""\n',
        '"""\n' + marker,
        out,
        count=1,
    )

    post = spec.get("post", "")
    if post:
        out = out.rstrip() + "\n\n\n# ---- variant post-patch ----\n" + post + "\n"
    return out


def main() -> int:
    with open(BASE, "r", encoding="utf-8") as f:
        base_src = f.read()

    os.makedirs(OUT_DIR, exist_ok=True)
    written = []
    for name, spec in VARIANTS.items():
        out = build_variant(name, spec, base_src)
        fname = spec.get("filename") or (name + ".py")
        path = os.path.join(OUT_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        written.append(path)
    print(f"Built {len(written)} variants:")
    for p in written:
        print(" ", os.path.relpath(p, ROOT).replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

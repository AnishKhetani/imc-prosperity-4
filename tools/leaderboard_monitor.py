"""
R5 Leaderboard Monitor
======================
Reads two leaderboard snapshots (CSV or JSON) and computes rank-velocity
intelligence:

  - per-team rank delta and velocity (ranks/hour or ranks/snapshot)
  - velocity z-score relative to teams within ±50 ranks (peer cohort)
  - flags anomalously fast movers + classifies their movement against
    the Decision Commander pattern taxonomy
  - emits "teams to watch" with the most-likely strategy interpretation

Snapshot format (CSV):
    team,rank,pnl
    Acme,1,123456
    ...

Snapshot format (JSON):
    [{"team": "Acme", "rank": 1, "pnl": 123456}, ...]

Usage:
    python tools/leaderboard_monitor.py snap_T1.csv snap_T2.csv
    python tools/leaderboard_monitor.py snap_T1.json snap_T2.json --top 25
    python tools/leaderboard_monitor.py snap_T1.csv snap_T2.csv \\
        --my-team "MyTeamName" --round-pct 40

The script is offline-only; it does NOT scrape the website. Capture the
leaderboard snapshots manually (copy/paste into CSV or use the website's
JSON if available).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple


# --------------------------------------------------------------------------
# Pattern taxonomy (from Decision Commander Part C)
# --------------------------------------------------------------------------

PATTERNS = [
    {
        "name": "EARLY_SPIKE",
        "description": "+200 ranks in first 20%, then stabilises",
        "likely_strategy": (
            "One-shot anomaly capture: caught a single large mispricing "
            "event (e.g. a basket-arb residual blowout) and locked it in. "
            "Implication: the market may have already corrected the same "
            "anomaly we are exploiting (P2 / S1+S2). Threat."
        ),
        "matcher": lambda v, r2: v >= 200 and r2 < 200,
    },
    {
        "name": "LINEAR_RISER",
        "description": "Steady ~constant velocity throughout the round",
        "likely_strategy": (
            "Pure market-making with disciplined inventory management. "
            "Implication: spread-capture edge is alive; we are competing "
            "on quote tightness. Threat to M1/M3 specifically."
        ),
        "matcher": lambda v, r2: 30 <= v <= 100 and r2 < 500,
    },
    {
        "name": "LATE_CRASH",
        "description": "Top performer for >60% then sharp drop",
        "likely_strategy": (
            "Concentrated directional/leveraged position that reversed. "
            "Implication: regime shift occurred; check our exposures vs "
            "the same regime variable. Opportunity if we are positioned "
            "neutral."
        ),
        "matcher": lambda v, r2: v <= -100 and r2 < 50,
    },
    {
        "name": "TOP_TURBULENCE",
        "description": "Top-10 team drops 50 ranks then recovers",
        "likely_strategy": (
            "Got adversarially targeted (front-run) but had reserve "
            "alpha to recover. Implication: someone is hunting top "
            "teams; our top-rank trip-wires must be sharper."
        ),
        "matcher": lambda v, r2: abs(v) >= 50 and r2 < 20,
    },
    {
        "name": "MASS_DROP",
        "description": "Multiple top-20 teams drop simultaneously",
        "likely_strategy": (
            "Market regime shift — a shared assumption broke (e.g. "
            "volatility doubled, a cointegration broke). Implication: "
            "deploy CONTINGENCY_REGIME_SHIFT immediately."
        ),
        "matcher": None,  # detected globally, not per-team
    },
    {
        "name": "SUDDEN_RISER",
        "description": "Anomalously fast jump for current rank cohort",
        "likely_strategy": (
            "Found an edge other teams (including us) missed. "
            "Implication: read their position changes if visible; "
            "consider partial replication."
        ),
        "matcher": lambda v, r2: v >= 80,  # backstop catch-all
    },
]


# --------------------------------------------------------------------------
# Snapshot I/O
# --------------------------------------------------------------------------

def _load_snapshot(path: str) -> Dict[str, dict]:
    """Return {team_name: {rank: int, pnl: float}}."""
    if not os.path.isfile(path):
        sys.stderr.write(f"ERROR: {path} not found\n")
        sys.exit(2)
    ext = os.path.splitext(path)[1].lower()
    out: Dict[str, dict] = {}
    if ext == ".json":
        with open(path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        rows = data if isinstance(data, list) else data.get("teams", [])
    else:  # csv
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
    for row in rows:
        name = str(row.get("team") or row.get("name") or "").strip()
        if not name:
            continue
        try:
            rank = int(row.get("rank") or 0)
        except (TypeError, ValueError):
            continue
        try:
            pnl = float(row.get("pnl") or row.get("score") or 0.0)
        except (TypeError, ValueError):
            pnl = 0.0
        out[name] = {"rank": rank, "pnl": pnl}
    return out


# --------------------------------------------------------------------------
# Velocity computation
# --------------------------------------------------------------------------

def _velocity(snap1: Dict[str, dict], snap2: Dict[str, dict]) -> List[dict]:
    """Compute velocity = rank improvement (snap1.rank - snap2.rank).
    Positive velocity = climbing the leaderboard."""
    rows = []
    for team, r2 in snap2.items():
        r1 = snap1.get(team)
        if r1 is None:
            continue
        v = r1["rank"] - r2["rank"]
        dpnl = r2["pnl"] - r1["pnl"]
        rows.append({
            "team": team,
            "rank_t1": r1["rank"],
            "rank_t2": r2["rank"],
            "velocity": v,
            "pnl_t1": r1["pnl"],
            "pnl_t2": r2["pnl"],
            "pnl_delta": dpnl,
        })
    return rows


def _peer_zscore(rows: List[dict], radius: int = 50) -> None:
    """For each row, compute z-score of velocity vs peers within ±radius
    ranks at T2. Mutates rows in place adding 'peer_z' field."""
    by_rank = sorted(rows, key=lambda r: r["rank_t2"])
    for r in rows:
        peers = [p["velocity"] for p in by_rank
                 if abs(p["rank_t2"] - r["rank_t2"]) <= radius and p is not r]
        if len(peers) < 3:
            r["peer_z"] = 0.0
            continue
        mean = sum(peers) / len(peers)
        var = sum((x - mean) ** 2 for x in peers) / max(1, len(peers) - 1)
        sd = math.sqrt(var) if var > 0 else 1.0
        r["peer_z"] = (r["velocity"] - mean) / sd


# --------------------------------------------------------------------------
# Pattern classification
# --------------------------------------------------------------------------

def _classify(row: dict, round_pct: Optional[float]) -> List[str]:
    """Return list of pattern names that match this row."""
    matched = []
    v = row["velocity"]
    r1 = row["rank_t1"]
    r2 = row["rank_t2"]
    # Re-evaluate matchers with both ranks available
    rules = [
        ("EARLY_SPIKE",     lambda: v >= 200 and r2 < 200
                                    and (round_pct is None or round_pct <= 25)),
        ("LINEAR_RISER",    lambda: 30 <= v <= 100 and r2 < 500),
        ("LATE_CRASH",      lambda: v <= -50 and r1 <= 20),
        ("TOP_TURBULENCE",  lambda: r1 <= 10 and abs(v) >= 30),
        ("SUDDEN_RISER",    lambda: v >= 80),
    ]
    for name, fn in rules:
        try:
            if fn():
                matched.append(name)
        except Exception:
            pass
    return matched


def _detect_mass_drop(rows: List[dict]) -> bool:
    """Detect if many top-20 teams dropped simultaneously."""
    top20_now = [r for r in rows if r["rank_t2"] <= 20]
    if len(top20_now) < 5:
        return False
    dropped = [r for r in top20_now if r["velocity"] <= -10]
    return len(dropped) >= 3


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def _print_table(rows: List[dict], top_n: int, my_team: Optional[str],
                 round_pct: Optional[float]) -> None:
    print()
    print(f"{'Rank T1':>7} {'Rank T2':>7} {'dRank':>7} {'dPnL':>10} "
          f"{'PeerZ':>6}  Team")
    print("-" * 70)
    rows_sorted = sorted(rows, key=lambda r: r["rank_t2"])
    for r in rows_sorted[:top_n]:
        marker = "*" if my_team and r["team"] == my_team else " "
        print(f"{r['rank_t1']:>7} {r['rank_t2']:>7} {r['velocity']:>+7} "
              f"{r['pnl_delta']:>+10,.0f} {r.get('peer_z',0):>+6.1f}  "
              f"{marker} {r['team']}")
    print()


def _print_watchlist(rows: List[dict], round_pct: Optional[float]) -> None:
    flagged = [r for r in rows if abs(r.get("peer_z", 0)) >= 1.5
               or abs(r["velocity"]) >= 80]
    if not flagged:
        print("  No anomalous movers detected.\n")
        return
    print("  TEAMS TO WATCH (peer_z >= 1.5 OR |velocity| >= 80):")
    print()
    flagged.sort(key=lambda r: -abs(r.get("peer_z", 0)))
    for r in flagged[:15]:
        patterns = _classify(r, round_pct)
        if not patterns:
            patterns = ["UNCLASSIFIED"]
        print(f"  - {r['team']:30s} rank {r['rank_t1']}->{r['rank_t2']} "
              f"(d{r['velocity']:+d}, z={r.get('peer_z',0):+.1f})")
        for pname in patterns:
            pat = next((p for p in PATTERNS if p["name"] == pname), None)
            if pat:
                print(f"      [{pname}] {pat['likely_strategy']}")
        print()


def _print_decision(rows: List[dict], my_team: Optional[str],
                    round_pct: Optional[float]) -> None:
    if _detect_mass_drop(rows):
        print("  >> SIGNAL: MASS_DROP detected in top 20.")
        print("  >> ACTION: deploy CONTINGENCY_REGIME_SHIFT.\n")
    me = next((r for r in rows if my_team and r["team"] == my_team), None)
    if me is not None:
        print(f"  YOUR POSITION: rank {me['rank_t1']} -> {me['rank_t2']} "
              f"(d{me['velocity']:+d}, dPnL {me['pnl_delta']:+,.0f})")
        if me["velocity"] <= -50:
            print("  >> Sharp rank drop. Consult playbook trip-wire table.")
        elif me["velocity"] >= 50:
            print("  >> Positive trajectory. Hold base unless trip-wire fires.")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("snapshot_t1")
    p.add_argument("snapshot_t2")
    p.add_argument("--top", type=int, default=20,
                   help="show this many top teams in raw table")
    p.add_argument("--my-team", type=str, default=None)
    p.add_argument("--round-pct", type=float, default=None,
                   help="approximate pct of round complete at T2 (for context)")
    p.add_argument("--peer-radius", type=int, default=50,
                   help="rank window for peer z-score")
    args = p.parse_args()

    s1 = _load_snapshot(args.snapshot_t1)
    s2 = _load_snapshot(args.snapshot_t2)
    rows = _velocity(s1, s2)
    if not rows:
        sys.stderr.write("ERROR: no overlapping teams between snapshots\n")
        return 1
    _peer_zscore(rows, radius=args.peer_radius)

    print(f"Snapshots: {args.snapshot_t1}  ->  {args.snapshot_t2}")
    print(f"Teams in both: {len(rows)}  (T1={len(s1)}, T2={len(s2)})")
    if args.round_pct is not None:
        print(f"Round complete: {args.round_pct:.0f}%")

    _print_table(rows, args.top, args.my_team, args.round_pct)
    _print_watchlist(rows, args.round_pct)
    _print_decision(rows, args.my_team, args.round_pct)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

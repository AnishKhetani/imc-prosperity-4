"""
R3 Manual: deep game-theoretic analysis & competitor simulation.

Builds on previous findings:
  - No-penalty optimum (single-player): (b1, b2) = (751, 836), EV/CP = 84.333
  - Bids only meaningful at 5k+1 (671, 676, ..., 916) due to discrete reserves on 5-grid.

This script:
  A) Recomputes joint-optimal b1 for EVERY candidate b2 (corrects earlier quick
     answer where I assumed b1=751 throughout).
  B) Models the competitor population with explicit level-k reasoning and
     simulates the resulting μ distribution over many "tournament" worlds.
  C) Computes EV, regret, and worst-case for every candidate strategy.
  D) Final pick.
"""
import numpy as np
import itertools
from collections import Counter

RES = np.arange(670, 921, 5)   # 51 reserves
N = len(RES)
RV = 920

def nb(b):
    return int(np.sum(RES < b))

def ev(b1, b2, mu):
    """Expected profit per counterparty with bids (b1, b2) and competitor mean b2 = mu.
    mu=None means no penalty (single-player)."""
    n1 = nb(b1)
    n2 = nb(b2) - n1
    p1 = n1 * (RV - b1) / N
    if mu is None or b2 > mu:
        s = 1.0
    else:
        # b2 <= mu: penalised
        if b2 >= RV:
            s = 0.0
        else:
            s = ((RV - mu) / (RV - b2)) ** 3
    return p1 + n2 * (RV - b2) * s / N


# Realistic bid grid: only 5k+1 makes sense for both b1 and b2
# (any other integer wastes margin for the same fill set).
# But we also include 5k for safety (some competitors may bid that way).
BID_GRID_OPT = [v for v in range(671, 920, 5)]   # 671, 676, ..., 916


# ============================================================
# A) For each plausible b2, find the OPTIMAL b1
# ============================================================
print("=" * 78)
print("A) Optimal (b1, b2) pair for each b2 candidate (no penalty / μ<b2)")
print("=" * 78)
print(f"{'b2':>5} | {'best b1':>8} | {'EV no-penalty':>14}")
no_pen_pairs = {}
for b2 in BID_GRID_OPT[:30]:   # b2 up to 821+30*5=821 (skip very high)
    if b2 < 700: continue
    best = max(((ev(b1, b2, None), b1) for b1 in BID_GRID_OPT if b1 < b2),
               default=(None, None))
    no_pen_pairs[b2] = (best[1], best[0])
    if 826 <= b2 <= 876:
        print(f"  {b2:>5} | {str(best[1]):>8} | {best[0]:14.4f}")

# Also include b2 in 5k+1 from 826..876
for b2 in [826, 831, 836, 841, 846, 851, 856, 861, 866, 871, 876]:
    best = max(((ev(b1, b2, None), b1) for b1 in BID_GRID_OPT if b1 < b2))
    no_pen_pairs[b2] = (best[1], best[0])

# ============================================================
# B) Symmetric Nash check on 5k+1 grid
# ============================================================
print("\n" + "=" * 78)
print("B) Symmetric Nash candidates on the 5k+1 grid")
print("=" * 78)
print("If everyone bids b2=μ (so b2 NOT > μ → scale=((920-μ)/(920-b2))^3=1),")
print("can a deviation to b2±5 strictly improve?")
print()
print(f"{'b2=μ':>5} | {'EV at μ':>8} | {'dev +5':>8} | {'dev -5':>10} | {'Nash?':>6}")
for b2 in [836, 841, 846, 851, 856, 861, 866, 871]:
    b1_star = no_pen_pairs[b2][0]
    base = ev(b1_star, b2, b2)
    up = ev(b1_star, b2 + 5, b2)
    # Optimal b1 may change if we deviate; recompute:
    up_full = max(ev(b1, b2 + 5, b2) for b1 in BID_GRID_OPT if b1 < b2 + 5)
    down_full = max(ev(b1, b2 - 5, b2) for b1 in BID_GRID_OPT if b1 < b2 - 5)
    is_nash = (base >= up_full - 1e-9) and (base >= down_full - 1e-9)
    print(f"  {b2:>5} | {base:8.4f} | {up_full:8.4f} | {down_full:10.4f} | {str(is_nash):>6}")


# ============================================================
# C) Competitor simulation (level-k thinking)
# ============================================================
print("\n" + "=" * 78)
print("C) Competitor population simulation")
print("=" * 78)

# Hypothesis on player types:
#  L0 ("naive"):       bid no-penalty optimum (b2=836)
#  L1:                 bid 841 (anticipating L0)
#  L2:                 bid 846 (anticipating L1)
#  L3:                 bid 851 (anticipating L2)
#  Conservative human: bid 851-866 with eyeball
#  Random/wide:        uniform 836-871
#
# Without strong empirical anchor we sweep mixes.

def sample_field(weights, n_players, rng):
    """weights: list of (b2_value, prob)."""
    vals, probs = zip(*weights)
    return rng.choice(vals, size=n_players, p=probs)

scenarios = {
    "Heavy-L0 (60% naive)": [(836, 0.60), (841, 0.20), (846, 0.10), (851, 0.05),
                             (856, 0.03), (861, 0.02)],
    "Even split L0/L1":     [(836, 0.40), (841, 0.40), (846, 0.10), (851, 0.05),
                             (856, 0.03), (861, 0.02)],
    "L1-dominated":         [(836, 0.25), (841, 0.45), (846, 0.20), (851, 0.06),
                             (856, 0.03), (861, 0.01)],
    "L2-shifted (AI savvy)":[(836, 0.15), (841, 0.30), (846, 0.30), (851, 0.15),
                             (856, 0.07), (861, 0.03)],
    "Conservative-heavy":   [(836, 0.20), (841, 0.25), (846, 0.20), (851, 0.15),
                             (856, 0.10), (861, 0.05), (866, 0.05)],
    "Last-yr-pattern (drift +2/70 ⇒ +7/250)":
                            [(836, 0.40), (841, 0.30), (846, 0.20), (851, 0.07),
                             (856, 0.03)],
}

rng = np.random.default_rng(2026)
N_PLAYERS = 1500           # IMC P3 had ~12k teams; field this big means avg is tight
N_TRIALS  = 8000

scenario_mu = {}
for name, w in scenarios.items():
    mus = []
    for _ in range(N_TRIALS):
        b2s = sample_field(w, N_PLAYERS, rng)
        mus.append(b2s.mean())
    mus = np.array(mus)
    scenario_mu[name] = mus
    print(f"  {name:46s}: μ mean={mus.mean():7.3f} std={mus.std():.3f} "
          f"5%={np.percentile(mus,5):.3f} 95%={np.percentile(mus,95):.3f}")


# ============================================================
# D) Strategy comparison: full (b1, b2) candidates
# ============================================================
print("\n" + "=" * 78)
print("D) Strategy comparison across scenarios")
print("=" * 78)

# Candidate strategies — both b1 and b2 jointly optimized for each b2 target
candidates = []
for b2_target in [836, 841, 846, 851, 856, 861, 866]:
    b1_star = no_pen_pairs[b2_target][0]
    candidates.append((b1_star, b2_target))
# Also include "lower b1" alternatives for risk-spread
candidates += [(751, 841), (751, 846), (756, 846), (761, 846), (756, 851)]
candidates = list(dict.fromkeys(candidates))    # dedupe preserving order

print(f"\n{'Strategy':>14} |", end="")
for name in scenarios:
    print(f" {name[:18]:>18} |", end="")
print()
for (b1, b2) in candidates:
    print(f"  ({b1},{b2}) |", end="")
    for name, mus in scenario_mu.items():
        evs = np.array([ev(b1, b2, mu) for mu in mus])
        print(f" {evs.mean():9.3f}±{evs.std():5.2f} |", end="")
    print()


# ============================================================
# E) Regret analysis
# ============================================================
print("\n" + "=" * 78)
print("E) Regret analysis: what's the worst regret of each strategy?")
print("=" * 78)
print("(For each scenario, compute optimum strategy in candidate set; my regret")
print(" = optimum_EV - my_EV.  Worst regret across scenarios is shown.)")

strat_mean_evs = {}
for (b1, b2) in candidates:
    strat_mean_evs[(b1, b2)] = {name: np.mean([ev(b1, b2, mu) for mu in mus])
                                  for name, mus in scenario_mu.items()}

print(f"\n{'Strategy':>14} | {'Avg EV':>8} | {'Max regret':>10} | {'Worst-case scen':>26}")
results = []
for cand in candidates:
    by_scen = strat_mean_evs[cand]
    regrets = {}
    for name in scenarios:
        opt = max(strat_mean_evs[c][name] for c in candidates)
        regrets[name] = opt - by_scen[name]
    avg_ev = np.mean(list(by_scen.values()))
    max_reg = max(regrets.values())
    worst = max(regrets, key=regrets.get)
    results.append((cand, avg_ev, max_reg, worst))
    print(f"  {str(cand):>14} | {avg_ev:8.3f} | {max_reg:10.3f} | {worst[:26]:>26}")

# Sort by max regret (lowest = best)
print("\nRanked by minimax regret (lower is better):")
for cand, avg_ev, mr, worst in sorted(results, key=lambda x: x[2]):
    print(f"  {str(cand):>14}: max regret = {mr:.3f} (in '{worst}'), avg EV = {avg_ev:.3f}")

print("\nRanked by average EV (higher is better):")
for cand, avg_ev, mr, worst in sorted(results, key=lambda x: -x[1]):
    print(f"  {str(cand):>14}: avg EV = {avg_ev:.3f}, max regret = {mr:.3f}")


# ============================================================
# F) Crossover analysis: μ-threshold where 841 → 846 dominance flips
# ============================================================
print("\n" + "=" * 78)
print("F) Threshold μ where (756,846) overtakes (751,841)")
print("=" * 78)
for mu in np.arange(836, 850, 0.5):
    e1 = ev(751, 841, mu)
    e2 = ev(756, 846, mu)
    diff = e2 - e1
    marker = " <-- crossover" if abs(diff) < 0.05 else ""
    print(f"  μ={mu:6.2f}: EV(751,841)={e1:.4f}  EV(756,846)={e2:.4f}  Δ={diff:+.4f}{marker}")


# ============================================================
# G) Probability that μ > X under each scenario
# ============================================================
print("\n" + "=" * 78)
print("G) P(μ > 841) and P(μ > 843) under each scenario")
print("=" * 78)
print(f"{'Scenario':46s} {'P(μ>841)':>10} {'P(μ>843)':>10} {'P(μ>846)':>10}")
for name, mus in scenario_mu.items():
    p1 = (mus > 841).mean()
    p2 = (mus > 843).mean()
    p3 = (mus > 846).mean()
    print(f"  {name:44s} {p1:>10.3f} {p2:>10.3f} {p3:>10.3f}")

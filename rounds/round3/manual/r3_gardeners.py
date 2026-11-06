"""
Round 3 Manual Challenge: The Celestial Gardeners' Guild
=========================================================

Problem statement (verbatim from notion page):
  - Reserve prices of counterparties are uniformly distributed at increments of 5
    between 670 and 920 (inclusive).  -> reserves R in {670, 675, ..., 920} (51 vals).
  - Resale value next day = 920.
  - Submit TWO bids (b1, b2) with b1 < b2 (WLOG).
  - For each counterparty with reserve r:
      * if b1 > r:  trade at b1, profit per unit = 920 - b1
      * elif b2 > r: trade at b2, BUT
            - if b2 > avg_b2 (mean across players): full profit 920 - b2
            - if b2 <= avg_b2: profit = (920 - b2) * ((920-avg_b2)/(920-b2))**3
              (penalty multiplier <= 1 when b2 <= avg_b2)
      * else: no trade.
  - Notion uses ">" so we use strict inequality.

We optimize EXPECTED profit per counterparty (number is secret but constant).
Bids are integers; reserves are on a 5-grid so optimal bids are 1 above grid (e.g. 671, 836).

This script:
  1. Brute force solves no-penalty optimum.
  2. Solves best response b2*(mu) for any belief about competitor mean.
  3. Solves symmetric Nash equilibrium for b2.
  4. Sweeps mu beliefs and ranks robust strategies.
  5. Outputs final recommendation.
"""
import numpy as np
import itertools

# ---- Distribution of reserves ----
RESERVES = np.arange(670, 921, 5)            # 670, 675, ..., 920
N_RES = len(RESERVES)                        # 51
RESALE = 920

def n_below_strict(b):
    """count of reserves r with r < b (strict trade rule)."""
    return int(np.sum(RESERVES < b))

def expected_profit(b1, b2, mu=None):
    """Expected profit per counterparty for bids (b1, b2) given belief about avg b2 = mu.
    If mu is None, we assume no penalty applies (b2 > mu)."""
    n1 = n_below_strict(b1)            # reserves served by b1
    n2 = n_below_strict(b2) - n1       # additional reserves served only by b2
    p1 = n1 / N_RES * (RESALE - b1)
    if mu is None or b2 > mu:
        scale = 1.0
    else:
        # b2 <= mu  (and b2 must still beat reserve to trade)
        scale = ((RESALE - mu) / (RESALE - b2)) ** 3 if b2 < RESALE else 0.0
    p2 = n2 / N_RES * (RESALE - b2) * scale
    return p1 + p2

# Bids: integers in [670, 920]. Optimal bids are r+1 for r on grid (671, 676, ...)
# We'll enumerate all integers in [670, 920]; the optimum will land at 5k+1.
BID_RANGE = list(range(670, 921))


def best_response(mu, b1_fixed=None):
    """Best (b1,b2) maximizing E[profit] given competitor mean mu.
    If b1_fixed given, only optimize b2."""
    best = (-1, None, None)
    if b1_fixed is None:
        for b1 in BID_RANGE:
            for b2 in BID_RANGE:
                if b2 <= b1:
                    continue
                ev = expected_profit(b1, b2, mu)
                if ev > best[0]:
                    best = (ev, b1, b2)
    else:
        b1 = b1_fixed
        for b2 in BID_RANGE:
            if b2 <= b1:
                continue
            ev = expected_profit(b1, b2, mu)
            if ev > best[0]:
                best = (ev, b1, b2)
    return best  # (ev, b1, b2)


# ---------- 1. No-penalty (single-player) optimum ----------
print("=" * 70)
print("STEP 1: No-penalty optimum (ignore competitor average)")
print("=" * 70)
ev0, b1_0, b2_0 = best_response(mu=None)
print(f"  Optimal (b1,b2) = ({b1_0}, {b2_0})")
print(f"  Expected profit per CP = {ev0:.4f}")

# Show the surface near optimum
print("\n  Grid around no-penalty optimum (top 10):")
all_vals = []
for b1 in BID_RANGE:
    for b2 in BID_RANGE:
        if b2 <= b1: continue
        all_vals.append((expected_profit(b1, b2, None), b1, b2))
all_vals.sort(reverse=True)
for v, b1, b2 in all_vals[:10]:
    print(f"    b1={b1}, b2={b2}, EV={v:.4f}")


# ---------- 2. Best b2 as function of belief mu ----------
print("\n" + "=" * 70)
print("STEP 2: Best response b2*(mu) given b1 = no-penalty optimum")
print("=" * 70)
print("(How does optimal b2 shift as we believe competitor mean of b2 varies?)")
mus = list(range(800, 921, 5))
for mu in mus:
    ev, b1, b2 = best_response(mu, b1_fixed=b1_0)
    print(f"  mu={mu}: best b2 = {b2}, EV per CP = {ev:.4f}")


# ---------- 3. Joint best response (b1 + b2) vs mu ----------
print("\n" + "=" * 70)
print("STEP 3: Joint best response (b1, b2) vs belief mu")
print("=" * 70)
joint = {}
for mu in mus:
    ev, b1, b2 = best_response(mu)
    joint[mu] = (ev, b1, b2)
    print(f"  mu={mu}: best (b1,b2)=({b1},{b2}), EV={ev:.4f}")


# ---------- 4. Symmetric Nash equilibrium ----------
print("\n" + "=" * 70)
print("STEP 4: Symmetric Nash equilibrium in b2")
print("=" * 70)
print("(All players bid the same b2; no one can benefit from deviating)")
# Iterate: start with no-penalty b2, find best response, etc.
# A Nash eq has best_response(mu).b2 == mu (approximately).
nash_candidates = []
for mu in BID_RANGE:
    ev, b1_br, b2_br = best_response(mu, b1_fixed=b1_0)
    if b2_br == mu:
        nash_candidates.append((mu, ev, b1_br, b2_br))
print(f"  Pure Nash candidates (b2*=mu) given b1={b1_0}:")
for mu, ev, b1, b2 in nash_candidates:
    print(f"    mu=b2={mu}, EV={ev:.4f}")

# Also: full joint Nash
print("\n  Joint Nash candidates (over both b1 and b2):")
nash_full = []
for mu in BID_RANGE:
    ev, b1_br, b2_br = best_response(mu)
    if b2_br == mu:
        nash_full.append((mu, ev, b1_br, b2_br))
for mu, ev, b1, b2 in nash_full:
    print(f"    mu=b2={mu}, b1={b1}, EV={ev:.4f}")


# ---------- 5. Robustness: EV under uncertainty about mu ----------
print("\n" + "=" * 70)
print("STEP 5: Robustness — EV of fixed strategies across mu beliefs")
print("=" * 70)
# Candidate strategies to compare
candidates = [
    (b1_0, b2_0),         # no-penalty optimum
    (b1_0, b2_0 + 5),
    (b1_0, b2_0 + 10),
    (b1_0, b2_0 + 15),
    (b1_0, b2_0 + 20),
    (b1_0, 871),
    (b1_0, 876),
    (b1_0, 881),
]
# unique
seen = set(); cands_u = []
for c in candidates:
    if c not in seen:
        seen.add(c); cands_u.append(c)

# Define a prior over mu: AI competitors will likely cluster between
# the no-penalty optimum (b2_0) and some upward shift due to penalty fear.
# Build a prior distribution (from very low to high) so we test robustness.
mu_grid = np.arange(820, 911, 1)
print(f"\n  Sweep mu in [{mu_grid[0]}, {mu_grid[-1]}]:")
print(f"  {'(b1,b2)':>14} | {'EV@mu=830':>10} | {'EV@mu=850':>10} | {'EV@mu=860':>10} | {'EV@mu=870':>10} | {'EV@mu=880':>10} | {'min EV':>8} | {'avg EV':>8}")
for (b1, b2) in cands_u:
    evs = [expected_profit(b1, b2, mu) for mu in mu_grid]
    spot = lambda m: expected_profit(b1, b2, m)
    print(f"  ({b1},{b2}) | "
          f"{spot(830):10.3f} | {spot(850):10.3f} | {spot(860):10.3f} | "
          f"{spot(870):10.3f} | {spot(880):10.3f} | "
          f"{min(evs):8.3f} | {np.mean(evs):8.3f}")


# ---------- 6. Monte Carlo: model AI competitors ----------
print("\n" + "=" * 70)
print("STEP 6: Monte Carlo with model of AI competitor population")
print("=" * 70)
# Model: opponents are a mixture
#   30% "naive no-penalty optimum"  -> b2 ~ Normal(b2_0, 3) clipped
#   40% "Nash-aware" bidders        -> b2 ~ Normal(nash_b2, 4)
#   20% "overshoot conservative"    -> b2 ~ Normal(nash_b2 + 10, 5)
#   10% "random within reasonable"  -> b2 ~ Uniform(820, 900)
# Take the LOWEST Nash candidate as "the" Nash for the model.
if nash_candidates:
    nash_b2 = nash_candidates[0][0]   # lowest mu Nash with given b1
else:
    nash_b2 = b2_0
print(f"  Using Nash reference b2 = {nash_b2}")

rng = np.random.default_rng(42)
N_PLAYERS = 1000  # simulated player population
N_TRIALS = 5000

mu_samples = []
for _ in range(N_TRIALS):
    types = rng.choice(4, size=N_PLAYERS, p=[0.30, 0.40, 0.20, 0.10])
    b2s = np.zeros(N_PLAYERS)
    m = types == 0
    b2s[m] = np.clip(rng.normal(b2_0, 3, m.sum()), 670, 920)
    m = types == 1
    b2s[m] = np.clip(rng.normal(nash_b2, 4, m.sum()), 670, 920)
    m = types == 2
    b2s[m] = np.clip(rng.normal(nash_b2 + 10, 5, m.sum()), 670, 920)
    m = types == 3
    b2s[m] = rng.uniform(820, 900, m.sum())
    mu_samples.append(b2s.mean())
mu_samples = np.array(mu_samples)
print(f"  Mu distribution: mean={mu_samples.mean():.2f}, "
      f"std={mu_samples.std():.2f}, 5%={np.percentile(mu_samples,5):.2f}, "
      f"95%={np.percentile(mu_samples,95):.2f}")

# Evaluate candidate strategies under this mu distribution
print("\n  Strategy ranking under MC distribution of mu:")
print(f"  {'(b1,b2)':>14} | {'mean EV':>10} | {'5% EV':>10} | {'95% EV':>10}")
ranked = []
for (b1, b2) in cands_u:
    evs = np.array([expected_profit(b1, b2, mu) for mu in mu_samples])
    ranked.append(((b1, b2), evs.mean(), np.percentile(evs, 5), np.percentile(evs, 95)))
ranked.sort(key=lambda x: -x[1])
for (b1b2, mean, lo, hi) in ranked:
    print(f"  {str(b1b2):>14} | {mean:10.4f} | {lo:10.4f} | {hi:10.4f}")


# ---------- 7. Brute force pick best b2 under MC mu ----------
print("\n" + "=" * 70)
print("STEP 7: Optimal b2 under MC distribution of mu (b1 fixed)")
print("=" * 70)
b2_search = list(range(b1_0 + 1, 921))
results = []
for b2 in b2_search:
    evs = np.array([expected_profit(b1_0, b2, mu) for mu in mu_samples])
    results.append((b2, evs.mean(), np.percentile(evs, 5)))
results.sort(key=lambda x: -x[1])
print("  Top 15 b2 by mean EV:")
for b2, mean, lo in results[:15]:
    print(f"    b2={b2}: mean EV={mean:.4f}, 5% EV={lo:.4f}")


# ---------- 8. Final recommendation ----------
print("\n" + "=" * 70)
print("FINAL RECOMMENDATION")
print("=" * 70)
best_b2 = results[0][0]
print(f"  Recommended b1 = {b1_0}")
print(f"  Recommended b2 = {best_b2}")
print(f"  Expected profit per CP (under MC) = {results[0][1]:.4f}")
print(f"  No-penalty upper bound EV          = {ev0:.4f}")

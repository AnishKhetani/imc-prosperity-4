"""Final R3 manual recommendation — fast version."""
import numpy as np
RES = np.arange(670, 921, 5)
N = len(RES)
RV = 920

def n_below(b):  # strict ">" trade rule
    return int(np.sum(RES < b))

def ev(b1, b2, mu):
    n1 = n_below(b1); n2 = n_below(b2) - n1
    p1 = n1 * (RV - b1) / N
    if mu is None or b2 > mu:
        s = 1.0
    else:
        s = ((RV - mu) / (RV - b2))**3 if b2 < RV else 0.0
    return p1 + n2 * (RV - b2) * s / N

# ---- 1. No-penalty optimum ----
best = max(((ev(b1,b2,None), b1, b2)
            for b1 in range(670,921) for b2 in range(b1+1,921)))
print(f"No-penalty optimum: b1={best[1]}, b2={best[2]}, EV/CP={best[0]:.4f}")

# ---- 2. Realistic AI competitor models ----
# Hypothesis: AI/quant teams (~half the field) will identify 836 as the no-penalty
# optimum and bid there or just above. Other half consists of humans who eyeball
# or "play safe" by bidding higher to avoid the penalty.

scenarios = {
    "AI-converged":       {"center": 836, "std": 3,  "skew": 0},   # everyone finds optimum
    "AI + slight overshoot": {"center": 840, "std": 5, "skew": 5},
    "Mixed field":        {"center": 850, "std": 12, "skew": 0},   # uncertainty
    "Conservative field": {"center": 865, "std": 10, "skew": 0},   # last yr 287 vs opt 285 (tight, but here range is wider)
    "Wide uncertainty":   {"center": 855, "std": 20, "skew": 0},
}

rng = np.random.default_rng(7)
N_SAMP = 50000

print("\nCandidate strategies — EV per CP under each scenario:")
candidates = [(751, b2) for b2 in [836, 841, 846, 851, 856, 861, 866, 871, 881]]
header = f"{'(b1,b2)':>14} | " + " | ".join(f"{k:>20}" for k in scenarios)
print(header)
for (b1,b2) in candidates:
    row = f"({b1},{b2})".rjust(14)
    for name, p in scenarios.items():
        mus = rng.normal(p["center"]+p["skew"], p["std"], N_SAMP).clip(670,920)
        evs = np.array([ev(b1,b2,m) for m in mus[:1500]])  # subsample for speed
        row += f" | {evs.mean():8.3f}±{evs.std():5.2f}     "
    print(row)

# ---- 3. Find b2 that maximizes EV averaged over a "consensus prior" ----
# Consensus prior: weight scenarios above by plausibility
weights = {"AI-converged": 0.30, "AI + slight overshoot": 0.30,
           "Mixed field": 0.20, "Conservative field": 0.10, "Wide uncertainty": 0.10}

print("\n\nWeighted-prior optimization (b1=751):")
print(f"  Weights: {weights}")
results = []
for b2 in range(752, 921):
    total = 0
    for name, p in scenarios.items():
        mus = rng.normal(p["center"]+p["skew"], p["std"], 2000).clip(670,920)
        evs = np.array([ev(751, b2, m) for m in mus])
        total += weights[name] * evs.mean()
    results.append((total, b2))
results.sort(reverse=True)
print("\n  Top 12 b2 values by weighted-prior mean EV:")
for v, b2 in results[:12]:
    print(f"    b2={b2}: weighted EV/CP = {v:.4f}")

# ---- 4. Worst-case (max-min) over scenarios ----
print("\n\nMax-min (worst-case) over scenarios, b1=751:")
maxmin = []
for b2 in range(752, 921):
    worst = float("inf")
    for name, p in scenarios.items():
        mus = rng.normal(p["center"]+p["skew"], p["std"], 2000).clip(670,920)
        evs = np.array([ev(751, b2, m) for m in mus])
        worst = min(worst, evs.mean())
    maxmin.append((worst, b2))
maxmin.sort(reverse=True)
print("  Top 12 b2 values by worst-case scenario mean EV:")
for v, b2 in maxmin[:12]:
    print(f"    b2={b2}: worst-case EV/CP = {v:.4f}")

print("\n\n=== RECOMMENDATION ===")
print(f"  b1 = 751   (captures reserves 670..750, profit 169 each, 17 reserves)")
print(f"  b2 = (see above)")

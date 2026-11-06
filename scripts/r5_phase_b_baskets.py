"""R5 Phase B (extension) — investigate SNACKPACK basket structure
and ROBOT_DISHES/OXYGEN_SHAKE mean reversion + size-hierarchy anomalies."""
import os, math
import numpy as np
import pandas as pd

ROOT = os.path.join(os.path.dirname(__file__), "..", "round_data", "ROUND_5")
DAYS = [2, 3, 4]

prices = pd.concat(
    [pd.read_csv(os.path.join(ROOT, f"prices_round_5_day_{d}.csv"), sep=";") for d in DAYS],
    ignore_index=True,
)
piv = prices.pivot_table(index=["day", "timestamp"], columns="product",
                          values="mid_price", aggfunc="first").sort_index()


def stat(arr, name=""):
    a = np.asarray(arr, dtype=float)
    a = a[~np.isnan(a)]
    if len(a) == 0:
        return
    print(f"  {name:50s}  mean={a.mean():+12.3f}  std={a.std():9.3f}  "
          f"min={a.min():+12.3f}  max={a.max():+12.3f}")


SP = ["SNACKPACK_CHOCOLATE", "SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY",
      "SNACKPACK_STRAWBERRY", "SNACKPACK_VANILLA"]

print("=" * 90)
print("SNACKPACK basket structure")
print("=" * 90)
print("\nIndividual mid means:")
for s in SP:
    stat(piv[s], s)

# Sum and mean of all five
print("\nSum / mean of all 5:")
allsum = piv[SP].sum(axis=1)
stat(allsum, "sum_all_5")
stat(allsum / 5.0, "mean_all_5")

# Pairs with high anti-corr suggest x + y = const candidates
print("\nPairwise sums / means (high |corr| pairs):")
for a, b in [("SNACKPACK_RASPBERRY", "SNACKPACK_STRAWBERRY"),
             ("SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA"),
             ("SNACKPACK_PISTACHIO", "SNACKPACK_STRAWBERRY"),
             ("SNACKPACK_PISTACHIO", "SNACKPACK_RASPBERRY")]:
    s = piv[a] + piv[b]
    d = piv[a] - piv[b]
    stat(s, f"sum  {a}+{b}")
    stat(d, f"diff {a}-{b}")

# Try OLS basket: predict each by linear combination of other four
print("\nLeast-squares decomposition: each product ~ alpha + sum b_i * other_i")
from itertools import combinations
mat = piv[SP].dropna()
print(f"  rows usable: {len(mat)}")
X_full = mat.values  # n x 5
for i, target in enumerate(SP):
    others = [j for j in range(5) if j != i]
    Y = X_full[:, i]
    Xo = np.column_stack([np.ones(len(Y)), X_full[:, others]])
    beta, *_ = np.linalg.lstsq(Xo, Y, rcond=None)
    yhat = Xo @ beta
    resid = Y - yhat
    r2 = 1 - resid.var() / Y.var()
    print(f"  {target:24s}  R2={r2:.4f}  alpha={beta[0]:+9.2f}  "
          f"betas={['%+0.3f' % b for b in beta[1:]]}  resid_std={resid.std():.3f}")

# Try ALL pairs (linear combo of 2 explains 1?) and 3-way subsets
print("\nFull 5-way OLS: best 2-other regressions per target:")
for i, target in enumerate(SP):
    others = [j for j in range(5) if j != i]
    Y = X_full[:, i]
    best = (-1, None)
    for combo in combinations(others, 2):
        Xo = np.column_stack([np.ones(len(Y))] + [X_full[:, c] for c in combo])
        beta, *_ = np.linalg.lstsq(Xo, Y, rcond=None)
        resid = Y - Xo @ beta
        r2 = 1 - resid.var() / Y.var()
        if r2 > best[0]:
            best = (r2, combo, beta, resid.std())
    r2, combo, beta, rsd = best
    names = [SP[c] for c in combo]
    print(f"  target={target:24s} r2={r2:.4f} combo=({names[0]},{names[1]}) "
          f"alpha={beta[0]:+8.2f} b1={beta[1]:+0.3f} b2={beta[2]:+0.3f} resid_std={rsd:.3f}")

# Test integer-coefficient hypotheses ('basket' style)
print("\nInteger-combination 'is this constant?' hypothesis tests:")
candidates = [
    ("CHOC+VAN", ["SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA"], [1, 1]),
    ("CHOC-VAN", ["SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA"], [1, -1]),
    ("RASP+STRAW", ["SNACKPACK_RASPBERRY", "SNACKPACK_STRAWBERRY"], [1, 1]),
    ("RASP+STRAW-PIST*?", None, None),  # filled below
    ("ALL_5_SUM", SP, [1, 1, 1, 1, 1]),
]
for label, prods, w in candidates:
    if prods is None: continue
    s = sum(c * piv[p] for c, p in zip(w, prods))
    stat(s, label)

# Test Pistachio vs (Strawberry - Raspberry):
# pistachio +0.913 strawberry, -0.831 raspberry. Try pistachio ~ a*(straw - rasp) + c
print("\nPISTACHIO vs (STRAWBERRY - RASPBERRY):")
y = piv["SNACKPACK_PISTACHIO"].values
x = (piv["SNACKPACK_STRAWBERRY"] - piv["SNACKPACK_RASPBERRY"]).values
mask = ~(np.isnan(y) | np.isnan(x))
y, x = y[mask], x[mask]
A = np.column_stack([np.ones_like(x), x])
beta, *_ = np.linalg.lstsq(A, y, rcond=None)
yhat = A @ beta
resid = y - yhat
r2 = 1 - resid.var() / y.var()
print(f"  pistachio = {beta[0]:+.2f} + {beta[1]:+.4f} * (straw - rasp)   R2={r2:.4f}  resid_std={resid.std():.3f}")

# ---------------- ROBOT group (DISHES has ACF1 = -0.232) ----------------
print("\n" + "=" * 90)
print("ROBOT — strong tick mean reversion candidates")
print("=" * 90)
RB = ["ROBOT_DISHES", "ROBOT_IRONING", "ROBOT_LAUNDRY", "ROBOT_MOPPING", "ROBOT_VACUUMING"]
for r in RB:
    df = prices[prices["product"] == r].sort_values(["day", "timestamp"])
    mids = df["mid_price"].astype(float).values
    rets = np.diff(mids)
    # microstructure: how often does price oscillate (sign flip rate)
    signs = np.sign(rets)
    flips = np.sum(signs[:-1] * signs[1:] < 0) / max(1, np.sum(signs[:-1] * signs[1:] != 0))
    # move size distribution
    sp = (df["ask_price_1"] - df["bid_price_1"]).values
    print(f"  {r:18s}  ret_std={rets.std():.3f}  flip_rate={flips:.3f}  "
          f"spread_med={np.nanmedian(sp):.1f}  abs_ret_med={np.median(np.abs(rets)):.2f}")

# ---------------- OXYGEN_SHAKE: kurtosis 14-15 means heavy tails -> events ----------------
print("\n" + "=" * 90)
print("OXYGEN_SHAKE — heavy-tail returns inspection")
print("=" * 90)
OS = ["OXYGEN_SHAKE_CHOCOLATE", "OXYGEN_SHAKE_EVENING_BREATH", "OXYGEN_SHAKE_GARLIC",
      "OXYGEN_SHAKE_MINT", "OXYGEN_SHAKE_MORNING_BREATH"]
for o in OS:
    df = prices[prices["product"] == o].sort_values(["day", "timestamp"])
    mids = df["mid_price"].astype(float).values
    rets = np.diff(mids)
    big = np.abs(rets) > 5 * rets.std()
    print(f"  {o:30s} kurt={pd.Series(rets).kurt():.2f} pct_>5sigma={big.mean()*100:.3f}% "
          f"max_jump={np.max(np.abs(rets)):.1f}")

# ---------------- PEBBLES_L < PEBBLES_M anomaly ----------------
print("\n" + "=" * 90)
print("PEBBLES — size hierarchy break (L < M on average)")
print("=" * 90)
for q in ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL"]:
    df = prices[prices["product"] == q]
    print(f"  {q:12s} day-mean: ", end="")
    for d in DAYS:
        m = df[df["day"] == d]["mid_price"].mean()
        print(f"d{d}={m:8.1f}  ", end="")
    print()

# Are L and M moving in lockstep (substitutes)?
s = piv["PEBBLES_L"] - piv["PEBBLES_M"]
stat(s, "PEBBLES_L - PEBBLES_M")
c = piv["PEBBLES_L"].corr(piv["PEBBLES_M"])
print(f"  level corr(L,M)={c:.4f}  return corr(L,M)={piv['PEBBLES_L'].diff().corr(piv['PEBBLES_M'].diff()):.4f}")

# Check whether PEBBLES_XL is a basket of others (since it's anti-corr to all four)
print("\nPEBBLES_XL ~ basket of others (OLS):")
mat = piv[["PEBBLES_XS","PEBBLES_S","PEBBLES_M","PEBBLES_L","PEBBLES_XL"]].dropna().values
Y = mat[:, 4]
X = np.column_stack([np.ones(len(Y)), mat[:, :4]])
beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
resid = Y - X @ beta
r2 = 1 - resid.var() / Y.var()
print(f"  XL = {beta[0]:+.2f} + {beta[1]:+.3f}*XS + {beta[2]:+.3f}*S + {beta[3]:+.3f}*M + {beta[4]:+.3f}*L   R2={r2:.4f}  resid_std={resid.std():.3f}")

# Sum of all 5 PEBBLES:
allsum = piv[["PEBBLES_XS","PEBBLES_S","PEBBLES_M","PEBBLES_L","PEBBLES_XL"]].sum(axis=1)
stat(allsum, "sum_all_5_PEBBLES")

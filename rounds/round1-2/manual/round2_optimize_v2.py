import numpy as np

LOG101 = np.log(101)

def research(r):
    if r <= 0: return 0.0
    return 200_000 * np.log(1 + r) / LOG101

def scale(sc):
    return 7 * sc / 100

def net_pnl(r, sc, sp, s):
    return research(r) * scale(sc) * s - (r + sc + sp) * 500

# ============================================================
# PART A: Find optimal R/S split for given T (= budget for R+S)
# Uses calculus: on boundary r+sc=T, optimize g(r) = R(r)*S(T-r)
# ============================================================
print("OPTIMAL R/S SPLIT (using full R+S budget T)")
print("-" * 70)
for T in [100, 95, 90, 85, 80, 75, 70, 60, 50]:
    best = max(range(0, T*100+1), 
               key=lambda r10: research(r10/100) * scale(T - r10/100))
    r = best/100
    sc = T - r
    print(f"  T={T:3d}: r={r:6.2f}%, sc={sc:6.2f}%, "
          f"R={research(r):10,.0f}, S={scale(sc):.3f}, "
          f"R*S={research(r)*scale(sc):12,.0f}, r/T={r/T*100:.1f}%")

# ============================================================
# PART B: Net PnL for various (sp, speed_mult) - assuming full budget
# ============================================================
print("\n\nNET PnL TABLE: rows=speed_mult, cols=sp% (using 100% budget)")
print("-" * 90)
header = "  s\\sp |" + "".join(f"{sp:>8d}%" for sp in range(0, 55, 5))
print(header)
print("-" * 90)

best_overall = {}
for s_100 in range(10, 95, 5):
    s = s_100 / 100
    row = f"  {s:.2f} |"
    for sp in range(0, 55, 5):
        T = 100 - sp
        if T <= 0:
            row += "      N/A"
            continue
        best_r10 = max(range(0, T*100+1),
                       key=lambda r10: research(r10/100) * scale(T - r10/100))
        r = best_r10/100
        sc = T - r
        pnl = net_pnl(r, sc, sp, s)
        row += f"{pnl:9,.0f}"
        key = f"s={s:.2f}"
        if key not in best_overall or pnl > best_overall[key][0]:
            best_overall[key] = (pnl, r, sc, sp)
    print(row)

print("\n\nBEST ALLOCATION FOR EACH SPEED MULTIPLIER (full budget)")
print("-" * 70)
for key in sorted(best_overall.keys()):
    pnl, r, sc, sp = best_overall[key]
    print(f"  {key}: r={r:.2f}%, sc={sc:.2f}%, sp={sp}%, net={pnl:,.0f}")

# ============================================================
# PART C: Value of speed multiplier at different sp allocations
# ============================================================
print("\n\nVALUE OF SPEED MULTIPLIER")
print("How much is each 0.1 increase in speed mult worth?")
print("-" * 70)
for sp in [0, 5, 10, 20, 30]:
    T = 100 - sp
    best_r10 = max(range(0, T*100+1),
                   key=lambda r10: research(r10/100) * scale(T - r10/100))
    r = best_r10/100
    sc = T - r
    rs_product = research(r) * scale(sc)
    print(f"  sp={sp:2d}%: R*S={rs_product:,.0f}, "
          f"value of s=0.1 increase = {rs_product * 0.1:,.0f} XIRECs")

# ============================================================
# PART D: Critical analysis - what sp gives best EXPECTED PnL?
# ============================================================
print("\n\n" + "=" * 80)
print("GAME THEORY: Expected PnL under population assumptions")
print("=" * 80)

np.random.seed(42)
N = 5000
NUM_SIMS = 200

def get_speed_mult(my_sp, others_sp):
    """Compute speed multiplier given my investment and others'"""
    all_sp = np.append(others_sp, my_sp)
    n = len(all_sp)
    
    # Sort descending to assign ranks
    order = np.argsort(-all_sp)
    sorted_sp = all_sp[order]
    
    # Assign ranks with ties
    ranks = np.zeros(n)
    i = 0
    while i < n:
        j = i + 1
        while j < n and sorted_sp[j] == sorted_sp[i]:
            j += 1
        for k in range(i, j):
            ranks[order[k]] = i + 1  # rank = position of first in group
        i = j
    
    my_rank = ranks[-1]
    max_rank = n
    
    if max_rank <= 1:
        return 0.5
    
    return 0.9 - (my_rank - 1) / (max_rank - 1) * 0.8

def expected_pnl(my_sp, pop_gen, T_for_rs=None):
    """Expected net PnL for a given speed investment and population generator"""
    if T_for_rs is None:
        T_for_rs = 100 - my_sp
    
    # Optimal R/S split
    T = T_for_rs
    best_r10 = max(range(0, int(T*100)+1),
                   key=lambda r10: research(r10/100) * scale(T - r10/100))
    r = best_r10/100
    sc = T - r
    
    mults = []
    for _ in range(NUM_SIMS):
        others = pop_gen(N - 1)
        s = get_speed_mult(my_sp, others)
        mults.append(s)
    
    avg_s = np.mean(mults)
    pnl = net_pnl(r, sc, my_sp, avg_s)
    return pnl, avg_s, r, sc

# Population models
populations = {
    "Uniform(0,30)": lambda n: np.random.uniform(0, 30, n),
    "Uniform(0,50)": lambda n: np.random.uniform(0, 50, n),
    "Beta(2,5)*40": lambda n: np.random.beta(2, 5, n) * 40,
    "Normal(10,5)": lambda n: np.clip(np.random.normal(10, 5, n), 0, 100),
    "Normal(15,8)": lambda n: np.clip(np.random.normal(15, 8, n), 0, 100),
    "Normal(20,10)": lambda n: np.clip(np.random.normal(20, 10, n), 0, 100),
    "60%@33+rest": lambda n: np.concatenate([np.full(int(n*0.6), 33.0), 
                                               np.random.uniform(0, 50, n - int(n*0.6))]),
    "Concentrated(5,3)": lambda n: np.clip(np.random.normal(5, 3, n), 0, 100),
    "Heavy_low": lambda n: np.random.exponential(8, n).clip(0, 100),
}

sp_values = [0, 1, 2, 3, 5, 8, 10, 15, 20, 25, 30, 33, 40, 50]

for pop_name, pop_gen in populations.items():
    print(f"\n  Population: {pop_name}")
    print(f"  {'sp%':>4s}  {'avg_s':>6s}  {'r%':>6s}  {'sc%':>6s}  {'net_pnl':>10s}")
    best_pnl = -1e18
    best_sp = 0
    for sp in sp_values:
        if sp > 95: continue
        pnl, avg_s, r, sc = expected_pnl(sp, pop_gen)
        if pnl > best_pnl:
            best_pnl = pnl
            best_sp = sp
        print(f"  {sp:4d}  {avg_s:6.3f}  {r:6.2f}  {sc:6.2f}  {pnl:10,.0f}")
    print(f"  >>> BEST: sp={best_sp}%, net PnL={best_pnl:,.0f}")

# ============================================================
# PART E: Robustness - what allocation is best across ALL scenarios?
# ============================================================
print("\n\n" + "=" * 80)
print("ROBUSTNESS: Average PnL across all population scenarios")
print("=" * 80)

avg_pnls = {}
for sp in sp_values:
    if sp > 95: continue
    total_pnl = 0
    count = 0
    for pop_name, pop_gen in populations.items():
        pnl, _, _, _ = expected_pnl(sp, pop_gen)
        total_pnl += pnl
        count += 1
    avg_pnls[sp] = total_pnl / count

print(f"\n  {'sp%':>4s}  {'avg_pnl_across_scenarios':>25s}")
for sp in sorted(avg_pnls.keys()):
    print(f"  {sp:4d}  {avg_pnls[sp]:25,.0f}")

best_robust_sp = max(avg_pnls, key=avg_pnls.get)
print(f"\n  MOST ROBUST sp = {best_robust_sp}%, avg PnL = {avg_pnls[best_robust_sp]:,.0f}")

# ============================================================
# PART F: Final recommendation with precise percentages
# ============================================================
print("\n\n" + "=" * 80)
print("FINAL ANALYSIS: Precise optimal allocations")
print("=" * 80)

for sp in [best_robust_sp, max(0, best_robust_sp-5), min(50, best_robust_sp+5)]:
    T = 100 - sp
    # Fine search for optimal r
    best_r10 = max(range(0, T*100+1),
                   key=lambda r10: research(r10/100) * scale(T - r10/100))
    r = best_r10 / 100
    sc = T - r
    
    print(f"\n  sp={sp}% → r={r:.2f}%, sc={sc:.2f}%")
    print(f"    Research = {research(r):,.0f}")
    print(f"    Scale    = {scale(sc):.3f}")
    print(f"    Budget   = {(r+sc+sp)*500:,.0f}")
    for s in [0.3, 0.5, 0.6, 0.7, 0.8, 0.9]:
        pnl = net_pnl(r, sc, sp, s)
        print(f"    At s={s:.1f}: gross={research(r)*scale(sc)*s:,.0f}, net={pnl:,.0f}")

print("\nDONE!")

import numpy as np
from scipy.optimize import minimize_scalar, minimize
import itertools

###############################################################################
# PROBLEM FORMULATION
# Budget: 50,000 XIRECs
# Allocate r%, sc%, sp% to Research, Scale, Speed (r + sc + sp <= 100)
#
# Research(r) = 200_000 * ln(1 + r) / ln(1 + 100)
# Scale(sc)   = 7 * sc / 100
# Speed(sp)   = rank-based multiplier [0.1, 0.9]
#
# PnL = Research(r) * Scale(sc) * Speed_mult - (r + sc + sp) * 500
###############################################################################

LOG101 = np.log(101)

def research(r):
    """Research value given r% allocation"""
    if r <= 0: return 0.0
    return 200_000 * np.log(1 + r) / LOG101

def scale(sc):
    """Scale value given sc% allocation"""
    return 7 * sc / 100

def gross_pnl(r, sc, speed_mult):
    """Gross PnL before budget deduction"""
    return research(r) * scale(sc) * speed_mult

def net_pnl(r, sc, sp, speed_mult):
    """Net PnL after budget deduction"""
    budget_used = (r + sc + sp) * 500
    return gross_pnl(r, sc, speed_mult) - budget_used

###############################################################################
# PART 1: Optimal R/S split for a given T = 100 - sp and speed multiplier s
###############################################################################
def optimal_rs_split(T, speed_mult):
    """Find optimal (r, sc) given T = r + sc budget and speed multiplier"""
    best_pnl = -1e18
    best_r = 0
    best_sc = 0
    # Fine grid search
    for r_100 in range(0, int(T * 100) + 1):
        r = r_100 / 100.0
        sc = T - r
        if sc < 0: continue
        pnl = gross_pnl(r, sc, speed_mult)
        if pnl > best_pnl:
            best_pnl = pnl
            best_r = r
            best_sc = sc
    return best_r, best_sc, best_pnl

print("="*80)
print("PART 1: Optimal Research/Scale split for various T and speed multipliers")
print("="*80)

for s in [0.1, 0.3, 0.5, 0.7, 0.9]:
    for T in [100, 95, 90, 80, 70, 60, 50]:
        r, sc, gp = optimal_rs_split(T, s)
        sp = 100 - T
        npnl = gp - (r + sc + sp) * 500
        print(f"  s={s:.1f}, T={T:3d} (sp={100-T:2d}): r={r:6.2f}%, sc={sc:6.2f}%, "
              f"gross={gp:12,.0f}, net={npnl:12,.0f}, r/(r+sc)={r/T*100:.1f}%")
    print()

###############################################################################
# PART 2: For each speed multiplier, what's the optimal allocation?
###############################################################################
print("="*80)
print("PART 2: Optimal allocation for each speed multiplier (using full budget)")
print("="*80)

for s in np.arange(0.1, 0.95, 0.05):
    T = 100  # Use full budget, sp = 0 for now
    r, sc, gp = optimal_rs_split(T, s)
    npnl = gp - 50000
    print(f"  s={s:.2f}: r={r:6.2f}%, sc={sc:6.2f}%, gross={gp:12,.0f}, net={npnl:12,.0f}")

###############################################################################
# PART 3: Net PnL as function of sp for various speed multiplier assumptions
###############################################################################
print("\n" + "="*80)
print("PART 3: Net PnL for various (sp, achieved_speed_mult) combinations")
print("="*80)

results = []
for sp in range(0, 51, 1):
    for s_10 in range(1, 10):
        s = s_10 / 10.0
        T = 100 - sp
        if T <= 0: continue
        r, sc, gp = optimal_rs_split(T, s)
        npnl = gp - 50000
        results.append((sp, s, r, sc, npnl))

# Show best allocation for each speed multiplier
print("\nBest sp for each speed multiplier:")
for s_10 in range(1, 10):
    s = s_10 / 10.0
    best = max([x for x in results if abs(x[1] - s) < 0.01], key=lambda x: x[4])
    sp, _, r, sc, npnl = best
    print(f"  s={s:.1f}: sp={sp:2d}%, r={r:6.2f}%, sc={sc:6.2f}%, net={npnl:12,.0f}")

###############################################################################
# PART 4: Game theory analysis - what speed multiplier do you get for sp?
###############################################################################
print("\n" + "="*80)
print("PART 4: Game Theory Analysis")
print("="*80)

# Simulate different population distributions
def simulate_speed_multiplier(my_sp, population_sp_dist, N=1000):
    """
    Given my speed investment and the distribution of others,
    compute my expected speed multiplier.
    """
    other_investments = population_sp_dist(N - 1)
    all_investments = np.append(other_investments, my_sp)
    
    # Rank: 1 = highest, N = lowest
    # Use argsort to rank (higher investment = better rank)
    sorted_idx = np.argsort(-all_investments)  # descending
    ranks = np.empty(N)
    
    # Handle ties: same investment = same rank
    sorted_vals = all_investments[sorted_idx]
    current_rank = 1
    i = 0
    while i < N:
        j = i
        while j < N and sorted_vals[j] == sorted_vals[i]:
            j += 1
        for k in range(i, j):
            ranks[sorted_idx[k]] = current_rank
        current_rank = j + 1
        i = j
    
    # Actually let me re-read the ranking. In the example:
    # investments: 70, 70, 70, 50, 40, 40, 30 → ranks: 1, 1, 1, 4, 5, 5, 7
    # So rank is based on position, with ties sharing the top rank of the group
    
    my_rank = ranks[-1]  # my entry is the last one
    max_rank = N
    
    if max_rank == 1:
        return 0.5  # all tied
    
    speed_mult = 0.9 - (my_rank - 1) / (max_rank - 1) * 0.8
    return speed_mult

# Different population scenarios
print("\nScenario: Uniform distribution of speed investments (0-30%)")
for my_sp in [0, 2, 5, 10, 15, 20, 25, 30]:
    mults = []
    for _ in range(50):
        s = simulate_speed_multiplier(my_sp, lambda n: np.random.uniform(0, 30, n))
        mults.append(s)
    avg_s = np.mean(mults)
    T = 100 - my_sp
    r, sc, gp = optimal_rs_split(T, avg_s)
    npnl = gp - 50000
    print(f"  sp={my_sp:2d}%: avg_mult={avg_s:.3f}, r={r:5.2f}%, sc={sc:5.2f}%, net={npnl:10,.0f}")

print("\nScenario: Most players invest little in speed (Beta(2,8) * 50)")
for my_sp in [0, 2, 5, 10, 15, 20, 25, 30]:
    mults = []
    for _ in range(50):
        s = simulate_speed_multiplier(my_sp, lambda n: np.random.beta(2, 8, n) * 50)
        mults.append(s)
    avg_s = np.mean(mults)
    T = 100 - my_sp
    r, sc, gp = optimal_rs_split(T, avg_s)
    npnl = gp - 50000
    print(f"  sp={my_sp:2d}%: avg_mult={avg_s:.3f}, r={r:5.2f}%, sc={sc:5.2f}%, net={npnl:10,.0f}")

print("\nScenario: Bimodal - 50% invest 0-5%, 50% invest 20-40%")
for my_sp in [0, 2, 5, 10, 15, 20, 25, 30]:
    mults = []
    for _ in range(50):
        def bimodal(n):
            low = np.random.uniform(0, 5, n // 2)
            high = np.random.uniform(20, 40, n - n // 2)
            return np.concatenate([low, high])
        s = simulate_speed_multiplier(my_sp, bimodal)
        mults.append(s)
    avg_s = np.mean(mults)
    T = 100 - my_sp
    r, sc, gp = optimal_rs_split(T, avg_s)
    npnl = gp - 50000
    print(f"  sp={my_sp:2d}%: avg_mult={avg_s:.3f}, r={r:5.2f}%, sc={sc:5.2f}%, net={npnl:10,.0f}")

print("\nScenario: Smart players - most invest 5-15% in speed (Normal(10,5) clipped)")
for my_sp in [0, 2, 5, 10, 15, 20, 25, 30]:
    mults = []
    for _ in range(50):
        s = simulate_speed_multiplier(my_sp, 
            lambda n: np.clip(np.random.normal(10, 5, n), 0, 50))
        mults.append(s)
    avg_s = np.mean(mults)
    T = 100 - my_sp
    r, sc, gp = optimal_rs_split(T, avg_s)
    npnl = gp - 50000
    print(f"  sp={my_sp:2d}%: avg_mult={avg_s:.3f}, r={r:5.2f}%, sc={sc:5.2f}%, net={npnl:10,.0f}")

print("\nScenario: 33/33/33 naive players dominate")
for my_sp in [0, 2, 5, 10, 15, 20, 25, 30, 33, 34, 35]:
    mults = []
    for _ in range(50):
        def naive_dist(n):
            # 60% invest exactly 33%, 40% random 0-50%
            naive = np.full(int(n * 0.6), 33.0)
            random_part = np.random.uniform(0, 50, n - int(n * 0.6))
            return np.concatenate([naive, random_part])
        s = simulate_speed_multiplier(my_sp, naive_dist)
        mults.append(s)
    avg_s = np.mean(mults)
    T = 100 - my_sp
    r, sc, gp = optimal_rs_split(T, avg_s)
    npnl = gp - 50000
    print(f"  sp={my_sp:2d}%: avg_mult={avg_s:.3f}, r={r:5.2f}%, sc={sc:5.2f}%, net={npnl:10,.0f}")

###############################################################################
# PART 5: Exhaustive search - best allocation for each speed multiplier
###############################################################################
print("\n" + "="*80)
print("PART 5: Top allocations for each speed multiplier scenario")
print("="*80)

for s in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
    best_pnl = -1e18
    best_alloc = None
    # Try integer percentages
    for r in range(0, 101):
        for sc in range(0, 101 - r):
            sp = 100 - r - sc
            pnl = net_pnl(r, sc, sp, s)
            if pnl > best_pnl:
                best_pnl = pnl
                best_alloc = (r, sc, sp)
    # Also try partial allocations (not using full budget)
    for r in range(0, 101):
        for sc in range(0, 101 - r):
            for sp in range(0, 101 - r - sc):
                pnl = net_pnl(r, sc, sp, s)
                if pnl > best_pnl:
                    best_pnl = pnl
                    best_alloc = (r, sc, sp)
    r, sc, sp = best_alloc
    print(f"  s={s:.1f}: r={r}%, sc={sc}%, sp={sp}%, total={r+sc+sp}%, net={best_pnl:,.0f}")
    print(f"         Research={research(r):,.0f}, Scale={scale(sc):.2f}")

###############################################################################
# PART 6: Fine-grained search around optimal region
###############################################################################
print("\n" + "="*80)
print("PART 6: Fine-grained search (0.1% increments) for s=0.5 through s=0.9")
print("="*80)

for s in [0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
    best_pnl = -1e18
    best_alloc = None
    for r_10 in range(0, 1001):
        r = r_10 / 10.0
        for sc_10 in range(0, 1001 - r_10):
            sc = sc_10 / 10.0
            sp = 100 - r - sc
            if sp < 0: continue
            pnl = net_pnl(r, sc, sp, s)
            if pnl > best_pnl:
                best_pnl = pnl
                best_alloc = (r, sc, sp)
    r, sc, sp = best_alloc
    print(f"  s={s:.1f}: r={r:.1f}%, sc={sc:.1f}%, sp={sp:.1f}%, net={best_pnl:,.0f}")

###############################################################################
# PART 7: What if we DON'T use all 100%? (partial budget)
###############################################################################
print("\n" + "="*80)
print("PART 7: Is it ever better to not use full budget?")
print("="*80)

for s in [0.3, 0.5, 0.7, 0.9]:
    best_pnl = -1e18
    best_alloc = None
    for total_pct in range(0, 101):
        T = total_pct
        # Optimize r, sc within T (sp = 0)
        for r_pct in range(0, T + 1):
            r = r_pct
            sc = T - r
            pnl = net_pnl(r, sc, 0, s)
            if pnl > best_pnl:
                best_pnl = pnl
                best_alloc = (r, sc, 0, T)
    r, sc, sp, T = best_alloc
    print(f"  s={s:.1f}: r={r}%, sc={sc}%, sp={sp}%, total={T}%, net={best_pnl:,.0f}")
    # Compare with full budget
    r100, sc100, gp100 = optimal_rs_split(100, s)
    pnl100 = gp100 - 50000
    print(f"         vs full budget: r={r100:.1f}%, sc={sc100:.1f}%, net={pnl100:,.0f}")

print("\n\nDONE!")

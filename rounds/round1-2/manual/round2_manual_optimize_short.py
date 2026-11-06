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


print('DONE')


import numpy as np
LOG101 = np.log(101)
def research(r):
    if r <= 0: return 0.0
    return 200_000 * np.log(1 + r) / LOG101
def scale(sc): return 7 * sc / 100
def net_pnl(r, sc, sp, s): return research(r) * scale(sc) * s - (r + sc + sp) * 500
def optimal_rs(T):
    best = max(range(0, int(T*100)+1), key=lambda r10: research(r10/100) * scale(T - r10/100))
    return best/100, T - best/100

np.random.seed(42)
N = 5000
SIMS = 100

def get_speed_mult(my_sp, others_sp):
    all_sp = np.append(others_sp, my_sp)
    n = len(all_sp)
    order = np.argsort(-all_sp)
    sorted_sp = all_sp[order]
    ranks = np.zeros(n)
    i = 0
    while i < n:
        j = i + 1
        while j < n and sorted_sp[j] == sorted_sp[i]: j += 1
        for k in range(i, j): ranks[order[k]] = i + 1
        i = j
    my_rank = ranks[-1]
    if n <= 1: return 0.5
    return 0.9 - (my_rank - 1) / (n - 1) * 0.8

populations = {
    'Uniform(0,30)': lambda n: np.random.uniform(0, 30, n),
    'Uniform(0,50)': lambda n: np.random.uniform(0, 50, n),
    'Beta(2,5)*40': lambda n: np.random.beta(2, 5, n) * 40,
    'Normal(10,5)': lambda n: np.clip(np.random.normal(10, 5, n), 0, 100),
    'Normal(15,8)': lambda n: np.clip(np.random.normal(15, 8, n), 0, 100),
    'Normal(20,10)': lambda n: np.clip(np.random.normal(20, 10, n), 0, 100),
    'Concentrated(5,3)': lambda n: np.clip(np.random.normal(5, 3, n), 0, 100),
    'Heavy_low_exp8': lambda n: np.random.exponential(8, n).clip(0, 100),
    '60pct@33+rest': lambda n: np.concatenate([np.full(int(n*0.6), 33.0), np.random.uniform(0, 50, n - int(n*0.6))]),
}

sp_values = [0, 1, 2, 3, 5, 8, 10, 12, 15, 18, 20, 25, 30, 33, 40, 50]

all_results = {}
for pop_name, pop_gen in populations.items():
    print(f'\nPopulation: {pop_name}')
    print(f'  sp%  avg_s    r%     sc%     net_pnl')
    best_pnl, best_sp = -1e18, 0
    for sp in sp_values:
        T = 100 - sp
        if T <= 0: continue
        r, sc = optimal_rs(T)
        mults = [get_speed_mult(sp, pop_gen(N-1)) for _ in range(SIMS)]
        avg_s = np.mean(mults)
        pnl = net_pnl(r, sc, sp, avg_s)
        if pnl > best_pnl: best_pnl, best_sp = pnl, sp
        print(f'  {sp:3d}  {avg_s:.3f}  {r:5.1f}  {sc:5.1f}  {pnl:10,.0f}')
        all_results[(pop_name, sp)] = pnl
    print(f'  >>> BEST: sp={best_sp}%, PnL={best_pnl:,.0f}')

print('\n\nROBUSTNESS: Average PnL across ALL scenarios')
print('-'*50)
for sp in sp_values:
    if sp > 50: continue
    vals = [all_results.get((p, sp), -1e18) for p in populations]
    avg = np.mean([v for v in vals if v > -1e17])
    print(f'  sp={sp:3d}%: avg_pnl = {avg:,.0f}')

best_sp_robust = max(sp_values[:sp_values.index(50)+1], key=lambda sp: np.mean([all_results.get((p, sp), -1e18) for p in populations]))
print(f'\nMOST ROBUST SPEED: {best_sp_robust}%')

# Final recommendation
print('\n\nFINAL RECOMMENDATION')
print('='*60)
sp = best_sp_robust
T = 100 - sp
r, sc = optimal_rs(T)
print(f'  Research: {r:.1f}%')
print(f'  Scale:    {sc:.1f}%')
print(f'  Speed:    {sp}%')
print(f'  Total:    {r+sc+sp:.1f}%')
print(f'\n  Research value: {research(r):,.0f}')
print(f'  Scale value:    {scale(sc):.3f}')
for s in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]:
    pnl = net_pnl(r, sc, sp, s)
    print(f'  At speed_mult={s:.1f}: net PnL = {pnl:,.0f}')

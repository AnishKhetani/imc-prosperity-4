"""Per-strike EDA for v11 design."""
import csv, math, io
from collections import defaultdict

DATA = "backtester_data/round3"
TTE_BY_DAY = {0: 8, 1: 7, 2: 6}  # historical TTE per day

def norm_cdf(x): return 0.5 * (1 + math.erf(x / math.sqrt(2)))

def bs_call(S, K, T, sigma):
    if T <= 0 or sigma <= 0 or S <= 0: return max(S - K, 0.0)
    sst = sigma * math.sqrt(T)
    d1 = (math.log(S/K) + 0.5*sigma*sigma*T) / sst
    d2 = d1 - sst
    return S*norm_cdf(d1) - K*norm_cdf(d2)

def bs_iv(price, S, K, T, sigma_init=0.25):
    if price <= 0 or T <= 0: return None
    if price < max(S-K, 0) - 1e-6 or price > S: return None
    sigma = sigma_init
    for _ in range(40):
        if sigma <= 0 or sigma > 5: return None
        sst = sigma*math.sqrt(T)
        d1 = (math.log(S/K) + 0.5*sigma*sigma*T)/sst
        p = S*norm_cdf(d1) - K*norm_cdf(d1-sst)
        vega = S*math.sqrt(T)*math.exp(-0.5*d1*d1)/math.sqrt(2*math.pi)
        if vega < 1e-8: return None
        diff = price - p
        if abs(diff) < 1e-4: return sigma
        sigma += diff/vega
    return sigma if 0.01 < sigma < 5 else None

def load_day(day):
    out = defaultdict(list)
    with open(f"{DATA}/prices_round_3_day_{day}.csv") as f:
        for r in csv.DictReader(f, delimiter=';'):
            try:
                bb = float(r['bid_price_1']) if r['bid_price_1'] else None
                ba = float(r['ask_price_1']) if r['ask_price_1'] else None
                if bb and ba:
                    out[r['product']].append((int(r['timestamp']), bb, ba, float(r['mid_price'])))
            except: pass
    return out

# ============== Per-product summary across all days ==============
print("="*78)
print("PER-PRODUCT SUMMARY (3 days × 10,000 ticks)")
print("="*78)
all_data = {d: load_day(d) for d in [0,1,2]}

prods = sorted(set(p for d in all_data for p in all_data[d]))
TTE_AT_LIVE = 5  # live round 3 day 3

for p in prods:
    print(f"\n[{p}]")
    for d in [0,1,2]:
        rows = all_data[d].get(p, [])
        if not rows: continue
        mids = [r[3] for r in rows]
        spreads = [r[2]-r[1] for r in rows]
        mean = sum(mids)/len(mids)
        std = (sum((m-mean)**2 for m in mids)/len(mids))**0.5
        # autocorr lag 1
        rets = [mids[i+1]-mids[i] for i in range(len(mids)-1)]
        if len(rets) > 10:
            mr = sum(rets)/len(rets)
            num = sum((rets[i]-mr)*(rets[i+1]-mr) for i in range(len(rets)-1))
            den = sum((r-mr)**2 for r in rets)
            ac1 = num/den if den > 0 else 0
        else: ac1 = 0
        print(f"  d{d}: mid={mean:.1f}±{std:.1f}  range=[{min(mids):.0f},{max(mids):.0f}]  end={mids[-1]:.0f}  spread={sum(spreads)/len(spreads):.1f}  AC1={ac1:+.3f}")

# ============== IV smile ==============
print("\n" + "="*78)
print("IMPLIED VOL SMILE (per strike, per day, sampled @ ts=500k)")
print("="*78)
strikes = [4000, 4500, 5000, 5100, 5200, 5300, 5400, 5500, 6000, 6500]
for d in [0,1,2]:
    T = TTE_BY_DAY[d] / 365.0
    vfe = all_data[d].get('VELVETFRUIT_EXTRACT', [])
    if not vfe: continue
    # find row near ts=500_000
    row = min(vfe, key=lambda r: abs(r[0]-500_000))
    S = row[3]
    print(f"\n  Day {d} (TTE={TTE_BY_DAY[d]}d, S={S:.1f}):")
    for K in strikes:
        sym = f"VEV_{K}"
        rows = all_data[d].get(sym, [])
        if not rows: continue
        r = min(rows, key=lambda x: abs(x[0]-500_000))
        mid = r[3]
        iv = bs_iv(mid, S, K, T)
        intrinsic = max(S-K, 0)
        m = math.log(K/S)/math.sqrt(T) if T>0 else 0
        print(f"    K={K:5d} mid={mid:7.2f} intr={intrinsic:6.1f} m={m:+.3f} IV={iv*100 if iv else 0:5.2f}%  spread={r[2]-r[1]:.1f}")

# ============== Liquidity / fill availability ==============
print("\n" + "="*78)
print("VOUCHER LIQUIDITY (n trades per day from trades CSV)")
print("="*78)
trade_counts = defaultdict(lambda: defaultdict(int))
for d in [0,1,2]:
    try:
        with open(f"{DATA}/trades_round_3_day_{d}.csv") as f:
            for r in csv.DictReader(f, delimiter=';'):
                trade_counts[r['symbol']][d] += 1
    except FileNotFoundError: pass
for s in sorted(trade_counts):
    cnts = [trade_counts[s][d] for d in [0,1,2]]
    print(f"  {s:25s} d0={cnts[0]:5d}  d1={cnts[1]:5d}  d2={cnts[2]:5d}  total={sum(cnts)}")

# ============== Realised vol of VFE ==============
print("\n" + "="*78)
print("VFE REALISED VOL")
print("="*78)
for d in [0,1,2]:
    rows = all_data[d].get('VELVETFRUIT_EXTRACT', [])
    if len(rows) < 2: continue
    mids = [r[3] for r in rows]
    rets = [math.log(mids[i+1]/mids[i]) for i in range(len(mids)-1)]
    sigma_per_step = (sum(r*r for r in rets)/len(rets))**0.5
    # 100 ts per step, 1M ts per day
    sigma_daily = sigma_per_step * math.sqrt(10_000)
    sigma_annual = sigma_daily * math.sqrt(365)
    print(f"  d{d}: σ/step={sigma_per_step*1e4:.2f}bps  σ_daily={sigma_daily*100:.2f}%  σ_annual={sigma_annual*100:.1f}%")

# ============== HGP mean reversion check ==============
print("\n" + "="*78)
print("HGP HALF-LIFE (OLS on x_{t+1}-x_t = -lambda*(x_t - mu))")
print("="*78)
for d in [0,1,2]:
    rows = all_data[d].get('HYDROGEL_PACK', [])
    if len(rows) < 100: continue
    mids = [r[3] for r in rows]
    mu = sum(mids)/len(mids)
    xs = [m - mu for m in mids[:-1]]
    ys = [mids[i+1] - mids[i] for i in range(len(mids)-1)]
    den = sum(x*x for x in xs)
    if den == 0: continue
    lam = -sum(xs[i]*ys[i] for i in range(len(xs)))/den
    half = math.log(2)/lam if lam > 0 else float('inf')
    print(f"  d{d}: mu={mu:.1f}  lambda={lam:.4f}  half_life={half:.0f} ticks  ({half/100:.0f}*100ts)")

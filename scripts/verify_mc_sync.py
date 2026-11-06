"""Verify MC bootstrap-sync fix preserves cross-asset invariants.

Tests:
  T1: PEBBLES 5-leg basket sum is preserved (≡ 50,000 ± small noise) under fixed bootstrap.
      Compares vs broken (independent-block) bootstrap which has huge std.
  T2: SNACKPACK CHOC+VAN cointegration target ≈ 19,940 preserved.
  T3: All R5 product histories have aligned timestamps (prerequisite for sync).
  T4: Length parity — every product has the same number of historical ticks.
  T5: Other potential coupled groups — check empirical correlations between
      products in same R5 group, before vs after sync, to flag structures
      we should also be syncing.
  T6: Per-leg marginal distribution preserved (mean, std) — sync should not
      bias individual leg statistics.
"""
from __future__ import annotations
import os, sys, json
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import montecarlo as mc

R5_GROUPS = {
    "PEBBLES": ["PEBBLES_XS", "PEBBLES_S", "PEBBLES_M", "PEBBLES_L", "PEBBLES_XL"],
    "SNACKPACK": ["SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA", "SNACKPACK_PISTACHIO",
                  "SNACKPACK_RASPBERRY", "SNACKPACK_STRAWBERRY"],
    "MICROCHIP": ["MICROCHIP_CIRCLE", "MICROCHIP_OVAL", "MICROCHIP_RECTANGLE",
                  "MICROCHIP_SQUARE", "MICROCHIP_TRIANGLE"],
    "GALAXY_SOUNDS": ["GALAXY_SOUNDS_BLACK_HOLES", "GALAXY_SOUNDS_DARK_MATTER",
                      "GALAXY_SOUNDS_PLANETARY_RINGS", "GALAXY_SOUNDS_SOLAR_FLAMES",
                      "GALAXY_SOUNDS_SOLAR_WINDS"],
    "OXYGEN_SHAKE": ["OXYGEN_SHAKE_CHOCOLATE", "OXYGEN_SHAKE_EVENING_BREATH",
                     "OXYGEN_SHAKE_GARLIC", "OXYGEN_SHAKE_MINT", "OXYGEN_SHAKE_MORNING_BREATH"],
    "PANEL": ["PANEL_1X2", "PANEL_1X4", "PANEL_2X2", "PANEL_2X4", "PANEL_4X4"],
    "ROBOT": ["ROBOT_DISHES", "ROBOT_IRONING", "ROBOT_LAUNDRY", "ROBOT_MOPPING",
              "ROBOT_VACUUMING"],
    "SLEEP_POD": ["SLEEP_POD_COTTON", "SLEEP_POD_LAMB_WOOL", "SLEEP_POD_NYLON",
                  "SLEEP_POD_POLYESTER", "SLEEP_POD_SUEDE"],
    "TRANSLATOR": ["TRANSLATOR_ASTRO_BLACK", "TRANSLATOR_ECLIPSE_CHARCOAL",
                   "TRANSLATOR_GRAPHITE_MIST", "TRANSLATOR_SPACE_GRAY",
                   "TRANSLATOR_VOID_BLUE"],
    "UV_VISOR": ["UV_VISOR_AMBER", "UV_VISOR_MAGENTA", "UV_VISOR_ORANGE",
                 "UV_VISOR_RED", "UV_VISOR_YELLOW"],
}


def mids(seq):
    return np.array([t["mid_price"] for t in seq if t.get("mid_price") is not None])


def empirical_check(historical):
    """T5: Empirical sum-stationarity for each group (in real history).
    Reports group-sum mean & std. Low std relative to mean → strong constraint."""
    print("\n=== T5: Empirical group-sum statistics in real R5 history ===")
    print(f"{'GROUP':<15} {'sum_mean':>12} {'sum_std':>10} {'rel_std%':>9}  COUPLING?")
    flagged = []
    for grp, syms in R5_GROUPS.items():
        try:
            arrs = [mids(historical[s]) for s in syms]
            n = min(len(a) for a in arrs)
            stack = np.column_stack([a[:n] for a in arrs])
            s = stack.sum(axis=1)
            mu, sd = float(s.mean()), float(s.std())
            rel = 100 * sd / abs(mu) if mu else float('inf')
            tag = ""
            if rel < 0.5:
                tag = "STRONG (sync this!)"
                flagged.append((grp, rel))
            elif rel < 2:
                tag = "moderate"
            print(f"{grp:<15} {mu:>12,.1f} {sd:>10,.1f} {rel:>8.3f}%  {tag}")
        except Exception as e:
            print(f"{grp:<15} ERROR {e}")
    return flagged


def check_alignment(historical):
    """T3 + T4."""
    print("\n=== T3/T4: Timestamp alignment & length parity ===")
    lens = {s: len(v) for s, v in historical.items()}
    L = list(set(lens.values()))
    print(f"Distinct lengths: {sorted(L)}; products per length:")
    for l in sorted(L):
        cnt = sum(1 for v in lens.values() if v == l)
        print(f"  len={l}  count={cnt}")
    # Sample one product to inspect timestamps
    s0 = next(iter(historical))
    ts0 = [t["timestamp"] for t in historical[s0][:5]]
    s1 = list(historical.keys())[1]
    ts1 = [t["timestamp"] for t in historical[s1][:5]]
    print(f"  {s0} first 5 ts: {ts0}")
    print(f"  {s1} first 5 ts: {ts1}")
    aligned = ts0 == ts1
    print(f"  -> Per-tick aligned: {aligned}")
    return aligned and len(L) == 1


def test_sync(historical, group_syms, label, n_ticks=2000, n_runs=5):
    """T1/T2: bootstrap sync test for an arbitrary group."""
    print(f"\n=== T1/T2: {label} ===")
    rng = np.random.default_rng(42)

    # Broken: per-symbol independent
    bg_broken = mc.BootstrapGenerator(historical, block_size=50, noise_scale=1.0,
                                       rng=rng)
    sums_broken_means = []
    sums_broken_stds = []
    for run in range(n_runs):
        seqs = {s: bg_broken.generate_sequence(s, n_ticks) for s in group_syms}
        arrs = [mids(seqs[s]) for s in group_syms]
        n = min(len(a) for a in arrs)
        s = np.column_stack([a[:n] for a in arrs]).sum(axis=1)
        sums_broken_means.append(s.mean())
        sums_broken_stds.append(s.std())

    # Fixed: synced
    rng2 = np.random.default_rng(42)
    bg_fixed = mc.BootstrapGenerator(historical, block_size=50, noise_scale=1.0,
                                      rng=rng2)
    sums_fixed_means = []
    sums_fixed_stds = []
    for run in range(n_runs):
        seqs = bg_fixed.generate_synced_sequences(group_syms, n_ticks)
        arrs = [mids(seqs[s]) for s in group_syms]
        n = min(len(a) for a in arrs)
        s = np.column_stack([a[:n] for a in arrs]).sum(axis=1)
        sums_fixed_means.append(s.mean())
        sums_fixed_stds.append(s.std())

    # Real history reference
    arrs_real = [mids(historical[s]) for s in group_syms]
    n = min(len(a) for a in arrs_real)
    s_real = np.column_stack([a[:n] for a in arrs_real]).sum(axis=1)
    real_mu, real_sd = float(s_real.mean()), float(s_real.std())

    bm = float(np.mean(sums_broken_means)); bs = float(np.mean(sums_broken_stds))
    fm = float(np.mean(sums_fixed_means)); fs = float(np.mean(sums_fixed_stds))
    print(f"Real history sum:    mean={real_mu:>12,.1f}  std={real_sd:>10,.2f}")
    print(f"Broken bootstrap:    mean={bm:>12,.1f}  std={bs:>10,.2f}  ({n_runs} runs)")
    print(f"Fixed (synced):      mean={fm:>12,.1f}  std={fs:>10,.2f}  ({n_runs} runs)")
    ratio = (bs / fs) if fs else float('inf')
    print(f"Std reduction:       {ratio:.1f}× (fixed is tighter)")
    pass_means = abs(fm - real_mu) < 100  # within 100 units
    pass_std = fs < 1.5 * real_sd  # within 50% of real
    print(f"  pass_means(<100)={pass_means}  pass_std(<1.5×real)={pass_std}")
    return pass_means and pass_std


def test_marginals(historical, syms, n_ticks=2000):
    """T6: per-symbol marginal mean/std preserved by sync vs broken."""
    print("\n=== T6: per-symbol marginal preservation ===")
    rng = np.random.default_rng(7)
    bg_fixed = mc.BootstrapGenerator(historical, block_size=50, noise_scale=1.0, rng=rng)
    seqs = bg_fixed.generate_synced_sequences(syms, n_ticks)
    print(f"{'SYM':<22} {'real_mu':>10} {'sync_mu':>10} {'real_sd':>9} {'sync_sd':>9}")
    ok = True
    for s in syms:
        real = mids(historical[s])
        sync = mids(seqs[s])
        rmu, rsd = real.mean(), real.std()
        smu, ssd = sync.mean(), sync.std()
        flag = ""
        if abs(smu - rmu) > 5 or abs(ssd - rsd) > 0.5 * max(rsd, 1):
            flag = " !"
            ok = False
        print(f"{s:<22} {rmu:>10,.1f} {smu:>10,.1f} {rsd:>9,.2f} {ssd:>9,.2f}{flag}")
    return ok


def main():
    print("Loading R5 historical data...")
    historical = mc.load_r5_historical(ROOT)
    print(f"  Loaded {len(historical)} products")

    aligned = check_alignment(historical)
    flagged = empirical_check(historical)

    print("\n" + "=" * 72)
    print("CRITICAL TESTS")
    print("=" * 72)
    t1 = test_sync(historical, R5_GROUPS["PEBBLES"], "T1: PEBBLES basket sum")
    t2 = test_sync(historical,
                    ["SNACKPACK_CHOCOLATE", "SNACKPACK_VANILLA"],
                    "T2: SNACKPACK CHOC+VAN cointegration")
    t6 = test_marginals(historical, R5_GROUPS["PEBBLES"])

    # Test any other strong-coupling group that the empirical check flagged
    other_passes = {}
    for grp, rel in flagged:
        if grp not in ("PEBBLES",):
            ok = test_sync(historical, R5_GROUPS[grp],
                            f"EXTRA: {grp} (empirical rel_std={rel:.3f}%)")
            other_passes[grp] = ok

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(f"T3/T4 alignment & length parity:   {'PASS' if aligned else 'FAIL'}")
    print(f"T1 PEBBLES basket sync:            {'PASS' if t1 else 'FAIL'}")
    print(f"T2 SNACKPACK pair sync:            {'PASS' if t2 else 'FAIL'}")
    print(f"T6 PEBBLES marginal preservation:  {'PASS' if t6 else 'FAIL'}")
    for g, ok in other_passes.items():
        print(f"   EXTRA {g}: {'PASS' if ok else 'FAIL'}")
    print(f"T5 flagged STRONG groups: {[g for g, _ in flagged]}")
    print()
    all_critical = aligned and t1 and t2 and t6
    print(f"All critical tests pass: {all_critical}")


if __name__ == "__main__":
    main()

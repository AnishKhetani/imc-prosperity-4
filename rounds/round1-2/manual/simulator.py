"""
Manual Challenge Auction Simulator - Round 1
=============================================
Finds optimal bid (price, quantity) for EMBER_MUSHROOM and DRYLAND_FLAX.

Auction mechanics:
  1. Clearing price chosen to maximize total traded volume
  2. Ties broken by higher price
  3. At clearing price: price priority, then time priority (we are LAST)
  4. Post-auction buyback at fixed prices

Fees:
  EMBER_MUSHROOM: 0.05 buy + 0.05 sell = 0.10 per unit total
  DRYLAND_FLAX: no fees
"""

import itertools
from typing import List, Tuple, Optional


def simulate_auction(
    existing_bids: List[Tuple[int, float]],  # [(volume, price), ...]
    existing_asks: List[Tuple[float, int]],  # [(price, volume), ...]
    my_bid_price: float,
    my_bid_qty: int,
    buyback_price: float,
    fee_per_unit: float,
) -> dict:
    """
    Simulate a single-price auction with our bid added.
    
    Returns dict with clearing_price, our_fill, profit, and debug info.
    """
    # Combine all bids (existing + ours)
    # Each entry: (price, volume, is_ours, time_priority)
    # Higher price = better priority. At same price, earlier time = better.
    # We are LAST in time priority.
    
    all_bids = []
    for vol, price in existing_bids:
        all_bids.append((price, vol, False))
    if my_bid_qty > 0:
        all_bids.append((my_bid_price, my_bid_qty, True))
    
    all_asks = []
    for price, vol in existing_asks:
        all_asks.append((price, vol))
    
    # Sort bids: descending by price (best first), ours last at same price
    all_bids.sort(key=lambda x: (-x[0], x[2]))  # x[2]=True sorts after False
    # Sort asks: ascending by price (best first)
    all_asks.sort(key=lambda x: x[0])
    
    # Cumulative supply and demand at each possible clearing price
    # Collect all unique prices
    prices = set()
    for p, v, _ in all_bids:
        prices.add(p)
    for p, v in all_asks:
        prices.add(p)
    prices = sorted(prices)
    
    best_clearing = None
    best_volume = -1
    
    for cp in prices:
        # Total bid volume at prices >= cp
        total_demand = sum(v for p, v, _ in all_bids if p >= cp)
        # Total ask volume at prices <= cp
        total_supply = sum(v for p, v in all_asks if p <= cp)
        # Traded volume = min(demand, supply)
        traded = min(total_demand, total_supply)
        
        # Maximize volume, break ties with higher price
        if traded > best_volume or (traded == best_volume and cp > best_clearing):
            best_volume = traded
            best_clearing = cp
    
    if best_clearing is None or best_volume == 0:
        return {
            "clearing_price": None,
            "total_volume": 0,
            "our_fill": 0,
            "profit": 0,
            "revenue": 0,
            "cost": 0,
            "fees": 0,
        }
    
    cp = best_clearing
    
    # Now determine our fill at the clearing price
    # All bids with price > cp get fully filled
    # At price == cp, allocation is by time priority (we are last)
    
    total_supply = sum(v for p, v in all_asks if p <= cp)
    
    # Volume consumed by bids strictly above clearing price
    vol_above_cp = sum(v for p, v, _ in all_bids if p > cp)
    
    # Remaining supply after higher-priority bids
    remaining = total_supply - vol_above_cp
    remaining = max(0, remaining)
    
    # Bids at clearing price: existing ones first (time priority), then ours
    existing_at_cp = sum(v for p, v, is_ours in all_bids if p == cp and not is_ours)
    our_vol_at_cp = my_bid_qty if my_bid_price == cp else 0
    # If our bid is above cp, we get price-priority fill
    our_vol_above_cp = my_bid_qty if my_bid_price > cp else 0
    
    if my_bid_price > cp:
        # We have price priority - filled among the "above cp" bids
        # But we need to figure out our share of the above-cp fills
        # All above-cp bids get filled first. Our bid is among them.
        # Since supply >= vol_above (otherwise cp would be different), 
        # we get fully filled as long as total supply covers it.
        our_fill = min(my_bid_qty, max(0, total_supply - (vol_above_cp - my_bid_qty)))
        our_fill = min(our_fill, my_bid_qty)
    elif my_bid_price == cp:
        # We are last at the clearing price level
        after_existing = remaining - existing_at_cp
        our_fill = max(0, min(my_bid_qty, after_existing))
    else:
        # Our bid is below clearing price - no fill
        our_fill = 0
    
    our_fill = int(our_fill)
    cost = our_fill * cp
    revenue = our_fill * buyback_price
    total_fees = our_fill * fee_per_unit
    profit = revenue - cost - total_fees
    
    return {
        "clearing_price": cp,
        "total_volume": best_volume,
        "our_fill": our_fill,
        "profit": profit,
        "revenue": revenue,
        "cost": cost,
        "fees": total_fees,
    }


def find_optimal_order(
    existing_bids: List[Tuple[int, float]],
    existing_asks: List[Tuple[float, int]],
    buyback_price: float,
    fee_per_unit: float,
    product_name: str,
    max_qty: int = 1_000_000,
):
    """
    Brute-force search over all feasible bid prices and quantities.
    """
    print(f"\n{'='*70}")
    print(f"  OPTIMIZING: {product_name}")
    print(f"  Buyback: {buyback_price}, Fee/unit: {fee_per_unit}")
    print(f"{'='*70}")
    
    # Show the existing order book
    print(f"\n  Existing Bids (buyers):")
    for vol, price in sorted(existing_bids, key=lambda x: -x[1]):
        print(f"    Price {price:6.1f}  |  Volume {vol:>8,}")
    print(f"\n  Existing Asks (sellers):")
    for price, vol in sorted(existing_asks, key=lambda x: x[0]):
        print(f"    Price {price:6.1f}  |  Volume {vol:>8,}")
    
    # First: simulate with NO order from us (baseline)
    baseline = simulate_auction(existing_bids, existing_asks, 0, 0, buyback_price, fee_per_unit)
    print(f"\n  Baseline (no order from us):")
    print(f"    Clearing price: {baseline['clearing_price']}")
    print(f"    Total volume:   {baseline['total_volume']:,}")
    
    # Price range to search: from 1 to max bid price
    ask_prices = [p for p, v in existing_asks]
    bid_prices = [p for v, p in existing_bids]
    _ = ask_prices  # suppress unused warning
    all_prices = sorted(set(ask_prices + bid_prices))
    
    # We want to buy below buyback so we profit
    # Search integer and half-integer prices
    min_price = min(all_prices) if all_prices else 1
    max_price = max(all_prices) if all_prices else 50
    
    search_prices = []
    p = min_price
    while p <= max_price + 1:
        search_prices.append(p)
        p += 1
    
    # Also search around each existing price +/- 1
    for ep in all_prices:
        for delta in [-1, 0, 1]:
            sp = int(ep + delta)
            if sp >= 1 and sp not in search_prices:
                search_prices.append(sp)
    search_prices = sorted(set(int(p) for p in search_prices))
    
    # For quantity, try a wide range  
    # The key quantities are the ask volumes at each level (to clear specific levels)
    ask_levels = sorted(existing_asks, key=lambda x: x[0])
    cumulative_ask_vol = []
    running = 0
    for price, vol in ask_levels:
        running += vol
        cumulative_ask_vol.append((price, running))
    
    # Generate candidate quantities
    qty_candidates = set()
    qty_candidates.add(1)
    for step in range(1000, max_qty + 1, 1000):
        qty_candidates.add(step)
    # Add specific ask-volume boundaries
    running = 0
    for price, vol in ask_levels:
        running += vol
        for delta in [-1000, 0, 1000]:
            q = running + delta
            if 0 < q <= max_qty:
                qty_candidates.add(q)
    # Add bid-volume boundaries
    running_bid = 0
    for vol, price in sorted(existing_bids, key=lambda x: -x[1]):
        running_bid += vol
        for delta in [-1000, 0, 1000]:
            q = running_bid + delta
            if 0 < q <= max_qty:
                qty_candidates.add(q)
    
    qty_candidates = sorted(qty_candidates)
    
    best_profit = -1e18
    best_result = None
    best_price = None
    best_qty = None
    
    results_by_price = {}
    
    for bp in search_prices:
        if bp >= buyback_price - fee_per_unit:
            # Can't profit if buy price >= effective buyback
            continue
        
        price_best_profit = 0
        price_best_qty = 0
        price_best_result = None
        
        for qty in qty_candidates:
            result = simulate_auction(
                existing_bids, existing_asks, bp, qty, buyback_price, fee_per_unit
            )
            
            if result["profit"] > price_best_profit:
                price_best_profit = result["profit"]
                price_best_qty = qty
                price_best_result = result
            
            if result["profit"] > best_profit:
                best_profit = result["profit"]
                best_result = result
                best_price = bp
                best_qty = qty
        
        if price_best_profit > 0:
            results_by_price[bp] = (price_best_profit, price_best_qty, price_best_result)
    
    # Show top results by price
    print(f"\n  Top results by bid price:")
    print(f"  {'Price':>7} | {'Qty':>10} | {'Clearing':>10} | {'Fill':>10} | {'Profit':>12}")
    print(f"  {'-'*7}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}-+-{'-'*12}")
    
    for bp in sorted(results_by_price.keys()):
        profit, qty, res = results_by_price[bp]
        print(f"  {bp:7.1f} | {qty:>10,} | {res['clearing_price']:>10} | {res['our_fill']:>10,} | {profit:>12,.2f}")
    
    if best_result is None or best_profit <= 0:
        print(f"\n  No profitable order found for {product_name}.")
        return None, 0, 0, {"clearing_price": None, "our_fill": 0, "profit": 0, "revenue": 0, "cost": 0, "fees": 0}
    
    print(f"\n  {'*'*50}")
    print(f"  OPTIMAL ORDER: BUY at price {best_price}, quantity {best_qty:,}")
    print(f"  Clearing price: {best_result['clearing_price']}")
    print(f"  Our fill:       {best_result['our_fill']:,}")
    print(f"  Revenue:        {best_result['revenue']:,.2f}")
    print(f"  Cost:           {best_result['cost']:,.2f}")
    print(f"  Fees:           {best_result['fees']:,.2f}")
    print(f"  PROFIT:         {best_result['profit']:,.2f}")
    print(f"  {'*'*50}")
    
    # Fine-tune: search around the best quantity with finer granularity
    print(f"\n  Fine-tuning quantity around {best_qty:,} at price {best_price}...")
    fine_best_profit = best_profit
    fine_best_qty = best_qty
    fine_best_result = best_result
    
    for q in range(max(1, best_qty - 5000), min(max_qty, best_qty + 5000) + 1, 100):
        result = simulate_auction(
            existing_bids, existing_asks, best_price, q, buyback_price, fee_per_unit
        )
        if result["profit"] > fine_best_profit:
            fine_best_profit = result["profit"]
            fine_best_qty = q
            fine_best_result = result
    
    if fine_best_qty != best_qty:
        print(f"  Refined: qty {best_qty:,} -> {fine_best_qty:,}, profit {best_profit:,.2f} -> {fine_best_profit:,.2f}")
        best_qty = fine_best_qty
        best_profit = fine_best_profit
        best_result = fine_best_result
    else:
        print(f"  No improvement from fine-tuning.")
    
    # Also try nearby prices with fine qty
    print(f"\n  Checking adjacent prices with fine quantity tuning...")
    for adj_price in [best_price - 1, best_price + 1]:
        if adj_price < 1 or adj_price >= buyback_price - fee_per_unit:
            continue
        for q in range(max(1, fine_best_qty - 10000), min(max_qty, fine_best_qty + 10000) + 1, 100):
            result = simulate_auction(
                existing_bids, existing_asks, adj_price, q, buyback_price, fee_per_unit
            )
            if result["profit"] > best_profit:
                best_profit = result["profit"]
                best_qty = q
                best_price = adj_price
                best_result = result
                print(f"  NEW BEST: price={adj_price}, qty={q:,}, profit={result['profit']:,.2f}")
    
    print(f"\n  {'='*50}")
    print(f"  FINAL OPTIMAL ORDER for {product_name}")
    print(f"  Action:         BUY")
    print(f"  Price:          {best_price}")
    print(f"  Quantity:       {best_qty:,}")
    print(f"  Clearing price: {best_result['clearing_price']}")
    print(f"  Our fill:       {best_result['our_fill']:,}")
    print(f"  Revenue:        {best_result['revenue']:,.2f}")
    print(f"  Cost:           {best_result['cost']:,.2f}")
    print(f"  Fees:           {best_result['fees']:,.2f}")
    print(f"  NET PROFIT:     {best_result['profit']:,.2f}")
    print(f"  {'='*50}")
    
    return best_price, best_qty, best_profit, best_result


def detailed_analysis(
    existing_bids, existing_asks, buyback_price, fee_per_unit, product_name
):
    """
    Show what happens at every possible clearing price without our order,
    then with our order, to build intuition.
    """
    print(f"\n{'='*70}")
    print(f"  DETAILED CLEARING PRICE ANALYSIS: {product_name}")
    print(f"{'='*70}")
    
    all_prices = sorted(set(
        [p for v, p in existing_bids] + [p for p, v in existing_asks]
    ))
    _ = all_prices  # suppress unused
    
    print(f"\n  Without our order:")
    print(f"  {'Price':>7} | {'Demand':>10} | {'Supply':>10} | {'Traded':>10}")
    print(f"  {'-'*7}-+-{'-'*10}-+-{'-'*10}-+-{'-'*10}")
    
    for cp in all_prices:
        demand = sum(vol for vol, price in existing_bids if price >= cp)
        supply = sum(vol for price, vol in existing_asks if price <= cp)
        traded = min(demand, supply)
        marker = " <-- MAX" if traded == max(
            min(sum(vol for vol, price in existing_bids if price >= p),
                sum(vol for price, vol in existing_asks if price <= p))
            for p in all_prices
        ) else ""
        print(f"  {cp:7.1f} | {demand:>10,} | {supply:>10,} | {traded:>10,}{marker}")


def main():
    # ============================================================
    # EMBER MUSHROOM
    # ============================================================
    ember_bids = [
        (43000, 20), (17000, 19), (6000, 18), (5000, 17),
        (10000, 16), (5000, 15), (10000, 14), (7000, 13),
    ]
    ember_asks = [
        (12, 20000), (13, 25000), (14, 35000), (15, 6000),
        (16, 5000), (17, 0), (18, 10000), (19, 12000),
    ]
    
    detailed_analysis(ember_bids, ember_asks, 20, 0.10, "EMBER_MUSHROOM")
    ember_price, ember_qty, ember_profit, ember_result = find_optimal_order(
        ember_bids, ember_asks,
        buyback_price=20,
        fee_per_unit=0.10,  # 0.05 buy + 0.05 sell
        product_name="EMBER_MUSHROOM",
    )
    
    # ============================================================
    # DRYLAND FLAX
    # ============================================================
    flax_bids = [
        (30000, 30), (5000, 29), (12000, 28), (28000, 27),
    ]
    flax_asks = [
        (28, 40000), (31, 20000), (32, 20000), (33, 30000),
    ]
    
    detailed_analysis(flax_bids, flax_asks, 30, 0, "DRYLAND_FLAX")
    flax_price, flax_qty, flax_profit, flax_result = find_optimal_order(
        flax_bids, flax_asks,
        buyback_price=30,
        fee_per_unit=0,  # no fees
        product_name="DRYLAND_FLAX",
    )
    
    # ============================================================
    # SUMMARY
    # ============================================================
    print(f"\n\n{'#'*70}")
    print(f"  FINAL SUMMARY - OPTIMAL ORDERS TO SUBMIT")
    print(f"{'#'*70}")
    print(f"\n  EMBER_MUSHROOM:")
    print(f"    BUY  price={ember_price}  qty={ember_qty:,}")
    print(f"    Expected profit: {ember_profit:,.2f}")
    print(f"\n  DRYLAND_FLAX:")
    print(f"    BUY  price={flax_price}  qty={flax_qty:,}")
    print(f"    Expected profit: {flax_profit:,.2f}")
    print(f"\n  TOTAL EXPECTED PROFIT: {ember_profit + flax_profit:,.2f}")
    print(f"{'#'*70}")


if __name__ == "__main__":
    main()

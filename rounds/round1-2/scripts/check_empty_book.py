"""Check how often order book sides are empty."""
import csv

for day in [-1, 0, 1]:
    fname = f"round_data/ROUND_2/prices_round_2_day_{day}.csv"
    aco_empty = 0
    ipr_empty = 0
    aco_total = 0
    ipr_total = 0
    
    with open(fname) as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            product = row['product']
            has_bid = row['bid_price_1'] != ''
            has_ask = row['ask_price_1'] != ''
            
            if product == 'ASH_COATED_OSMIUM':
                aco_total += 1
                if not has_bid or not has_ask:
                    aco_empty += 1
            else:
                ipr_total += 1
                if not has_bid or not has_ask:
                    ipr_empty += 1
    
    print(f"Day {day}: ACO empty={aco_empty}/{aco_total}, IPR empty={ipr_empty}/{ipr_total}")

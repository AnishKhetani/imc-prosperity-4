import json
import pandas as pd
import io
import numpy as np

log_path = r'.\logs\365182\365182.log'

with open(log_path, 'r') as f:
    data = json.load(f)

activities_csv = data['activitiesLog']
df_activities = pd.read_csv(io.StringIO(activities_csv), sep=';')

# Convert columns to appropriate types if necessary
df_activities['timestamp'] = pd.to_numeric(df_activities['timestamp'])
df_activities['profit_and_loss'] = pd.to_numeric(df_activities['profit_and_loss'])

trade_history = data['tradeHistory']
df_trades = pd.DataFrame(trade_history)

products = df_activities['product'].unique()
num_days = df_activities['day'].nunique()

print(f"Number of days in log: {num_days}")
print("-" * 30)

total_pnl = 0

for product in products:
    pdf = df_activities[df_activities['product'] == product].sort_values('timestamp')
    final_pnl = pdf['profit_and_loss'].iloc[-1]
    total_pnl += final_pnl
    
    # Max drawdown: running min of (PnL - running max)
    running_max = pdf['profit_and_loss'].cummax()
    drawdown = pdf['profit_and_loss'] - running_max
    max_drawdown = drawdown.min()
    
    # Submission fills
    if not df_trades.empty:
        prod_trades = df_trades[(df_trades['symbol'] == product) & 
                               ((df_trades['buyer'] == 'SUBMISSION') | (df_trades['seller'] == 'SUBMISSION'))]
        fill_count = len(prod_trades)
    else:
        fill_count = 0
        
    print(f"Product: {product}")
    print(f"  Final PnL: {final_pnl}")
    print(f"  Max Drawdown: {max_drawdown}")
    print(f"  Submission Fills: {fill_count}")
    
    # PnL trajectory at 10 checkpoints
    timestamps = pdf['timestamp'].unique()
    if len(timestamps) > 0:
        indices = np.linspace(0, len(timestamps) - 1, 10, dtype=int)
        checkpoints = []
        for idx in indices:
            ts = timestamps[idx]
            pnl_val = pdf[pdf['timestamp'] == ts]['profit_and_loss'].iloc[0]
            checkpoints.append((ts, pnl_val))
        print(f"  PnL Trajectory: {checkpoints}")
    print("-" * 10)

print(f"Total PnL across all products: {total_pnl}")
print("-" * 30)

if not df_trades.empty:
    submission_trades = df_trades[(df_trades['buyer'] == 'SUBMISSION') | (df_trades['seller'] == 'SUBMISSION')].copy()
    if not submission_trades.empty:
        submission_trades['side'] = submission_trades.apply(lambda x: 'BUY' if x['buyer'] == 'SUBMISSION' else 'SELL', axis=1)
        
        agg_trades = []
        for prod in products:
            pt = submission_trades[submission_trades['symbol'] == prod]
            count = len(pt)
            buys = pt[pt['side'] == 'BUY']
            sells = pt[pt['side'] == 'SELL']
            
            total_bought = buys['quantity'].sum()
            total_sold = sells['quantity'].sum()
            avg_buy = buys['price'].mean() if not buys.empty else 0
            avg_sell = sells['price'].mean() if not sells.empty else 0
            
            agg_trades.append({
                'product': prod,
                'count': count,
                'total_bought': total_bought,
                'total_sold': total_sold,
                'avg_buy': avg_buy,
                'avg_sell': avg_sell
            })
        
        print("Submission Fills Aggregated per Product:")
        for item in agg_trades:
            print(f"Product: {item['product']}")
            print(f"  Count: {item['count']}, Bought: {item['total_bought']}, Sold: {item['total_sold']}")
            print(f"  Avg Buy Price: {item['avg_buy']:.2f}, Avg Sell Price: {item['avg_sell']:.2f}")
    else:
        print("No submission fills found in tradeHistory.")
else:
    print("tradeHistory is empty.")

Loading data…
Loaded prices=360000 trades=4048

===== H0 :: SCHEMA & SANITY =====
Prices rows=360000, Trades rows=4048, days=[0, 1, 2]
Products missing from trades (i.e. NEVER traded historically): []
[VERDICT::H0] Counterparty columns anonymized=True. Products never traded: none.

===== H1 :: HYDROGEL stationarity & fair-value =====
[VERDICT::H1] mean=9990.81 std=31.935 ac1=-0.129 hurst=0.978 halflife=299.9401789468062

===== H2/H3 :: VELVETFRUIT returns, drift, fat-tailedness =====
[VERDICT::H2] mean=5250.1 ret_std=1.131 kurt=0.35 ac1=-0.1587 ac(sq,1)=0.1098 hurst=0.970 ann_vol=0.412

===== H4 :: Order-book imbalance predictive power =====
  VEV_4000        corr_imb_vs_fwd1             corr=+0.4827
  VEV_4000        corr_microprice_vs_fwd1      corr=+0.4802
  VEV_4500        corr_imb_vs_fwd1             corr=+0.4012
  VEV_4500        corr_microprice_vs_fwd1      corr=+0.3974
  VEV_5300        corr_imb_vs_fwd1             corr=+0.3533
  VEV_5300        corr_microprice_vs_fwd1      corr=+0.3496
  HYDROGEL_PACK   corr_imb_vs_fwd1             corr=+0.2989
  HYDROGEL_PACK   corr_microprice_vs_fwd1      corr=+0.2970
[VERDICT::H4] Top imbalance signal: ('VEV_4000', 'corr_imb_vs_fwd1', 0.4827401365878334)

===== H5 :: Persistent large resting volumes (whales) =====
  HYDROGEL_PACK q95 bidvol=29 askvol=29 top-recurring big bids={}
  VELVETFRUIT_EXTRACT q95 bidvol=67 askvol=67 top-recurring big bids={5242: np.int64(71), 5250: np.int64(71), 5241: np.int64(71), 5234: np.int64(68), 5235: np.int64(67)}
[VERDICT::H5] See forensic_summary.json for recurring whale prices.

===== H6 :: Volume clustering / periodicity =====
  VELVETFRUIT_EXTRACT: n_trades=1372 median_iat=16.0 top_fft_periods=[7.636062229023207, 2.1718409981140283, 3.8529146827950065]
  HYDROGEL_PACK: n_trades=1010 median_iat=20.0 top_fft_periods=[3.2580398997056577, 1494.3, 4.391125477519836]
[VERDICT::H6] Check top_fft_periods_ticks per product for bot refresh cadence.

===== H7 :: Volatility smile shape (day-by-day, strike-by-strike) =====
day  K     iv_mean  iv_std  n
 0  4000  0.7361  0.0715  976
 0  4500  0.4174  0.0294  3012
 0  5000  0.2339  0.0053  10000
 0  5100  0.2366  0.0036  10000
 0  5200  0.2322  0.0033  10000
 0  5300  0.2322  0.0036  10000
 0  5400  0.2221  0.0089  10000
 0  5500  0.2385  0.0027  10000
 0  6000  0.3550  0.0062  10000
 0  6500  0.5370  0.0059  10000
 1  4000  0.7886  0.0783  1004
 1  4500  0.4479  0.0319  3037
 1  5000  0.2322  0.0093  9999
 1  5100  0.2293  0.0076  10000
 1  5200  0.2355  0.0061  10000
 1  5300  0.2384  0.0031  10000
 1  5400  0.2211  0.0066  10000
 1  5500  0.2404  0.0071  10000
 1  6000  0.3786  0.0071  10000
 1  6500  0.5732  0.0068  10000
 2  4000  0.8538  0.0820  1006
 2  4500  0.4869  0.0357  2774
 2  5000  0.2330  0.0097  9977
 2  5100  0.2264  0.0067  10000
 2  5200  0.2324  0.0078  10000
 2  5300  0.2370  0.0070  10000
 2  5400  0.2202  0.0052  10000
 2  5500  0.2406  0.0075  10000
 2  6000  0.4053  0.0089  10000
 2  6500  0.6156  0.0085  10000
[VERDICT::H7] Parabolic smile fits: {0: {'a': 0.2266333194614197, 'b': -0.0057225918013187604, 'c': 0.15344103270557138, 'resid_std': 0.012832951070246528, 'n': 83988}, 1: {'a': 0.22709397375123597, 'b': -0.0032375700799238682, 'c': 0.14988309413894466, 'resid_std': 0.016738890093347836, 'n': 84040}, 2: {'a': 0.22618008285254917, 'b': 0.0006513203079394625, 'c': 0.14499938668326884, 'resid_std': 0.02012381556914678, 'n': 83757}}

===== H8 :: Term structure ATM IV across TTE =====
 day     mean      std  count  TTE_days
   0 0.232176 0.003110  10000         8
   1 0.237304 0.004585  10000         7
   2 0.234746 0.008201  10000         6
[VERDICT::H8] ATM IV linear extrap to live TTE=5d: 0.2373

===== H9 :: Butterfly / spread / intrinsic violations =====
  intrinsic_lower_bound: 0 violation ticks (sampled every 10 ticks)
  upper_bound_S: 0 violation ticks (sampled every 10 ticks)
  vertical_spread: 0 violation ticks (sampled every 10 ticks)
  butterfly: 0 violation ticks (sampled every 10 ticks)
[VERDICT::H9] Arb violations: {'intrinsic_lower_bound': 0, 'upper_bound_S': 0, 'vertical_spread': 0, 'butterfly': 0}

===== H10 :: Realized vs implied vol on ATM voucher =====
[VERDICT::H10] RV=0.4117 ATM_IV=0.2347 -> recommend LONG_VOL  (RV > IV: straddle buy + delta hedge)

===== H11 :: Quote-refresh periodicity =====
  HYDROGEL_PACK: frac_change=0.820 median_gap=1.0 mode_gap=1.0
  VELVETFRUIT_EXTRACT: frac_change=0.767 median_gap=1.0 mode_gap=1.0
  VEV_5100: frac_change=0.705 median_gap=1.0 mode_gap=1.0
  VEV_5200: frac_change=0.575 median_gap=1.0 mode_gap=1.0
  VEV_5300: frac_change=0.424 median_gap=1.0 mode_gap=1.0
  VEV_5400: frac_change=0.280 median_gap=2.0 mode_gap=1.0
[VERDICT::H11] See per-product quote-refresh stats above.

===== H12 :: Signed-trade impact on mid =====
  HYDROGEL_PACK             h1_side1_n                524
  HYDROGEL_PACK             h1_side1_meanmove         -0.07538167938931298
  HYDROGEL_PACK             h1_side-1_n               486
  HYDROGEL_PACK             h1_side-1_meanmove        0.029835390946502057
  HYDROGEL_PACK             h5_side1_n                524
  HYDROGEL_PACK             h5_side1_meanmove         -0.15171755725190839
  HYDROGEL_PACK             h5_side-1_n               486
  HYDROGEL_PACK             h5_side-1_meanmove        -0.027777777777777776
  HYDROGEL_PACK             h20_side1_n               524
  HYDROGEL_PACK             h20_side1_meanmove        -0.17557251908396945
  HYDROGEL_PACK             h20_side-1_n              486
  HYDROGEL_PACK             h20_side-1_meanmove       0.29218106995884774
  VELVETFRUIT_EXTRACT       h1_side1_n                781
  VELVETFRUIT_EXTRACT       h1_side1_meanmove         0.41613316261203587
  VELVETFRUIT_EXTRACT       h1_side-1_n               591
  VELVETFRUIT_EXTRACT       h1_side-1_meanmove        -0.11928934010152284
  VELVETFRUIT_EXTRACT       h5_side1_n                781
  VELVETFRUIT_EXTRACT       h5_side1_meanmove         0.4654289372599232
  VELVETFRUIT_EXTRACT       h5_side-1_n               591
  VELVETFRUIT_EXTRACT       h5_side-1_meanmove        0.012690355329949238
  VELVETFRUIT_EXTRACT       h20_side1_n               781
  VELVETFRUIT_EXTRACT       h20_side1_meanmove        0.5384122919334187
  VELVETFRUIT_EXTRACT       h20_side-1_n              591
  VELVETFRUIT_EXTRACT       h20_side-1_meanmove       -0.05245346869712352
[VERDICT::H12] See per-product asymmetric impact stats above.

===== H13 :: End-of-day behavior =====
  HYDROGEL_PACK day0: core_std=2.189 tail_std=2.235 tail_drift=-50.00
  HYDROGEL_PACK day1: core_std=2.149 tail_std=2.136 tail_drift=-18.00
  HYDROGEL_PACK day2: core_std=2.169 tail_std=2.191 tail_drift=+23.00
  VELVETFRUIT_EXTRACT day0: core_std=1.124 tail_std=1.049 tail_drift=+5.00
  VELVETFRUIT_EXTRACT day1: core_std=1.135 tail_std=1.130 tail_drift=+13.50
  VELVETFRUIT_EXTRACT day2: core_std=1.138 tail_std=1.143 tail_drift=+21.00
[VERDICT::H13] Compare tail_std vs core_std — >1.5x means volatile close.

===== H14 :: Cross-asset correlations =====
Top 10 return correlations (non-self):
  VEV_4000             VEV_4500             +0.913
  VEV_4500             VEV_4000             +0.913
  VEV_5000             VEV_5100             +0.901
  VEV_5100             VEV_5000             +0.901
  VEV_5000             VEV_4500             +0.864
  VEV_4500             VEV_5000             +0.864
  VEV_4500             VEV_5100             +0.839
  VEV_5100             VEV_4500             +0.839
  VEV_5000             VEV_5200             +0.834
  VEV_5200             VEV_5000             +0.834
[VERDICT::H14] HYDROGEL↔VELVET corr: 0.006

===== H15 :: Spread & tradeable edge per product =====
product                      px    sprd      bps      n
  HYDROGEL_PACK          9990.8   15.72     15.7  30000
  VELVETFRUIT_EXTRACT    5250.1    4.99      9.5  30000
  VEV_4000               1250.1   20.81    166.5  30000
  VEV_4500                750.1   15.85    211.3  30000
  VEV_5000                255.0    6.04    237.0  30000
  VEV_5100                166.8    4.30    257.5  30000
  VEV_5200                 95.5    2.89    302.3  30000
  VEV_5300                 46.8    2.11    450.6  30000
  VEV_5400                 16.0    1.38    866.0  30000
  VEV_5500                  6.6    1.15   1731.2  30000
  VEV_6000                  0.5    1.00  20000.0  30000
  VEV_6500                  0.5    1.00  20000.0  30000
[VERDICT::H15] Wider spread = more MM edge potential; penny-wide = pure queue priority.

===== H16 :: Regime stability across days =====
Products with regime instability (|Δmean|/mean > 2% or |Δretstd|/retstd > 25%):
  VEV_5000               mean-swing=2.09%  retstd-swing=2.6%
  VEV_5200               mean-swing=3.64%  retstd-swing=2.6%
  VEV_5300               mean-swing=9.92%  retstd-swing=1.9%
  VEV_5400               mean-swing=34.46%  retstd-swing=4.3%
  VEV_5500               mean-swing=52.22%  retstd-swing=14.9%
[VERDICT::H16] Stable-regime products = safer for fixed-param strategies. Unstable = need adaptive estimators.

===== H17 :: Fill density & available volume =====
  HYDROGEL_PACK          qty/day=    1359 trades/1000t= 33.67
  VELVETFRUIT_EXTRACT    qty/day=    2756 trades/1000t= 45.73
  VEV_4000               qty/day=     313 trades/1000t= 15.47
  VEV_4500               qty/day=       0 trades/1000t=  0.03
  VEV_5000               qty/day=       0 trades/1000t=  0.03
  VEV_5100               qty/day=       0 trades/1000t=  0.03
  VEV_5200               qty/day=      21 trades/1000t=  0.60
  VEV_5300               qty/day=     140 trades/1000t=  4.03
  VEV_5400               qty/day=     262 trades/1000t=  7.50
  VEV_5500               qty/day=     312 trades/1000t=  8.90
  VEV_6000               qty/day=     334 trades/1000t=  9.47
  VEV_6500               qty/day=     334 trades/1000t=  9.47
[VERDICT::H17] Low qty_per_day & trades_per_1000t = illiquid; MM strategy will starve.
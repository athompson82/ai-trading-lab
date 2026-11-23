# Holdout evaluation (one-time)

Period: 2023-11-23 to latest data. Code: 55505a793edd04b25c9467cf79ca15e7bd6ce9a8.

## etf_trend

|                 | etf_trend   | bench_spy   | bench_60_40   |
|:----------------|:------------|:------------|:--------------|
| start           | 2023-11-24  | 2023-11-24  | 2023-11-24    |
| end             | 2026-11-20  | 2026-11-20  | 2026-11-20    |
| final_equity    | 13106.05    | 34975.41    | 22636.23      |
| total_return    | 0.3378      | 0.5709      | 0.4063        |
| cagr            | 0.1027      | 0.1639      | 0.1214        |
| vol             | 0.095       | 0.157       | 0.1063        |
| sharpe          | 1.0771      | 1.045       | 1.131         |
| sortino         | 1.4833      | 1.5184      | 1.6591        |
| max_drawdown    | -0.0889     | -0.1876     | -0.1274       |
| calmar          | 1.1552      | 0.8738      | 0.9531        |
| psr_vs_0        | 0.9645      | 0.9658      | 0.9756        |
| costs_usd       | 62.46       | 0.0         | 3.5           |
| annual_turnover | 2.1704      | 0.0         | 0.0713        |

### Criteria (docs/PREREGISTRATION.md §4)

- **Q1 positive net return**: MET (CAGR 10.27%, 95% CI 1.18% to 20.18%)
- **Q2a Deflated Sharpe >= 0.95**: MET (DSR 0.960 over 5 trials)
- **Q2b P(beats each benchmark's Sharpe) >= 0.90**: NOT MET (bench_spy: 0.51, bench_60_40: 0.42)
- **Q2c smaller max drawdown than each benchmark**: MET (-8.9% vs bench_spy -18.8%, bench_60_40 -12.7%)
- **Q2 overall (a and b and c)**: NOT MET (lower risk only, no proven edge)
- **Q3a no more reliant on best 1% of days than primary benchmark**: MET (43% vs bench_spy 60%)
- **Q3b profit after removing best 10 days > 0**: MET ($1,412)
- **Q3c at least 2 of 3 holdout years positive**: MET (3/3: +18.1%, +7.9%, +4.9%)

<details><summary>Raw evidence</summary>

```
{
  "psr_vs_0": 0.9644905097155714,
  "dsr": 0.9603284990112736,
  "n_trials": 5,
  "bootstrap": {
    "bench_spy": {
      "sharpe_ci": [
        0.171901169891085,
        2.073378442381256
      ],
      "cagr_ci": [
        0.011794965771280391,
        0.20183939698531306
      ],
      "sharpe_diff_ci": [
        -0.7613062547037286,
        0.7602384303389984
      ],
      "p_strategy_better": 0.5105
    },
    "bench_60_40": {
      "sharpe_ci": [
        0.171901169891085,
        2.073378442381256
      ],
      "cagr_ci": [
        0.011794965771280391,
        0.20183939698531306
      ],
      "sharpe_diff_ci": [
        -0.797695486294728,
        0.6535965902205045
      ],
      "p_strategy_better": 0.4165
    }
  },
  "concentration": {
    "yearly_block_returns": [
      0.18064416489120183,
      0.07879578050087388,
      0.04893188610352239
    ],
    "best_1pct_days_share_of_pnl": 0.4291684862093264,
    "pnl_without_best_10_days": 1411.637590208682,
    "hit_rate_days": 0.552,
    "positive_years": 3,
    "n_years": 3
  },
  "primary_bench_concentration": {
    "yearly_block_returns": [
      0.3256865651824854,
      0.13270820381314352,
      0.04263364973145123
    ],
    "best_1pct_days_share_of_pnl": 0.5969723003214276,
    "pnl_without_best_10_days": 3142.3356412610556,
    "hit_rate_days": 0.5586666666666666,
    "positive_years": 3,
    "n_years": 3
  }
}
```
</details>

## crypto_trend

|                 | crypto_trend   | bench_btc   | bench_btc_eth_50_50   |
|:----------------|:---------------|:------------|:----------------------|
| start           | 2023-11-23     | 2023-11-23  | 2023-11-23            |
| end             | 2026-11-22     | 2026-11-22  | 2026-11-22            |
| final_equity    | 92613.85       | 450363.22   | 940874.49             |
| total_return    | 0.3663         | 0.6396      | 0.261                 |
| cagr            | 0.1096         | 0.1792      | 0.0804                |
| vol             | 0.35           | 0.4706      | 0.5441                |
| sharpe          | 0.4716         | 0.5844      | 0.4126                |
| sortino         | 0.6985         | 0.8756      | 0.6111                |
| max_drawdown    | -0.4996        | -0.5308     | -0.6061               |
| calmar          | 0.2195         | 0.3376      | 0.1326                |
| psr_vs_0        | 0.7936         | 0.8452      | 0.7632                |
| costs_usd       | 10153.9        | 0.0         | 9061.52               |
| annual_turnover | 3.6888         | 0.0         | 0.3067                |

### Criteria (docs/PREREGISTRATION.md §4)

- **Q1 positive net return**: MET (CAGR 10.96%, 95% CI -27.28% to 71.14%)
- **Q2a Deflated Sharpe >= 0.95**: NOT MET (DSR 0.736 over 6 trials)
- **Q2b P(beats each benchmark's Sharpe) >= 0.90**: NOT MET (bench_btc: 0.33, bench_btc_eth_50_50: 0.58)
- **Q2c smaller max drawdown than each benchmark**: MET (-50.0% vs bench_btc -53.1%, bench_btc_eth_50_50 -60.6%)
- **Q2 overall (a and b and c)**: NOT MET (lower risk only, no proven edge)
- **Q3a no more reliant on best 1% of days than primary benchmark**: NOT MET (349% vs bench_btc 281%)
- **Q3b profit after removing best 10 days > 0**: NOT MET ($-61,734)
- **Q3c at least 2 of 3 holdout years positive**: NOT MET (1/3: +109.8%, -11.5%, -26.4%)

<details><summary>Raw evidence</summary>

```
{
  "psr_vs_0": 0.7936273455414892,
  "dsr": 0.7361841964104877,
  "n_trials": 6,
  "bootstrap": {
    "bench_btc": {
      "sharpe_ci": [
        -0.7455685480092941,
        1.7039018179258483
      ],
      "cagr_ci": [
        -0.2727677628805836,
        0.7114346132449236
      ],
      "sharpe_diff_ci": [
        -0.6094203753504088,
        0.43116763741844943
      ],
      "p_strategy_better": 0.3275
    },
    "bench_btc_eth_50_50": {
      "sharpe_ci": [
        -0.7455685480092941,
        1.7039018179258483
      ],
      "cagr_ci": [
        -0.2727677628805836,
        0.7114346132449236
      ],
      "sharpe_diff_ci": [
        -0.4482604298143708,
        0.5999910506050018
      ],
      "p_strategy_better": 0.5785
    }
  },
  "concentration": {
    "yearly_block_returns": [
      1.0977291963237503,
      -0.11504920236741611,
      -0.26401756217476113
    ],
    "best_1pct_days_share_of_pnl": 3.4864841010152934,
    "pnl_without_best_10_days": -61734.07860196961,
    "hit_rate_days": 0.5102239532619279,
    "positive_years": 1,
    "n_years": 3
  },
  "primary_bench_concentration": {
    "yearly_block_returns": [
      1.6211301453863585,
      -0.11219705463670693,
      -0.29542423833302534
    ],
    "best_1pct_days_share_of_pnl": 2.8101895472392764,
    "pnl_without_best_10_days": -318016.47731230815,
    "hit_rate_days": 0.5059360730593607,
    "positive_years": 1,
    "n_years": 3
  }
}
```
</details>

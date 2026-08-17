# 表格完整提取（PDF 逐表核对）

- PDF 物理页数: 104
- 正式物理表总数: 51
- 主文表: 15（Table 1–15）
- Internet Appendix 表: 36（IA.1–IA.34，其中 IA.17A/17B、IA.20A/20B 分别为两个物理表）
- 旧版 pdfplumber 将 p42、p44、p45、p47、p49、p64、p69、p73、p86、p93、p96、p97 的图形误识别为 17 个表；本版不把这些图形伪表计入正式表。
- 记号: 表格原生空白单元格保留为空；不从相邻表或公式推算。

## 物理页 p27 · Table 1: Sample, Signal Families, and Walk-Forward Timing

### Panel A. Anomaly-family construction

| Family | Signals | Positive | Negative | Economic content |
| --- | ---: | ---: | ---: | --- |
| Valuation | 36 | 35 | 1 | Discount-rate and recovery states |
| Continuation | 27 | 26 | 1 | Trend persistence and underreaction |
| Correction | 4 | 1 | 3 | Post-dislocation reversal |
| Profitability/quality | 27 | 23 | 4 | Quality under uncertainty |
| Investment/issuance | 46 | 20 | 26 | Investment discipline and financing states |
| Safety/downside | 26 | 2 | 24 | Downside protection and stress states |
| Liquidity/limits | 21 | 4 | 17 | Trading frictions and arbitrage capacity |
| Expectations | 25 | 21 | 4 | Forecast updating and analyst information flow |

### Panel B. Prediction design

| Design element | Value | Interpretation |
| --- | --- | --- |
| Start of characteristic history | 1963 | First year used in model training |
| First prediction year | 1985 | After initial training and validation windows |
| Initial training window | 10 years | 1963–1972 for the first prediction year |
| Validation window | 12 years | Fixed length for model selection |
| Prediction months | 479 | January 1985 through November 2024 |
| Roll-forward frequency | Annual | Training expands; validation rolls forward |

## 物理页 p28 · Table 2: Macro-State Blocks and Allocation Rules

### Panel A. Macro-state blocks

| Block | Series | Max timing lag | Economic role |
| --- | ---: | --- | --- |
| Credit | 2 | 0 months | Financing conditions |
| Growth | 4 | 0 months | Real activity |
| Inflation | 3 | 0 months | Price pressure |
| Liquidity | 2 | 0 months | Aggregate liquidity |
| Rates | 4 | 0 months | Discount-rate conditions |
| Risk | 4 | 0 months | Market stress and volatility |
| Trend | 3 | 0 months | Market trend and drawdown state |
| Valuation | 1 | 0 months | Aggregate valuation |

### Panel B. Leading allocation rules

| Allocation rule | Version | Mean return (%) | NW t-statistic | Sharpe | Concentration |
| --- | --- | ---: | ---: | ---: | ---: |
| Mixture of experts | Nonnegative softmax | 2.13 | 9.21 | 1.51 | 0.77 |
| Bayesian dynamic | Nonnegative softmax | 2.05 | 8.98 | 1.44 | 0.71 |
| Validation ensemble | Nonnegative softmax | 2.08 | 9.09 | 1.43 | 0.75 |
| Ensemble | Nonnegative softmax | 1.95 | 8.05 | 1.36 | 0.75 |
| Macro ridge | Nonnegative softmax | 1.82 | 7.60 | 1.30 | 0.75 |
| Factor momentum | Nonnegative softmax | 1.82 | 7.62 | 1.17 | 0.68 |
| Regime probability | Nonnegative softmax | 1.90 | 7.01 | 1.16 | 0.89 |
| Trailing Sharpe | Nonnegative softmax | 1.70 | 7.51 | 1.16 | 0.73 |

## 物理页 p29 · Table 3: Anomaly-Family Allocation Performance

| Allocation rule | Mean return (%) | NW t-statistic | Sharpe | EW L-S (%) | EW t-statistic | VW L-S (%) | Alpha (%) | Alpha t-statistic | Max drawdown (%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixture of experts | 2.13 | 9.21 | 1.51 | 2.51 | 9.71 | 1.39 | 2.07 | 7.63 | -22.71 |
| Validation ensemble | 2.08 | 9.09 | 1.43 | 2.42 | 9.46 | 1.26 | 1.88 | 6.62 | -31.83 |
| Bayesian dynamic | 2.05 | 8.98 | 1.44 | 2.43 | 9.39 | 1.36 | 1.94 | 6.74 | -23.97 |
| Ensemble | 1.95 | 8.05 | 1.36 | 2.28 | 8.54 | 1.12 | 1.85 | 6.67 | -32.74 |
| Macro ridge | 1.82 | 7.60 | 1.30 | 2.14 | 7.89 | 1.07 | 1.73 | 6.39 | -26.29 |
| Factor momentum | 1.82 | 7.62 | 1.17 | 2.20 | 8.01 | 1.17 | 1.64 | 6.68 | -35.38 |
| Trailing Sharpe | 1.70 | 7.51 | 1.16 | 1.89 | 7.56 | 1.05 | 1.52 | 6.23 | -41.52 |
| Equal weight | 0.38 | 5.81 | 0.94 | 1.22 | 6.66 | 0.41 | 0.58 | 4.33 | -13.25 |

## 物理页 p30 · Table 4: Regime-Allocation Weights Across Anomaly Families

| Family | Mean weight (%) | Std. dev. (%) | P10 (%) | P90 (%) | Max (%) | Trend corr. | Valuation corr. |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Continuation | 60.74 | 40.45 | 0.15 | 99.88 | 100.00 |  |  |
| Correction | 0.60 | 4.71 | 0.00 | 0.32 | 77.32 |  |  |
| Expectations | 1.98 | 4.79 | 0.00 | 5.06 | 55.00 |  |  |
| Investment/issuance | 0.27 | 2.66 | 0.00 | 0.02 | 51.00 |  |  |
| Liquidity/limits | 3.64 | 15.81 | 0.00 | 1.69 | 99.98 |  |  |
| Profitability/quality | 14.40 | 24.34 | 0.01 | 54.84 | 99.77 |  |  |
| Safety/downside | 0.93 | 7.24 | 0.00 | 0.02 | 99.12 |  |  |
| Valuation | 17.44 | 30.22 | 0.00 | 74.74 | 99.94 |  |  |

注: PDF 中 `Trend corr.` 与 `Valuation corr.` 两列整列为空。

## 物理页 p31 · Table 5: Full 212-Characteristic Hierarchical Evidence

| Allocation rule | Mean IC | IC t-statistic | Incremental IC | Incremental t | EW L-S (%) | VW L-S (%) | Alpha (%) | Alpha t-statistic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixture of experts | 0.05 | 11.02 | 0.02 | 6.25 | 2.40 | 1.46 | 1.89 | 7.63 |
| Bayesian dynamic | 0.05 | 11.14 | 0.02 | 6.14 | 2.38 | 1.57 | 1.82 | 6.56 |
| Validation ensemble | 0.05 | 10.78 | 0.02 | 5.19 | 2.29 | 1.40 | 1.68 | 5.92 |
| Macro ridge | 0.05 | 9.93 | 0.02 | 5.02 | 2.24 | 1.44 | 1.73 | 8.36 |
| Ensemble | 0.05 | 10.25 | 0.02 | 4.68 | 2.21 | 1.30 | 1.61 | 6.46 |
| Equal weight | 0.05 | 7.30 | 0.01 | 3.36 | 1.60 | 1.14 | 0.84 | 4.31 |
| EWMA sleeve performance | 0.04 | 8.81 | 0.01 | 3.68 | 1.98 | 1.22 | 1.26 | 5.41 |
| Contextual bandit | 0.04 | 8.77 | 0.01 | 3.58 | 1.95 | 1.04 | 1.24 | 5.54 |

## 物理页 p32 · Table 6: Stock-Level Benchmark Evidence

| Stock-level model | Mean IC | IC t-statistic | Incremental IC vs pooled ridge | Incremental t | EW L-S (%) | VW L-S (%) | Alpha (%) | Alpha t-statistic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ridge plus macro residual | 0.07 | 15.63 | 0.00 | 0.21 | 3.80 | 2.10 | 3.32 | 14.22 |
| Pooled all-212 ridge | 0.07 | 15.93 | 0.00 | 0.00 | 3.88 | 2.09 | 3.44 | 14.48 |
| Decay-weighted ridge | 0.07 | 15.08 | -0.00 | -0.13 | 3.82 | 1.82 | 3.44 | 13.08 |
| Ridge-decay blend | 0.07 | 15.18 | -0.00 | -0.74 | 3.80 | 1.81 | 3.39 | 13.42 |
| Ridge plus validation residual | 0.07 | 15.64 | -0.00 | -0.67 | 3.77 | 2.01 | 3.31 | 13.62 |
| Ridge plus macro-analog residual | 0.07 | 15.59 | -0.00 | -0.90 | 3.76 | 1.90 | 3.27 | 13.16 |
| Ridge plus attention residual | 0.07 | 15.71 | -0.00 | -1.17 | 3.74 | 1.91 | 3.26 | 13.55 |
| Ridge plus ensemble residual | 0.07 | 15.69 | -0.00 | -0.94 | 3.82 | 2.09 | 3.34 | 13.76 |
| Family-balanced ridge | 0.07 | 16.32 | -0.00 | -2.32 | 3.84 | 2.06 | 3.41 | 14.40 |
| SGD Huber | 0.07 | 10.48 | -0.01 | -1.77 | 3.24 | 2.24 | 2.53 | 12.62 |

## 物理页 p33 · Table 7: Controlled Cross-Sectional Prediction and Factor-Alpha Evidence

| Object | Specification | Mean IC | Controlled FMB t | EW L-S (%) | VW L-S (%) | Alpha (%) | Alpha t-statistic |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stock-level or hierarchical benchmark | Ridge plus macro residual | 0.07 | 2.42 | 3.80 | 2.10 | 3.32 | 14.22 |
| Stock-level or hierarchical benchmark | Pooled all-212 ridge | 0.07 | 12.83 | 3.88 | 2.09 | 3.44 | 14.48 |
| Stock-level or hierarchical benchmark | Hierarchical validation ensemble | 0.05 | 3.08 | 2.29 | 1.40 | 1.68 | 5.92 |
| Stock-level or hierarchical benchmark | Hierarchical macro ridge | 0.05 | 3.29 | 2.24 | 1.44 | 1.73 | 8.36 |
| Stock-level or hierarchical benchmark | Static 212 equal weight | 0.03 | 1.59 | 1.58 | 0.46 | 0.92 | 6.52 |
| Family allocation | Mixture of experts | 0.00 | 10.59 | 2.51 | 1.39 | 2.07 | 7.63 |
| Family allocation | Bayesian dynamic | 0.00 | 10.44 | 2.43 | 1.36 | 1.94 | 6.74 |
| Family allocation | Validation ensemble | 0.00 | 10.74 | 2.42 | 1.26 | 1.88 | 6.62 |
| Family allocation | Macro ridge | 0.00 | 8.17 | 2.14 | 1.07 | 1.73 | 6.39 |

## 物理页 p34 · Table 8: Regime-Family Payoff Map

| Macro block | Family | High-state return (%) | Low-state return (%) | High minus low (%) | Return t-statistic | IC spread | IC t-statistic |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Trend | Liquidity/limits | -1.79 | 1.41 | -3.20 | -6.77 | -0.06 | -7.14 |
| Valuation | Expectations | -0.38 | 1.94 | -2.32 | -5.12 | -0.04 | -5.28 |
| Valuation | Continuation | -0.03 | 3.07 | -3.09 | -4.76 | -0.04 | -4.82 |
| Valuation | Investment/issuance | -0.15 | -1.29 | +1.14 | 3.97 | 0.02 | 4.26 |
| Credit | Correction | -1.54 | 0.73 | -2.27 | -3.94 | -0.03 | -3.65 |
| Valuation | Profitability/quality | 0.30 | 2.33 | -2.03 | -3.83 | -0.03 | -4.25 |
| Trend | Safety/downside | -0.31 | -2.69 | +2.39 | 3.50 | 0.04 | 4.24 |
| Valuation | Valuation | 0.41 | 1.93 | -1.52 | -3.36 | -0.04 | -5.28 |
| Inflation | Profitability/quality | 2.85 | 1.03 | +1.82 | 3.15 | 0.02 | 2.58 |
| Rates | Correction | 0.63 | -1.06 | +1.69 | 2.94 | 0.03 | 3.55 |
| Inflation | Valuation | 1.84 | 0.50 | +1.34 | 2.89 | 0.02 | 2.78 |
| Trend | Valuation | 1.93 | 0.52 | +1.41 | 2.87 | 0.02 | 2.51 |
| Rates | Liquidity/limits | 0.53 | -0.88 | +1.42 | 2.87 | 0.03 | 3.43 |
| Risk | Correction | -1.51 | 0.19 | -1.70 | -2.78 | -0.02 | -2.11 |

## 物理页 p35 · Table 9: Liquidity/Limits × Trend Mechanism Across Universes

| Construction | Low minus high (%) | t-statistic | High-state return (%) | Low-state return (%) | High months | Low months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All firms | 3.13 | 7.41 | -2.23 | 0.89 | 248 | 248 |
| Outside microcaps | 1.71 | 4.58 | -1.45 | 0.25 | 248 | 248 |
| Liquid-proxy universe | 1.71 | 4.58 | -1.45 | 0.25 | 248 | 248 |
| Industry neutral | 2.76 | 7.06 | -1.99 | 0.77 | 248 | 248 |
| Beta neutral | 3.00 | 7.24 | -2.12 | 0.88 | 248 | 248 |
| Large stocks | -0.18 | -0.53 | -0.25 | -0.43 | 248 | 248 |

## 物理页 p36 · Table 10: Capacity Frontier of the Liquidity/Limits Mechanism

| Capacity region | EW return low-high | EW return t | VW return low-high | VW return t | IC low-high | IC t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All firms | 3.13 | 7.41 | 2.74 | 6.16 | 0.07 | 8.32 |
| Micro bottom 20 | 1.03 | 2.11 | 0.99 | 1.98 | 0.01 | 1.78 |
| Outside microcaps | 1.71 | 4.58 | 1.46 | 3.73 | 0.05 | 6.69 |
| Middle 60 | 1.42 | 3.67 | 1.14 | 3.02 | 0.04 | 4.90 |
| Upper half | 0.50 | 1.58 | 0.60 | 1.72 | 0.02 | 3.38 |
| Upper third | 0.17 | 0.54 | -0.01 | -0.03 | 0.01 | 1.77 |
| Large top 20 | -0.18 | -0.53 | -0.52 | -1.29 | -0.00 | -0.11 |
| Mega top 10 | -0.58 | -1.57 | -0.93 | -2.09 | -0.02 | -1.54 |

## 物理页 p37 · Table 11: State-Specificity Evidence

### Panel A. Macro-state content comparisons

| State comparison | Allocation rule | Estimate (%) | t-statistic | Months |
| --- | --- | ---: | ---: | ---: |
| Macro shuffle minus full macro | Macro ridge | -0.29 | -1.03 | 479 |
| Macro shuffle minus full macro | Ensemble | -0.36 | -1.53 | 479 |
| Extra lag minus equal weight | Macro ridge | +1.45 | 7.08 | 479 |
| Extra lag minus equal weight | Ensemble | +1.58 | 7.61 | 479 |
| Single-risk-state benchmark minus full macro | Macro ridge | +0.15 | 0.75 | 479 |
| Single-risk-state benchmark minus full macro | Ensemble | +0.01 | 0.04 | 479 |
| Calendar dummy minus full macro | Macro ridge | +0.31 | 1.18 | 479 |
| Calendar dummy minus full macro | Ensemble | +0.11 | 0.44 | 479 |
| Random macro minus full macro | Macro ridge | -0.17 | -0.72 | 479 |
| Random macro minus full macro | Ensemble | -0.21 | -0.95 | 479 |

### Panel B. Macro-block drop comparisons

| Block comparison | Estimate (%) | t-statistic | Months |
| --- | ---: | ---: | ---: |
| Drop Inflation block minus full macro states | +0.04 | 0.33 | 479 |
| Drop Growth block minus full macro states | +0.04 | 0.52 | 479 |
| Drop Rates block minus full macro states | +0.05 | 1.19 | 479 |
| Drop Credit block minus full macro states | -0.03 | -0.57 | 479 |
| Drop Liquidity block minus full macro states | +0.03 | 0.87 | 479 |
| Drop Risk block minus full macro states | -0.04 | -0.27 | 479 |
| Drop Valuation block minus full macro states | +0.02 | 1.40 | 479 |
| Drop Trend block minus full macro states | -0.08 | -1.23 | 479 |

### Panel C. Mechanism relabeling comparisons

| Macro-family pair | State comparison | Actual t | Comparison mean abs. t | Comparison max abs. t | Estimate (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| Liquidity/limits × Trend | Actual macro-family pair | -7.41 | 0.00 | 0.00 | -3.13 |
| Liquidity/limits × Trend | Circularly shifted macro state | -7.41 | 0.56 | 1.07 | -3.13 |
| Liquidity/limits × Trend | Calendar-month state | -7.41 | 1.10 | 1.10 | +0.43 |
| Liquidity/limits × Trend | Family-label relabeling | -7.41 | 2.00 | 4.61 | -3.13 |
| Continuation × Valuation | Actual macro-family pair | -2.39 | 0.00 | 0.00 | -1.18 |
| Continuation × Valuation | Circularly shifted macro state | -2.39 | 1.92 | 3.27 | -1.18 |
| Continuation × Valuation | Calendar-month state | -2.39 | 0.53 | 0.53 | +0.25 |
| Continuation × Valuation | Family-label relabeling | -2.39 | 2.28 | 3.38 | -1.18 |

## 物理页 p38 · Table 12: Model-Class Benchmark Evidence

| Model class | Benchmark role | Mean IC | IC t-statistic | Incremental IC vs pooled ridge | Incremental t | FMB t | Alpha t |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ridge plus macro residual | Macro residual after full-panel ridge | 0.07 | 15.63 | 0.00 | 0.21 | 2.42 | 14.22 |
| Pooled all-212 ridge | Full-panel stock-level benchmark | 0.07 | 15.93 | 0.00 | 0.00 | 12.83 | 14.48 |
| Decay-weighted ridge | Decay-aware linear benchmark | 0.07 | 15.08 | -0.00 | -0.13 | 2.56 | 13.08 |
| Ridge-decay blend | Decay-aware linear benchmark | 0.07 | 15.18 | -0.00 | -0.74 | 0.03 | 13.42 |
| Ridge plus validation residual | Macro residual after full-panel ridge | 0.07 | 15.64 | -0.00 | -0.67 | 2.21 | 13.62 |
| Ridge plus macro-analog residual | Macro residual after full-panel ridge | 0.07 | 15.59 | -0.00 | -0.90 | 2.76 | 13.16 |
| Ridge plus attention residual | Macro residual after full-panel ridge | 0.07 | 15.71 | -0.00 | -1.17 | 3.67 | 13.55 |
| Ridge plus ensemble residual | Macro residual after full-panel ridge | 0.07 | 15.69 | -0.00 | -0.94 | 2.42 | 13.76 |
| Family-balanced ridge | Family-balanced linear benchmark | 0.07 | 16.32 | -0.00 | -2.32 | -1.62 | 14.40 |
| SGD Huber | Regularized stock-level benchmark | 0.07 | 10.48 | -0.01 | -1.77 | 0.72 | 12.62 |
| SGD elastic net | Regularized stock-level benchmark | 0.06 | 13.01 | -0.01 | -4.25 | 1.32 | 11.41 |
| Neural network benchmark | Neural stock-level benchmark | 0.05 | 9.84 | -0.02 | -5.15 | 2.71 | 10.41 |

## 物理页 p39 · Table 13: Holdout and Mechanism Persistence Evidence

| Macro-family channel | Period | Pred. ret. (%) | t-statistic | High months | Low months |
| --- | --- | ---: | ---: | ---: | ---: |
| Continuation × Valuation | Formation period, 1985–2004 | 0.05 | 0.05 | 80 | 80 |
| Continuation × Valuation | Confirmation period, 2005 onward | 0.00 | 0.00 | 223 | 2 |
| Liquidity/limits × Trend | Formation period, 1985–2004 | 4.26 | 5.69 | 80 | 80 |
| Liquidity/limits × Trend | Confirmation period, 2005 onward | 1.86 | 3.11 | 62 | 107 |

## 物理页 p40 · Table 14: Economic Scope of the Main Finding

| Evidence block | Main tables | Economic interpretation |
| --- | --- | --- |
| Family allocation | Tables 3–4 | Macro-regime memory assigns capital across broad anomaly families and generates large out-of-sample allocation returns. |
| Full characteristic panel | Table 5 | The family-allocation structure remains valuable when applied to the complete 212-signal panel. |
| Stock-level benchmark | Tables 6–7 | The pooled all-212 ridge is a demanding stock-level benchmark that sharpens the interpretation of the family-allocation result. |
| Lead mechanism | Tables 8–9 | Liquidity/limits × trend is the strongest family-state channel and has direct limits-to-arbitrage content. |
| Capacity shape | Table 10 | The mechanism is strongest outside the deepest-capacity names, matching the economic region where limits to arbitrage should bind most. |
| State specificity | Tables 11–13 | The evidence is concentrated in economically meaningful state-family links and retains the predicted sign in the holdout period. |

## 物理页 p41 · Table 15: Family-Group Ablations and the Economic Content of Concentration

| Family set | Weight kept | Mean | NW t | All-family mean | Full-minus-set | Inc. t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Continuation only | 60.74% | 1.96% | 7.06 | 2.13% | 0.17% | 0.75 |
| Valuation only | 17.44% | 1.17% | 4.96 | 2.13% | 0.96% | 3.27 |
| Continuation + Valuation | 78.18% | 2.08% | 9.24 | 2.13% | 0.05% | 0.66 |
| Continuation + Valuation + Profitability | 92.58% | 2.12% | 9.11 | 2.13% | 0.01% | 0.11 |
| All eight families | 100.00% | 2.13% | 9.21 | 2.13% | 0.00% | 0.00 |

## 物理页 p52 · Table IA.1. Annual Walk-Forward Windows

| Prediction year | Months | Train start | Train end | Validation start | Validation end |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1985 | 12 | 1963 | 1972 | 1973 | 1984 |
| 1986 | 12 | 1963 | 1973 | 1974 | 1985 |
| 1987 | 12 | 1963 | 1974 | 1975 | 1986 |
| 1988 | 12 | 1963 | 1975 | 1976 | 1987 |
| 1989 | 12 | 1963 | 1976 | 1977 | 1988 |
| 1990 | 12 | 1963 | 1977 | 1978 | 1989 |
| 1991 | 12 | 1963 | 1978 | 1979 | 1990 |
| 1992 | 12 | 1963 | 1979 | 1980 | 1991 |
| 1993 | 12 | 1963 | 1980 | 1981 | 1992 |
| 1994 | 12 | 1963 | 1981 | 1982 | 1993 |
| 1995 | 12 | 1963 | 1982 | 1983 | 1994 |
| 1996 | 12 | 1963 | 1983 | 1984 | 1995 |
| 1997 | 12 | 1963 | 1984 | 1985 | 1996 |
| 1998 | 12 | 1963 | 1985 | 1986 | 1997 |
| 1999 | 12 | 1963 | 1986 | 1987 | 1998 |
| 2000 | 12 | 1963 | 1987 | 1988 | 1999 |
| 2001 | 12 | 1963 | 1988 | 1989 | 2000 |
| 2002 | 12 | 1963 | 1989 | 1990 | 2001 |
| 2003 | 12 | 1963 | 1990 | 1991 | 2002 |
| 2004 | 12 | 1963 | 1991 | 1992 | 2003 |
| 2005 | 12 | 1963 | 1992 | 1993 | 2004 |
| 2006 | 12 | 1963 | 1993 | 1994 | 2005 |
| 2007 | 12 | 1963 | 1994 | 1995 | 2006 |
| 2008 | 12 | 1963 | 1995 | 1996 | 2007 |
| 2009 | 12 | 1963 | 1996 | 1997 | 2008 |
| 2010 | 12 | 1963 | 1997 | 1998 | 2009 |
| 2011 | 12 | 1963 | 1998 | 1999 | 2010 |
| 2012 | 12 | 1963 | 1999 | 2000 | 2011 |
| 2013 | 12 | 1963 | 2000 | 2001 | 2012 |
| 2014 | 12 | 1963 | 2001 | 2002 | 2013 |
| 2015 | 12 | 1963 | 2002 | 2003 | 2014 |
| 2016 | 12 | 1963 | 2003 | 2004 | 2015 |
| 2017 | 12 | 1963 | 2004 | 2005 | 2016 |
| 2018 | 12 | 1963 | 2005 | 2006 | 2017 |
| 2019 | 12 | 1963 | 2006 | 2007 | 2018 |
| 2020 | 12 | 1963 | 2007 | 2008 | 2019 |
| 2021 | 12 | 1963 | 2008 | 2009 | 2020 |
| 2022 | 12 | 1963 | 2009 | 2010 | 2021 |
| 2023 | 12 | 1963 | 2010 | 2011 | 2022 |
| 2024 | 11 | 1963 | 2011 | 2012 | 2023 |

## 物理页 p53 · Table IA.2. Macro-State Blocks

| Series | Identifier | Block | Frequency | Timing lag |
| --- | --- | --- | --- | --- |
| Cpi | CPIAUCSL | Inflation | Monthly | 0 months |
| Pce | PCEPI | Inflation | Monthly | 0 months |
| Core cpi | CPILFESL | Inflation | Monthly | 0 months |
| Industrial output | INDPRO | Growth | Monthly | 0 months |
| Unemployment | UNRATE | Growth | Monthly | 0 months |
| Payrolls | PAYEMS | Growth | Monthly | 0 months |
| Recession | USREC | Growth | Monthly | 0 months |
| Fed funds | FEDFUNDS | Rates | Monthly | 0 months |
| Tbill 3m | TB3MS | Rates | Monthly | 0 months |
| Treasury 10y | GS10 | Rates | Monthly | 0 months |
| Treasury 2y | GS2 | Rates | Monthly | 0 months |
| Baa 10y spread | BAA10Y | Credit | Monthly | 0 months |
| Corp oas | BAMLC0A0CM | Credit | Daily | 0 months |
| Financial stress | STLFSI4 | Liquidity | Weekly | 0 months |
| Vix | VIXCLS | Risk | Daily | 0 months |
| Sp500 | SP500 | Trend | Daily | 0 months |
| Market ret | market ret | Trend | Monthly | 0 months |
| Market vol proxy | market vol proxy | Risk | Monthly | 0 months |
| Cs dispersion | cs dispersion | Risk | Monthly | 0 months |
| Aggregate valuation | aggregate valuation | Valuation | Monthly | 0 months |
| Aggregate liquidity | aggregate liquidity | Liquidity | Monthly | 0 months |
| Market trend 12m | market trend 12m | Trend | Monthly | 0 months |
| Market drawdown 12m | market drawdown 12m | Risk | Monthly | 0 months |

## 物理页 p54 · Table IA.3. Signal Family Mapping

| Family | Signals | Positive orientation | Negative orientation | Share of panel (%) |
| --- | ---: | ---: | ---: | ---: |
| Valuation | 36 | 35 | 1 | 17.0 |
| Continuation | 27 | 26 | 1 | 12.7 |
| Correction | 4 | 1 | 3 | 1.9 |
| Profitability/quality | 27 | 23 | 4 | 12.7 |
| Investment/issuance | 46 | 20 | 26 | 21.7 |
| Safety/downside | 26 | 2 | 24 | 12.3 |
| Liquidity/limits | 21 | 4 | 17 | 9.9 |
| Expectations | 25 | 21 | 4 | 11.8 |

## 物理页 p55 · Table IA.4. Real-Time Macro Information Timing

| Macro series | Identifier | Vintage months | Nonmissing values | Real-time values | Conservative values | First vintage | Last vintage | Timing violations |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| Baa 10y spread | BAA10Y | 743 | 466 | 0 | 743 | 1963-01-31 | 2024-11-30 | 0 |
| Corp oas | BAMLC0A0CM | 743 | 18 | 0 | 743 | 1963-01-31 | 2024-11-30 | 0 |
| Cpi | CPIAUCSL | 743 | 743 | 629 | 114 | 1963-01-31 | 2024-11-30 | 0 |
| Core cpi | CPILFESL | 743 | 743 | 336 | 407 | 1963-01-31 | 2024-11-30 | 0 |
| Fed funds | FEDFUNDS | 743 | 743 | 336 | 407 | 1963-01-31 | 2024-11-30 | 0 |
| Treasury 10y | GS10 | 743 | 743 | 336 | 407 | 1963-01-31 | 2024-11-30 | 0 |
| Treasury 2y | GS2 | 743 | 581 | 336 | 407 | 1963-01-31 | 2024-11-30 | 0 |
| Industrial output | INDPRO | 743 | 743 | 743 | 0 | 1963-01-31 | 2024-11-30 | 0 |
| Payrolls | PAYEMS | 743 | 743 | 743 | 0 | 1963-01-31 | 2024-11-30 | 0 |
| Pce | PCEPI | 743 | 743 | 292 | 451 | 1963-01-31 | 2024-11-30 | 0 |
| Sp500 | SP500 | 743 | 102 | 0 | 743 | 1963-01-31 | 2024-11-30 | 0 |
| Financial stress | STLFSI4 | 743 | 372 | 0 | 743 | 1963-01-31 | 2024-11-30 | 0 |
| Tbill 3m | TB3MS | 743 | 743 | 336 | 407 | 1963-01-31 | 2024-11-30 | 0 |
| Unemployment | UNRATE | 743 | 743 | 743 | 0 | 1963-01-31 | 2024-11-30 | 0 |
| Recession | USREC | 743 | 743 | 123 | 620 | 1963-01-31 | 2024-11-30 | 0 |
| Vix | VIXCLS | 743 | 419 | 0 | 743 | 1963-01-31 | 2024-11-30 | 0 |

## 物理页 p56 · Table IA.5. Macro-State Correlations

| Row block | Credit | Growth | Inflation | Liquidity | Rates | Risk | Trend | Valuation |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Credit | 0.56 | 0.12 | 0.07 | 0.21 | 0.16 | 0.18 | 0.12 | 0.08 |
| Growth | 0.12 | 0.26 | 0.12 | 0.09 | 0.17 | 0.09 | 0.10 | 0.10 |
| Inflation | 0.07 | 0.12 | 0.35 | 0.12 | 0.20 | 0.06 | 0.03 | 0.20 |
| Liquidity | 0.21 | 0.09 | 0.12 | 0.33 | 0.13 | 0.15 | 0.12 | 0.34 |
| Rates | 0.16 | 0.17 | 0.20 | 0.13 | 0.44 | 0.08 | 0.08 | 0.18 |
| Risk | 0.18 | 0.09 | 0.06 | 0.15 | 0.08 | 0.32 | 0.26 | 0.07 |
| Trend | 0.12 | 0.10 | 0.03 | 0.12 | 0.08 | 0.26 | 0.48 | 0.07 |
| Valuation | 0.08 | 0.10 | 0.20 | 0.34 | 0.18 | 0.07 | 0.07 | 0.64 |

## 物理页 p59 · Table IA.6. Baseline Family Predictability

| Allocation rule | Future return slope | Return t | Future IC slope | IC t | Family-months |
| --- | ---: | ---: | ---: | ---: | ---: |
| Attention memory | 0.01 | 2.88 | 0.01 | 3.06 | 3832 |
| Bayesian dynamic | 0.01 | 4.17 | 0.02 | 3.94 | 3832 |
| Contextual bandit | 0.01 | 2.86 | 0.01 | 2.99 | 3832 |
| Ensemble | 0.01 | 3.73 | 0.02 | 3.13 | 3832 |
| Equal weight | 0.00 | 0.00 | 0.00 | 0.00 | 3832 |
| EWMA sleeve performance | 0.00 | 1.27 | 0.01 | 0.86 | 3832 |
| Factor momentum | 0.01 | 3.10 | 0.01 | 2.34 | 3832 |
| Macro analog | 0.01 | 2.86 | 0.01 | 2.99 | 3832 |
| Macro ridge | 0.01 | 4.06 | 0.02 | 3.84 | 3832 |
| Mixture of experts | 0.01 | 4.24 | 0.02 | 4.23 | 3832 |
| Regime probability | -0.00 | -0.36 | -0.01 | -0.72 | 3832 |
| Trailing ic | 0.00 | 0.96 | 0.01 | 0.94 | 3832 |

## 物理页 p60 · Table IA.7. Family Sleeve Return Evidence

| Allocation rule | EW return (%) | EW t | VW return (%) | VW t | Alpha (%) | Alpha t | Turnover |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixture of experts | 2.51 | 9.71 | 1.39 | 5.36 | 2.07 | 7.63 | 0.61 |
| Bayesian dynamic | 2.43 | 9.39 | 1.36 | 5.32 | 1.94 | 6.74 | 0.57 |
| Validation ensemble | 2.42 | 9.46 | 1.26 | 4.82 | 1.88 | 6.62 | 0.61 |
| Ensemble | 2.28 | 8.54 | 1.12 | 4.06 | 1.85 | 6.67 | 0.62 |
| Macro ridge | 2.14 | 7.89 | 1.07 | 3.85 | 1.73 | 6.39 | 0.66 |
| EWMA sleeve performance | 2.16 | 7.98 | 1.16 | 4.10 | 1.68 | 6.83 | 0.41 |
| Factor momentum | 2.20 | 8.01 | 1.17 | 4.14 | 1.64 | 6.68 | 0.43 |
| Regime probability | 2.05 | 7.32 | 1.00 | 3.43 | 1.47 | 7.73 | 0.53 |
| Trailing ic | 2.11 | 7.27 | 1.03 | 3.45 | 1.56 | 7.41 | 0.42 |
| Contextual bandit | 1.93 | 7.51 | 0.87 | 3.30 | 1.40 | 5.88 | 0.65 |
| Macro analog | 1.93 | 7.51 | 0.87 | 3.30 | 1.40 | 5.88 | 0.65 |
| Trailing Sharpe | 1.89 | 7.56 | 1.05 | 4.10 | 1.52 | 6.23 | 0.37 |

## 物理页 p61 · Table IA.8. Allocation Rule Variants

| Allocation rule | Version | Mean return (%) | NW t | Sharpe | Drawdown (%) | Concentration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Mixture of experts | Nonnegative softmax | 2.13 | 9.21 | 1.51 | -22.71 | 0.77 |
| Bayesian dynamic | Nonnegative softmax | 2.05 | 8.98 | 1.44 | -23.97 | 0.71 |
| Validation ensemble | Nonnegative softmax | 2.08 | 9.09 | 1.43 | -31.83 | 0.75 |
| Ensemble | Nonnegative softmax | 1.95 | 8.05 | 1.36 | -32.74 | 0.75 |
| Macro ridge | Nonnegative softmax | 1.82 | 7.60 | 1.30 | -26.29 | 0.75 |
| Factor momentum | Nonnegative softmax | 1.82 | 7.62 | 1.17 | -35.38 | 0.68 |
| Regime probability | Nonnegative softmax | 1.90 | 7.01 | 1.16 | -48.30 | 0.89 |
| Trailing Sharpe | Nonnegative softmax | 1.70 | 7.51 | 1.16 | -41.52 | 0.73 |
| Macro analog | Nonnegative softmax | 1.62 | 6.91 | 1.14 | -32.24 | 0.74 |
| Contextual bandit | Nonnegative softmax | 1.62 | 6.91 | 1.14 | -32.24 | 0.74 |
| Trailing ic | Nonnegative softmax | 1.69 | 6.98 | 1.12 | -40.00 | 0.62 |
| Trailing return | Nonnegative softmax | 1.74 | 7.19 | 1.12 | -41.55 | 0.73 |
| EWMA sleeve performance | Nonnegative softmax | 1.75 | 7.16 | 1.11 | -41.35 | 0.67 |
| Attention memory | Nonnegative softmax | 1.48 | 6.56 | 1.03 | -30.56 | 0.76 |
| Equal weight | Nonnegative softmax | 0.38 | 5.81 | 0.94 | -13.25 | 0.12 |
| Mixture of experts | Long short l1 | 1.44 | 10.23 | 1.57 | -18.87 | 0.18 |
| Regime probability | Long short l1 | 1.19 | 8.85 | 1.57 | -17.00 | 0.15 |
| Validation ensemble | Long short l1 | 1.41 | 10.00 | 1.53 | -17.60 | 0.18 |

## 物理页 p62 · Table IA.9. Family Weight Distribution Over Time

| Family | Mean (%) | Std. dev. (%) | Min (%) | P25 (%) | Median (%) | P75 (%) | Max (%) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Continuation | 60.74 | 40.45 | 0.00 | 12.80 | 80.08 | 98.33 | 100.00 |
| Correction | 0.60 | 4.71 | 0.00 | 0.00 | 0.00 | 0.03 | 77.32 |
| Expectations | 1.98 | 4.79 | 0.00 | 0.05 | 0.39 | 1.82 | 55.00 |
| Investment/issuance | 0.27 | 2.66 | 0.00 | 0.00 | 0.00 | 0.00 | 51.00 |
| Liquidity/limits | 3.64 | 15.81 | 0.00 | 0.00 | 0.00 | 0.07 | 99.98 |
| Profitability/quality | 14.40 | 24.34 | 0.00 | 0.10 | 1.81 | 17.48 | 99.77 |
| Safety/downside | 0.93 | 7.24 | 0.00 | 0.00 | 0.00 | 0.00 | 99.12 |
| Valuation | 17.44 | 30.22 | 0.00 | 0.02 | 0.87 | 19.45 | 99.94 |

## 物理页 p63 · Table IA.10. Family Weight Distribution by Macro State

PDF 原表只有一列表头 `Family`，无任何数据行、无其余列标题，表体为空。

| Family |
| --- |

## 物理页 p65 · Table IA.11. Signal Composition Within Anomaly Families

| Family | Signals | Average IC | Average IC t | Max signal t |
| --- | ---: | ---: | ---: | ---: |
| Continuation | 27 | 0.01 | 5.98 | 13.63 |
| Correction | 4 | -0.00 | 0.08 | 7.53 |
| Expectations | 25 | 0.00 | 3.67 | 13.04 |
| Investment/issuance | 46 | -0.00 | -1.17 | 7.76 |
| Liquidity/limits | 21 | -0.00 | -1.76 | 5.80 |
| Profitability/quality | 27 | 0.01 | 3.51 | 11.92 |
| Safety/downside | 26 | -0.01 | -2.97 | 3.46 |
| Valuation | 36 | 0.01 | 4.26 | 12.58 |

## 物理页 p67 · Table IA.12. Full 212-Signal Hierarchical Layer Detail

| Allocation rule | Mean IC | IC t | Incremental IC | Incremental t | EW L-S (%) | Alpha (%) | Alpha t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixture of experts | 0.05 | 11.02 | 0.02 | 6.25 | 2.40 | 1.89 | 7.63 |
| Bayesian dynamic | 0.05 | 11.14 | 0.02 | 6.14 | 2.38 | 1.82 | 6.56 |
| Validation ensemble | 0.05 | 10.78 | 0.02 | 5.19 | 2.29 | 1.68 | 5.92 |
| Macro ridge | 0.05 | 9.93 | 0.02 | 5.02 | 2.24 | 1.73 | 8.36 |
| Ensemble | 0.05 | 10.25 | 0.02 | 4.68 | 2.21 | 1.61 | 6.46 |
| Equal weight | 0.05 | 7.30 | 0.01 | 3.36 | 1.60 | 0.84 | 4.31 |
| EWMA sleeve performance | 0.04 | 8.81 | 0.01 | 3.68 | 1.98 | 1.26 | 5.41 |
| Contextual bandit | 0.04 | 8.77 | 0.01 | 3.58 | 1.95 | 1.24 | 5.54 |
| Macro analog | 0.04 | 8.77 | 0.01 | 3.58 | 1.95 | 1.24 | 5.54 |
| Factor momentum | 0.04 | 8.35 | 0.01 | 3.42 | 2.06 | 1.34 | 5.35 |
| Trailing return | 0.04 | 8.57 | 0.01 | 3.33 | 1.86 | 1.22 | 5.28 |
| Trailing ic | 0.04 | 7.93 | 0.01 | 3.03 | 1.84 | 1.12 | 4.98 |
| Trailing Sharpe | 0.04 | 9.19 | 0.01 | 3.44 | 1.84 | 1.27 | 4.86 |
| Attention memory | 0.04 | 8.31 | 0.01 | 2.92 | 1.80 | 1.12 | 5.27 |
| Regime probability | 0.04 | 7.89 | 0.01 | 2.46 | 1.77 | 1.05 | 5.67 |

## 物理页 p68 · Table IA.13. Hierarchical Decile Portfolio Evidence

| Allocation rule | EW L-S (%) | EW t | VW L-S (%) | VW t | Alpha (%) | Alpha t | Months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixture of experts | 2.40 | 8.84 | 1.46 | 4.46 | 1.89 | 7.63 | 479 |
| Bayesian dynamic | 2.38 | 8.94 | 1.57 | 4.98 | 1.82 | 6.56 | 479 |
| Validation ensemble | 2.29 | 8.83 | 1.40 | 4.39 | 1.68 | 5.92 | 479 |
| Macro ridge | 2.24 | 7.86 | 1.44 | 4.15 | 1.73 | 8.36 | 479 |
| Ensemble | 2.21 | 8.32 | 1.30 | 3.96 | 1.61 | 6.46 | 479 |
| Equal weight | 1.60 | 4.28 | 1.14 | 2.68 | 0.84 | 4.31 | 479 |
| EWMA sleeve performance | 1.98 | 6.49 | 1.22 | 3.35 | 1.26 | 5.41 | 479 |
| Contextual bandit | 1.95 | 6.67 | 1.04 | 3.39 | 1.24 | 5.54 | 479 |
| Macro analog | 1.95 | 6.67 | 1.04 | 3.39 | 1.24 | 5.54 | 479 |
| Factor momentum | 2.06 | 6.65 | 1.24 | 3.32 | 1.34 | 5.35 | 479 |
| Trailing return | 1.86 | 6.01 | 1.07 | 2.88 | 1.22 | 5.28 | 479 |
| Trailing ic | 1.84 | 5.32 | 1.03 | 2.65 | 1.12 | 4.98 | 479 |
| Trailing Sharpe | 1.84 | 6.46 | 0.90 | 2.72 | 1.27 | 4.86 | 479 |
| Attention memory | 1.80 | 6.31 | 0.94 | 2.98 | 1.12 | 5.27 | 479 |
| Regime probability | 1.77 | 5.44 | 0.97 | 2.39 | 1.05 | 5.67 | 479 |

## 物理页 p70 · Table IA.14. Stock-Level IC and Fama-MacBeth Detail

| Allocation rule | Mean IC | IC t | Incremental IC | Incremental t | FMB slope | FMB t | Months |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Mixture of experts | 0.05 | 11.46 | 0.02 | 6.10 | 0.03 | 8.56 | 479 |
| Validation ensemble | 0.05 | 11.52 | 0.02 | 6.00 | 0.03 | 9.48 | 479 |
| Bayesian dynamic | 0.05 | 11.16 | 0.02 | 5.86 | 0.03 | 8.61 | 479 |
| Trailing ic | 0.04 | 9.94 | 0.02 | 6.07 | 0.03 | 7.42 | 479 |
| EWMA sleeve performance | 0.04 | 9.78 | 0.02 | 5.31 | 0.03 | 7.92 | 479 |
| Ensemble | 0.04 | 9.99 | 0.02 | 5.11 | 0.03 | 7.68 | 479 |
| Factor momentum | 0.04 | 9.64 | 0.02 | 4.97 | 0.03 | 7.23 | 479 |
| Trailing return | 0.04 | 10.14 | 0.02 | 5.30 | 0.02 | 8.13 | 479 |
| Regime probability | 0.04 | 9.41 | 0.02 | 5.36 | 0.02 | 6.98 | 479 |
| Macro ridge | 0.04 | 8.92 | 0.02 | 3.79 | 0.03 | 7.48 | 479 |
| Trailing Sharpe | 0.04 | 10.56 | 0.02 | 4.42 | 0.02 | 7.48 | 479 |
| Contextual bandit | 0.04 | 8.62 | 0.02 | 4.07 | 0.02 | 7.98 | 479 |
| Macro analog | 0.04 | 8.62 | 0.02 | 4.07 | 0.02 | 7.98 | 479 |
| Attention memory | 0.03 | 7.81 | 0.01 | 2.73 | 0.02 | 6.43 | 479 |
| Equal weight | 0.03 | 8.68 | 0.01 | 3.62 | 0.06 | 6.39 | 479 |

## 物理页 p71 · Table IA.15. Stock-Level Horse-Race Detail

| Model | Mean IC | IC t | Incremental IC vs pooled ridge | Incremental t | EW L-S (%) | Alpha (%) | Alpha t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ridge plus macro residual | 0.07 | 15.63 | 0.00 | 0.21 | 3.80 | 3.32 | 14.22 |
| Pooled all-212 ridge | 0.07 | 15.93 | 0.00 | 0.00 | 3.88 | 3.44 | 14.48 |
| Decay-weighted ridge | 0.07 | 15.08 | -0.00 | -0.13 | 3.82 | 3.44 | 13.08 |
| Ridge-decay blend | 0.07 | 15.18 | -0.00 | -0.74 | 3.80 | 3.39 | 13.42 |
| Ridge plus validation residual | 0.07 | 15.64 | -0.00 | -0.67 | 3.77 | 3.31 | 13.62 |
| Ridge plus macro-analog residual | 0.07 | 15.59 | -0.00 | -0.90 | 3.76 | 3.27 | 13.16 |
| Ridge plus attention residual | 0.07 | 15.71 | -0.00 | -1.17 | 3.74 | 3.26 | 13.55 |
| Ridge plus ensemble residual | 0.07 | 15.69 | -0.00 | -0.94 | 3.82 | 3.34 | 13.76 |
| Family-balanced ridge | 0.07 | 16.32 | -0.00 | -2.32 | 3.84 | 3.41 | 14.40 |
| SGD Huber | 0.07 | 10.48 | -0.01 | -1.77 | 3.24 | 2.53 | 12.62 |
| SGD elastic net | 0.06 | 13.01 | -0.01 | -4.25 | 3.30 | 2.97 | 11.41 |
| Neural network benchmark | 0.05 | 9.84 | -0.02 | -5.15 | 2.83 | 2.42 | 10.41 |
| Hierarchical validation ensemble | 0.05 | 10.70 | -0.03 | -7.39 | 2.29 | 1.68 | 5.92 |
| Hierarchical macro ridge | 0.05 | 9.83 | -0.03 | -7.32 | 2.24 | 1.73 | 8.36 |
| Hierarchical ensemble | 0.05 | 10.20 | -0.03 | -7.26 | 2.21 | 1.61 | 6.46 |
| Hierarchical macro analog | 0.04 | 8.79 | -0.03 | -7.60 | 1.95 | 1.24 | 5.54 |
| Hierarchical attention memory | 0.04 | 8.24 | -0.03 | -8.01 | 1.80 | 1.12 | 5.27 |
| Static 212 equal weight | 0.03 | 9.42 | -0.04 | -13.69 | 1.58 | 0.92 | 6.52 |

## 物理页 p72 · Table IA.16. Factor-Adjusted Performance Detail

| Object | Name | Mean IC | Controlled FMB t | EW L-S (%) | VW L-S (%) | Alpha (%) | Alpha t |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Stock-level or hierarchical model | Ridge plus macro residual | 0.07 | 2.42 | 3.80 | 2.10 | 3.32 | 14.22 |
| Stock-level or hierarchical model | Pooled all-212 ridge | 0.07 | 12.83 | 3.88 | 2.09 | 3.44 | 14.48 |
| Stock-level or hierarchical model | Decay-weighted ridge | 0.07 | 2.56 | 3.82 | 1.82 | 3.44 | 13.08 |
| Stock-level or hierarchical model | Ridge-decay blend | 0.07 | 0.03 | 3.80 | 1.81 | 3.39 | 13.42 |
| Stock-level or hierarchical model | Ridge plus validation residual | 0.07 | 2.21 | 3.77 | 2.01 | 3.31 | 13.62 |
| Stock-level or hierarchical model | Ridge plus macro-analog residual | 0.07 | 2.76 | 3.76 | 1.90 | 3.27 | 13.16 |
| Stock-level or hierarchical model | Ridge plus attention residual | 0.07 | 3.67 | 3.74 | 1.91 | 3.26 | 13.55 |
| Stock-level or hierarchical model | Ridge plus ensemble residual | 0.07 | 2.42 | 3.82 | 2.09 | 3.34 | 13.76 |
| Stock-level or hierarchical model | Family-balanced ridge | 0.07 | -1.62 | 3.84 | 2.06 | 3.41 | 14.40 |
| Stock-level or hierarchical model | SGD Huber | 0.07 | 0.72 | 3.24 | 2.24 | 2.53 | 12.62 |
| Stock-level or hierarchical model | SGD elastic net | 0.06 | 1.32 | 3.30 | 1.54 | 2.97 | 11.41 |
| Stock-level or hierarchical model | Neural network benchmark | 0.05 | 2.71 | 2.83 | 1.77 | 2.42 | 10.41 |
| Stock-level or hierarchical model | Hierarchical validation ensemble | 0.05 | 3.08 | 2.29 | 1.40 | 1.68 | 5.92 |
| Stock-level or hierarchical model | Hierarchical macro ridge | 0.05 | 3.29 | 2.24 | 1.44 | 1.73 | 8.36 |
| Stock-level or hierarchical model | Hierarchical ensemble | 0.05 | 2.74 | 2.21 | 1.30 | 1.61 | 6.46 |
| Stock-level or hierarchical model | Hierarchical macro analog | 0.04 | 2.38 | 1.95 | 1.04 | 1.24 | 5.54 |
| Stock-level or hierarchical model | Hierarchical attention memory | 0.04 | 2.06 | 1.80 | 0.94 | 1.12 | 5.27 |
| Stock-level or hierarchical model | Static 212 equal weight | 0.03 | 1.59 | 1.58 | 0.46 | 0.92 | 6.52 |
| Family allocation | Mixture of experts | 0.00 | 10.59 | 2.51 | 1.39 | 2.07 | 7.63 |
| Family allocation | Bayesian dynamic | 0.00 | 10.44 | 2.43 | 1.36 | 1.94 | 6.74 |
| Family allocation | Validation ensemble | 0.00 | 10.74 | 2.42 | 1.26 | 1.88 | 6.62 |
| Family allocation | Ensemble | 0.00 | 9.44 | 2.28 | 1.12 | 1.85 | 6.67 |
| Family allocation | Macro ridge | 0.00 | 8.17 | 2.14 | 1.07 | 1.73 | 6.39 |
| Family allocation | EWMA sleeve performance | 0.00 | 8.37 | 2.16 | 1.16 | 1.68 | 6.83 |
| Family allocation | Factor momentum | 0.00 | 8.76 | 2.20 | 1.17 | 1.64 | 6.68 |
| Family allocation | Regime probability | 0.00 | 6.85 | 2.05 | 1.00 | 1.47 | 7.73 |
| Family allocation | Trailing ic | 0.00 | 6.82 | 2.11 | 1.03 | 1.56 | 7.41 |
| Family allocation | Contextual bandit | 0.00 | 7.93 | 1.93 | 0.87 | 1.40 | 5.88 |
| Family allocation | Macro analog | 0.00 | 7.93 | 1.93 | 0.87 | 1.40 | 5.88 |
| Family allocation | Trailing Sharpe | 0.00 | 8.11 | 1.89 | 1.05 | 1.52 | 6.23 |
| Family allocation | Trailing return | 0.00 | 7.38 | 1.99 | 1.05 | 1.57 | 7.02 |
| Family allocation | Equal weight | 0.00 | 5.66 | 1.22 | 0.41 | 0.58 | 4.33 |
| Family allocation | Attention memory | 0.00 | 6.50 | 1.71 | 0.71 | 1.23 | 5.13 |

## 物理页 p75 · Table IA.17A. Regime-Family Payoff Cells: Credit Through Liquidity

| Macro block | Family | High ret. (%) | Low ret. (%) | H-L ret. (%) | Ret. t | H-L IC | IC t |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Credit | Continuation | 1.64 | 2.23 | -0.59 | -0.79 | -0.01 | -0.78 |
| Credit | Correction | -1.54 | 0.73 | -2.27 | -3.94 | -0.03 | -3.65 |
| Credit | Expectations | 0.67 | 1.33 | -0.66 | -1.16 | -0.01 | -1.04 |
| Credit | Investment/issuance | -0.75 | -0.86 | +0.12 | 0.36 | -0.00 | -0.14 |
| Credit | Liquidity/limits | -0.23 | 0.34 | -0.56 | -1.17 | -0.02 | -2.05 |
| Credit | Profitability/quality | 1.51 | 1.60 | -0.09 | -0.15 | -0.01 | -0.91 |
| Credit | Safety/downside | -1.26 | -1.53 | +0.26 | 0.39 | 0.01 | 0.67 |
| Credit | Valuation | 1.78 | 0.76 | +1.01 | 2.03 | 0.01 | 1.25 |
| Growth | Continuation | 2.62 | 1.12 | +1.50 | 2.04 | 0.02 | 2.37 |
| Growth | Correction | -0.82 | -0.17 | -0.65 | -1.03 | -0.00 | -0.54 |
| Growth | Expectations | 1.24 | 0.73 | +0.51 | 0.93 | 0.01 | 1.19 |
| Growth | Investment/issuance | -1.03 | -0.50 | -0.53 | -1.71 | -0.01 | -1.75 |
| Growth | Liquidity/limits | -0.16 | -0.20 | +0.04 | 0.07 | -0.00 | -0.07 |
| Growth | Profitability/quality | 2.08 | 0.88 | +1.20 | 1.98 | 0.01 | 1.95 |
| Growth | Safety/downside | -1.46 | -0.78 | -0.69 | -0.93 | -0.01 | -1.16 |
| Growth | Valuation | 1.60 | 0.91 | +0.69 | 1.33 | 0.01 | 1.56 |
| Inflation | Continuation | 2.14 | 2.55 | -0.41 | -0.59 | 0.01 | 0.76 |
| Inflation | Correction | 0.12 | -0.07 | +0.19 | 0.34 | 0.01 | 0.57 |
| Inflation | Expectations | 1.90 | 0.69 | +1.21 | 2.37 | 0.02 | 2.62 |
| Inflation | Investment/issuance | -1.34 | -0.68 | -0.66 | -2.17 | -0.01 | -2.37 |
| Inflation | Liquidity/limits | -0.07 | -0.21 | +0.14 | 0.27 | 0.00 | 0.25 |
| Inflation | Profitability/quality | 2.85 | 1.03 | +1.82 | 3.15 | 0.02 | 2.58 |
| Inflation | Safety/downside | -2.79 | -1.04 | -1.74 | -2.68 | -0.03 | -2.77 |
| Inflation | Valuation | 1.84 | 0.50 | +1.34 | 2.89 | 0.02 | 2.78 |
| Liquidity | Continuation | 1.00 | 2.16 | -1.15 | -1.68 | -0.02 | -1.79 |
| Liquidity | Correction | -0.97 | 0.13 | -1.10 | -1.85 | -0.01 | -1.16 |
| Liquidity | Expectations | 0.82 | 1.57 | -0.75 | -1.37 | -0.01 | -1.13 |
| Liquidity | Investment/issuance | -0.81 | -0.99 | +0.18 | 0.58 | 0.00 | 0.29 |
| Liquidity | Liquidity/limits | -0.17 | -0.67 | +0.50 | 1.04 | 0.01 | 0.61 |
| Liquidity | Profitability/quality | 1.56 | 1.85 | -0.29 | -0.52 | -0.01 | -1.23 |
| Liquidity | Safety/downside | -1.60 | -1.31 | -0.29 | -0.44 | -0.01 | -0.89 |
| Liquidity | Valuation | 1.35 | 1.89 | -0.54 | -1.13 | -0.02 | -1.75 |

## 物理页 p76 · Table IA.17B. Regime-Family Payoff Cells: Rates Through Valuation

| Macro block | Family | High ret. (%) | Low ret. (%) | H-L ret. (%) | Ret. t | H-L IC | IC t |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Rates | Continuation | 2.36 | 1.21 | +1.15 | 1.65 | 0.02 | 1.92 |
| Rates | Correction | 0.63 | -1.06 | +1.69 | 2.94 | 0.03 | 3.55 |
| Rates | Expectations | 1.43 | 0.45 | +0.98 | 1.94 | 0.02 | 2.09 |
| Rates | Investment/issuance | -0.97 | -0.66 | -0.31 | -1.07 | -0.00 | -0.81 |
| Rates | Liquidity/limits | 0.53 | -0.88 | +1.42 | 2.87 | 0.03 | 3.43 |
| Rates | Profitability/quality | 1.99 | 0.89 | +1.10 | 1.92 | 0.02 | 2.62 |
| Rates | Safety/downside | -2.09 | -0.29 | -1.80 | -2.55 | -0.03 | -3.05 |
| Rates | Valuation | 0.74 | 1.76 | -1.02 | -2.23 | -0.01 | -1.20 |
| Risk | Continuation | 1.98 | 1.62 | +0.35 | 0.50 | 0.00 | 0.03 |
| Risk | Correction | -1.51 | 0.19 | -1.70 | -2.78 | -0.02 | -2.11 |
| Risk | Expectations | 0.74 | 1.09 | -0.35 | -0.67 | -0.00 | -0.34 |
| Risk | Investment/issuance | -0.93 | -0.58 | -0.35 | -1.20 | -0.01 | -1.35 |
| Risk | Liquidity/limits | -1.14 | 0.07 | -1.20 | -2.45 | -0.02 | -2.53 |
| Risk | Profitability/quality | 1.09 | 1.46 | -0.38 | -0.64 | -0.00 | -0.64 |
| Risk | Safety/downside | -0.67 | -1.58 | +0.91 | 1.28 | 0.01 | 0.96 |
| Risk | Valuation | 1.64 | 0.86 | +0.78 | 1.59 | 0.01 | 1.09 |
| Trend | Continuation | 2.09 | 2.20 | -0.11 | -0.16 | -0.01 | -1.02 |
| Trend | Correction | -0.80 | 0.54 | -1.35 | -2.33 | -0.02 | -2.78 |
| Trend | Expectations | 1.10 | 1.35 | -0.25 | -0.50 | -0.01 | -0.93 |
| Trend | Investment/issuance | -0.82 | -0.99 | +0.17 | 0.58 | 0.01 | 1.01 |
| Trend | Liquidity/limits | -1.79 | 1.41 | -3.20 | -6.77 | -0.06 | -7.14 |
| Trend | Profitability/quality | 0.88 | 2.39 | -1.51 | -2.63 | -0.02 | -2.96 |
| Trend | Safety/downside | -0.31 | -2.69 | +2.39 | 3.50 | 0.04 | 4.24 |
| Trend | Valuation | 1.93 | 0.52 | +1.41 | 2.87 | 0.02 | 2.51 |
| Valuation | Continuation | -0.03 | 3.07 | -3.09 | -4.76 | -0.04 | -4.82 |
| Valuation | Correction | -0.42 | -0.46 | +0.05 | 0.08 | 0.00 | 0.16 |
| Valuation | Expectations | -0.38 | 1.94 | -2.32 | -5.12 | -0.04 | -5.28 |
| Valuation | Investment/issuance | -0.15 | -1.29 | +1.14 | 3.97 | 0.02 | 4.26 |
| Valuation | Liquidity/limits | -0.02 | -0.34 | +0.32 | 0.69 | 0.00 | 0.32 |
| Valuation | Profitability/quality | 0.30 | 2.33 | -2.03 | -3.83 | -0.03 | -4.25 |
| Valuation | Safety/downside | -0.45 | -1.83 | +1.38 | 2.20 | 0.02 | 2.34 |
| Valuation | Valuation | 0.41 | 1.93 | -1.52 | -3.36 | -0.04 | -5.28 |

## 物理页 p77 · Table IA.18. Liquidity/Limits × Trend Across Controls

| Test group | Construction | Low-high return (%) | t-statistic | High return (%) | Low return (%) | High months | Low months |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cross-sectional construction | Raw all firms | 3.13 | 7.41 | -2.23 | 0.89 | 248 | 248 |
| Cross-sectional construction | Ex micro | 1.71 | 4.58 | -1.45 | 0.25 | 248 | 248 |
| Cross-sectional construction | Large stocks | -0.18 | -0.53 | -0.25 | -0.43 | 248 | 248 |
| Cross-sectional construction | Liquid proxy | 1.71 | 4.58 | -1.45 | 0.25 | 248 | 248 |
| Cross-sectional construction | Industry neutral | 2.76 | 7.06 | -1.99 | 0.77 | 248 | 248 |
| Cross-sectional construction | Beta neutral | 3.00 | 7.24 | -2.12 | 0.88 | 248 | 248 |
| Time-state construction | All months | 3.13 | 7.41 | -2.23 | 0.89 | 248 | 248 |
| Time-state construction | Non crisis | 3.28 | 8.03 | -2.35 | 0.93 | 201 | 201 |
| Time-state construction | Crisis | 3.27 | 2.45 | -2.02 | 1.25 | 47 | 47 |
| Time-state construction | 1960s | 3.54 | 3.22 | -3.49 | 0.04 | 28 | 50 |
| Time-state construction | 1970s | 2.54 | 1.77 | -2.77 | -0.23 | 40 | 40 |
| Time-state construction | 1980s | 3.91 | 5.03 | -1.93 | 1.97 | 40 | 40 |
| Time-state construction | 1990s | 4.46 | 4.21 | -2.26 | 2.20 | 40 | 40 |
| Time-state construction | 2000s | 3.75 | 3.69 | -2.90 | 0.86 | 40 | 40 |
| Time-state construction | 2010s | 1.32 | 1.72 | -0.91 | 0.41 | 40 | 40 |
| Time-state construction | 2020s | 2.15 | 1.49 | -1.11 | 1.04 | 20 | 20 |

## 物理页 p78 · Table IA.19. Mechanism Survival Across Cross-Sectional Constructions

| Family-state pair | Construction | High-low return (%) | t-statistic | High return (%) | Low return (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| Continuation × Valuation | Raw all firms | -1.18 | -2.39 | 0.84 | 2.02 |
| Continuation × Valuation | Ex micro | -1.52 | -2.94 | 0.48 | 2.00 |
| Continuation × Valuation | Large stocks | -0.88 | -1.74 | 0.26 | 1.14 |
| Continuation × Valuation | Liquid proxy | -1.52 | -2.94 | 0.48 | 2.00 |
| Continuation × Valuation | Industry neutral | -0.69 | -2.02 | 0.56 | 1.24 |
| Continuation × Valuation | Beta neutral | -0.63 | -1.76 | 1.13 | 1.76 |
| Continuation × Valuation | All months | -1.18 | -2.39 | 0.84 | 2.02 |
| Continuation × Valuation | Non crisis | -0.89 | -2.31 | 1.17 | 2.05 |
| Continuation × Valuation | Crisis | -4.21 | -2.28 | -2.06 | 2.15 |
| Continuation × Valuation | 1960s | -0.64 | -0.60 | 1.89 | 2.53 |
| Continuation × Valuation | 1970s | -0.23 | -0.21 | 2.17 | 2.41 |
| Continuation × Valuation | 1980s | +1.41 | 1.84 | 2.75 | 1.35 |
| Continuation × Valuation | 1990s | +2.16 | 2.19 | 4.63 | 2.47 |
| Continuation × Valuation | 2000s | -4.17 | -1.86 | -1.19 | 2.99 |
| Continuation × Valuation | 2010s | -1.53 | -1.67 | 0.55 | 2.08 |
| Continuation × Valuation | 2020s | -2.83 | -1.63 | -0.35 | 2.48 |
| Liquidity/limits × Trend | Raw all firms | -3.13 | -7.41 | -2.23 | 0.89 |
| Liquidity/limits × Trend | Ex micro | -1.71 | -4.58 | -1.45 | 0.25 |
| Liquidity/limits × Trend | Large stocks | +0.18 | 0.53 | -0.25 | -0.43 |
| Liquidity/limits × Trend | Liquid proxy | -1.71 | -4.58 | -1.45 | 0.25 |
| Liquidity/limits × Trend | Industry neutral | -2.76 | -7.06 | -1.99 | 0.77 |
| Liquidity/limits × Trend | Beta neutral | -3.00 | -7.24 | -2.12 | 0.88 |
| Liquidity/limits × Trend | All months | -3.13 | -7.41 | -2.23 | 0.89 |
| Liquidity/limits × Trend | Non crisis | -3.28 | -8.03 | -2.35 | 0.93 |
| Liquidity/limits × Trend | Crisis | -3.27 | -2.45 | -2.02 | 1.25 |
| Liquidity/limits × Trend | 1960s | -3.54 | -3.22 | -3.49 | 0.04 |
| Liquidity/limits × Trend | 1970s | -2.54 | -1.77 | -2.77 | -0.23 |
| Liquidity/limits × Trend | 1980s | -3.91 | -5.03 | -1.93 | 1.97 |
| Liquidity/limits × Trend | 1990s | -4.46 | -4.21 | -2.26 | 2.20 |
| Liquidity/limits × Trend | 2000s | -3.75 | -3.69 | -2.90 | 0.86 |
| Liquidity/limits × Trend | 2010s | -1.32 | -1.72 | -0.91 | 0.41 |
| Liquidity/limits × Trend | 2020s | -2.15 | -1.49 | -1.11 | 1.04 |

## 物理页 p79 · Table IA.20A. Family Drop-One Contribution Evidence: First Rule Group

| Allocation rule | Omitted family | Full ret. (%) | Full t | Omit ret. (%) | Omit t | Contrib. (%) | Contrib. t | Weight (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Attention memory | Continuation | 1.48 | 6.56 | 0.86 | 4.34 | 0.62 | 3.78 | 36.08 |
| Attention memory | Correction | 1.48 | 6.56 | 1.48 | 6.59 | -0.00 | -0.06 | 7.77 |
| Attention memory | Expectations | 1.48 | 6.56 | 1.48 | 6.48 | -0.00 | -0.06 | 5.69 |
| Attention memory | Investment/issuance | 1.48 | 6.56 | 1.48 | 6.54 | -0.01 | -0.25 | 2.66 |
| Attention memory | Liquidity/limits | 1.48 | 6.56 | 1.57 | 6.83 | -0.10 | -1.52 | 6.86 |
| Attention memory | Profitability/quality | 1.48 | 6.56 | 1.41 | 6.25 | 0.06 | 1.15 | 16.06 |
| Attention memory | Safety/downside | 1.48 | 6.56 | 1.66 | 7.77 | -0.18 | -2.86 | 8.44 |
| Attention memory | Valuation | 1.48 | 6.56 | 1.40 | 5.83 | 0.08 | 0.62 | 16.45 |
| Ensemble | Continuation | 1.95 | 8.05 | 1.29 | 6.49 | 0.67 | 3.52 | 50.74 |
| Ensemble | Correction | 1.95 | 8.05 | 1.93 | 7.88 | 0.02 | 0.90 | 3.11 |
| Ensemble | Expectations | 1.95 | 8.05 | 1.98 | 8.12 | -0.03 | -2.32 | 4.16 |
| Ensemble | Investment/issuance | 1.95 | 8.05 | 1.92 | 7.87 | 0.03 | 1.53 | 1.27 |
| Ensemble | Liquidity/limits | 1.95 | 8.05 | 1.92 | 7.83 | 0.03 | 0.78 | 4.19 |
| Ensemble | Profitability/quality | 1.95 | 8.05 | 1.89 | 7.81 | 0.06 | 0.99 | 16.75 |
| Ensemble | Safety/downside | 1.95 | 8.05 | 2.04 | 8.82 | -0.09 | -1.84 | 2.07 |
| Ensemble | Valuation | 1.95 | 8.05 | 1.94 | 7.70 | 0.01 | 0.13 | 17.72 |
| Macro analog | Continuation | 1.62 | 6.91 | 1.02 | 4.97 | 0.60 | 3.54 | 39.58 |
| Macro analog | Correction | 1.62 | 6.91 | 1.61 | 6.86 | 0.01 | 0.20 | 6.69 |
| Macro analog | Expectations | 1.62 | 6.91 | 1.63 | 6.92 | -0.01 | -0.52 | 5.80 |
| Macro analog | Investment/issuance | 1.62 | 6.91 | 1.63 | 6.97 | -0.01 | -0.65 | 2.15 |
| Macro analog | Liquidity/limits | 1.62 | 6.91 | 1.67 | 7.03 | -0.05 | -1.16 | 5.01 |
| Macro analog | Profitability/quality | 1.62 | 6.91 | 1.57 | 6.83 | 0.05 | 0.81 | 17.59 |
| Macro analog | Safety/downside | 1.62 | 6.91 | 1.72 | 7.73 | -0.10 | -2.09 | 5.34 |
| Macro analog | Valuation | 1.62 | 6.91 | 1.56 | 6.46 | 0.06 | 0.52 | 17.84 |

## 物理页 p80 · Table IA.20B. Family Drop-One Contribution Evidence: Second Rule Group

| Allocation rule | Omitted family | Full ret. (%) | Full t | Omit ret. (%) | Omit t | Contrib. (%) | Contrib. t | Weight (%) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Macro ridge | Continuation | 1.82 | 7.60 | 1.32 | 6.79 | 0.50 | 3.50 | 42.16 |
| Macro ridge | Correction | 1.82 | 7.60 | 1.84 | 7.61 | -0.02 | -1.14 | 3.77 |
| Macro ridge | Expectations | 1.82 | 7.60 | 1.85 | 7.73 | -0.03 | -2.60 | 3.35 |
| Macro ridge | Investment/issuance | 1.82 | 7.60 | 1.82 | 7.59 | 0.00 | 0.04 | 1.39 |
| Macro ridge | Liquidity/limits | 1.82 | 7.60 | 1.73 | 6.92 | 0.09 | 1.32 | 9.50 |
| Macro ridge | Profitability/quality | 1.82 | 7.60 | 1.76 | 7.54 | 0.06 | 1.12 | 15.71 |
| Macro ridge | Safety/downside | 1.82 | 7.60 | 1.99 | 8.62 | -0.17 | -2.96 | 4.60 |
| Macro ridge | Valuation | 1.82 | 7.60 | 1.80 | 6.89 | 0.01 | 0.12 | 19.52 |
| Mixture of experts | Continuation | 2.13 | 9.21 | 1.49 | 7.65 | 0.64 | 3.05 | 60.74 |
| Mixture of experts | Correction | 2.13 | 9.21 | 2.14 | 9.21 | -0.01 | -1.57 | 0.60 |
| Mixture of experts | Expectations | 2.13 | 9.21 | 2.14 | 9.33 | -0.02 | -1.82 | 1.98 |
| Mixture of experts | Investment/issuance | 2.13 | 9.21 | 2.12 | 9.09 | 0.01 | 0.97 | 0.27 |
| Mixture of experts | Liquidity/limits | 2.13 | 9.21 | 2.09 | 9.07 | 0.04 | 1.28 | 3.64 |
| Mixture of experts | Profitability/quality | 2.13 | 9.21 | 2.10 | 9.30 | 0.03 | 0.53 | 14.40 |
| Mixture of experts | Safety/downside | 2.13 | 9.21 | 2.14 | 9.27 | -0.01 | -0.61 | 0.93 |
| Mixture of experts | Valuation | 2.13 | 9.21 | 2.08 | 8.41 | 0.05 | 0.46 | 17.44 |
| Validation ensemble | Continuation | 2.08 | 9.09 | 1.50 | 6.92 | 0.58 | 2.25 | 56.49 |
| Validation ensemble | Correction | 2.08 | 9.09 | 2.05 | 8.91 | 0.02 | 0.75 | 2.71 |
| Validation ensemble | Expectations | 2.08 | 9.09 | 2.09 | 9.13 | -0.01 | -1.03 | 2.64 |
| Validation ensemble | Investment/issuance | 2.08 | 9.09 | 2.06 | 8.97 | 0.02 | 1.32 | 0.79 |
| Validation ensemble | Liquidity/limits | 2.08 | 9.09 | 2.01 | 8.71 | 0.07 | 1.41 | 3.57 |
| Validation ensemble | Profitability/quality | 2.08 | 9.09 | 2.08 | 9.08 | -0.00 | -0.10 | 15.85 |
| Validation ensemble | Safety/downside | 2.08 | 9.09 | 2.11 | 9.58 | -0.03 | -0.85 | 1.47 |
| Validation ensemble | Valuation | 2.08 | 9.09 | 1.98 | 7.76 | 0.10 | 0.65 | 16.47 |

## 物理页 p82 · Table IA.21. Regime-Local Reliability

| Macro block | Regime | Model | Mean IC | IC t | Inc. IC | Inc. t | FMB t | Months |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Valuation | Low | Static 212 equal weight | 0.05 | 11.10 | -0.05 | -11.06 | 1.71 | 160 |
| Risk | High | Static 212 equal weight | 0.02 | 4.37 | -0.05 | -9.69 | -1.13 | 160 |
| Liquidity | High | Static 212 equal weight | 0.02 | 3.59 | -0.05 | -8.30 | -0.36 | 160 |
| Inflation | High | Static 212 equal weight | 0.04 | 6.48 | -0.05 | -8.01 | 1.53 | 160 |
| Credit | High | Static 212 equal weight | 0.03 | 4.95 | -0.05 | -9.21 | 1.09 | 160 |
| Growth | Middle | Static 212 equal weight | 0.03 | 5.81 | -0.05 | -10.03 | -0.09 | 159 |
| Rates | Middle | Static 212 equal weight | 0.03 | 4.95 | -0.05 | -8.84 | -0.02 | 159 |
| Credit | Middle | Static 212 equal weight | 0.02 | 3.75 | -0.04 | -8.88 | -0.42 | 159 |
| Inflation | Low | Static 212 equal weight | 0.03 | 7.24 | -0.04 | -10.90 | 0.63 | 160 |
| Trend | Low | Static 212 equal weight | 0.04 | 5.38 | -0.04 | -7.76 | 1.72 | 160 |
| Growth | High | Static 212 equal weight | 0.04 | 7.47 | -0.04 | -9.36 | 2.71 | 160 |
| Valuation | Low | Hierarchical macro ridge | 0.06 | 9.53 | -0.04 | -6.93 | 1.52 | 160 |
| Valuation | Low | Hierarchical validation ensemble | 0.06 | 9.44 | -0.04 | -7.38 | 1.56 | 160 |
| Rates | Low | Static 212 equal weight | 0.02 | 4.31 | -0.04 | -7.29 | 0.63 | 160 |
| Trend | High | Static 212 equal weight | 0.02 | 6.20 | -0.04 | -8.95 | 0.33 | 160 |
| Trend | Middle | Static 212 equal weight | 0.03 | 6.02 | -0.04 | -7.75 | 0.38 | 159 |
| Liquidity | Low | Static 212 equal weight | 0.04 | 9.52 | -0.04 | -7.49 | 2.29 | 160 |
| Risk | Middle | Static 212 equal weight | 0.04 | 6.49 | -0.04 | -9.06 | 2.81 | 159 |
| Valuation | Middle | Static 212 equal weight | 0.04 | 6.87 | -0.04 | -7.84 | 2.83 | 159 |
| Rates | High | Static 212 equal weight | 0.04 | 7.16 | -0.04 | -9.51 | 1.85 | 160 |
| Liquidity | Middle | Static 212 equal weight | 0.03 | 6.12 | -0.04 | -9.83 | 1.60 | 159 |
| Growth | Low | Static 212 equal weight | 0.02 | 4.48 | -0.04 | -5.84 | -0.28 | 160 |
| Risk | High | Hierarchical validation ensemble | 0.04 | 5.28 | -0.04 | -4.34 | 0.39 | 160 |
| Risk | Low | Static 212 equal weight | 0.03 | 5.82 | -0.04 | -6.94 | 1.20 | 160 |
| Inflation | Middle | Static 212 equal weight | 0.02 | 4.29 | -0.03 | -7.12 | 0.54 | 159 |
| Credit | Low | Static 212 equal weight | 0.04 | 7.74 | -0.03 | -7.21 | 2.96 | 160 |
| Valuation | High | Static 212 equal weight | 0.01 | 1.34 | -0.03 | -6.43 | -2.04 | 160 |
| Risk | High | Hierarchical macro ridge | 0.04 | 5.33 | -0.03 | -5.16 | 0.98 | 160 |
| Credit | High | Hierarchical macro ridge | 0.04 | 3.95 | -0.03 | -5.22 | 0.95 | 160 |
| Inflation | High | Hierarchical validation ensemble | 0.06 | 6.09 | -0.03 | -5.50 | 1.28 | 160 |
| Credit | High | Hierarchical validation ensemble | 0.04 | 4.82 | -0.03 | -5.84 | 1.19 | 160 |
| Liquidity | Low | Hierarchical macro ridge | 0.05 | 10.02 | -0.03 | -6.66 | 2.95 | 160 |
| Liquidity | Low | Hierarchical validation ensemble | 0.05 | 7.22 | -0.03 | -6.07 | 2.09 | 160 |
| Rates | Low | Hierarchical validation ensemble | 0.04 | 3.92 | -0.03 | -5.29 | 1.08 | 160 |
| Growth | Middle | Hierarchical validation ensemble | 0.05 | 7.36 | -0.03 | -6.73 | 2.00 | 159 |
| Trend | Middle | Hierarchical macro ridge | 0.04 | 5.37 | -0.03 | -4.91 | 0.82 | 159 |
| Rates | Low | Neural network benchmark | 0.04 | 4.29 | -0.03 | -3.79 | 0.64 | 160 |
| Rates | Low | Hierarchical macro ridge | 0.04 | 3.97 | -0.03 | -5.56 | 1.09 | 160 |
| Growth | Middle | Hierarchical macro ridge | 0.05 | 6.78 | -0.03 | -5.92 | 3.06 | 159 |
| Valuation | Low | Neural network benchmark | 0.07 | 8.48 | -0.03 | -4.62 | 1.69 | 160 |

## 物理页 p84 · Table IA.22. Capacity Region Monthly Evidence

| Capacity region | Metric | Low-high value | t-statistic | High state | Low state | High months | Low months |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All firms | EW return | 0.03 | 7.41 | -0.02 | 0.01 | 248 | 248 |
| All firms | VW return | 0.03 | 6.16 | -0.02 | 0.01 | 248 | 248 |
| All firms | IC | 0.07 | 8.32 | -0.04 | 0.03 | 248 | 248 |
| Micro bottom 20 | EW return | 0.01 | 2.11 | -0.02 | -0.01 | 248 | 248 |
| Micro bottom 20 | VW return | 0.01 | 1.98 | -0.02 | -0.01 | 248 | 248 |
| Micro bottom 20 | IC | 0.01 | 1.78 | -0.04 | -0.03 | 248 | 248 |
| Outside microcaps | EW return | 0.02 | 4.58 | -0.01 | 0.00 | 248 | 248 |
| Outside microcaps | VW return | 0.01 | 3.73 | -0.01 | 0.00 | 248 | 248 |
| Outside microcaps | IC | 0.05 | 6.69 | -0.04 | 0.01 | 248 | 248 |
| Middle 60 | EW return | 0.01 | 3.67 | -0.01 | 0.00 | 248 | 248 |
| Middle 60 | VW return | 0.01 | 3.02 | -0.01 | 0.00 | 248 | 248 |
| Middle 60 | IC | 0.04 | 4.90 | -0.03 | 0.00 | 248 | 248 |
| Upper half | EW return | 0.01 | 1.58 | -0.01 | -0.00 | 248 | 248 |
| Upper half | VW return | 0.01 | 1.72 | -0.01 | -0.00 | 248 | 248 |
| Upper half | IC | 0.02 | 3.38 | -0.02 | -0.00 | 248 | 248 |
| Upper third | EW return | 0.00 | 0.54 | -0.01 | -0.00 | 248 | 248 |
| Upper third | VW return | -0.00 | -0.03 | -0.01 | -0.01 | 248 | 248 |
| Upper third | IC | 0.01 | 1.77 | -0.02 | -0.01 | 248 | 248 |
| Large top 20 | EW return | -0.00 | -0.53 | -0.00 | -0.00 | 248 | 248 |
| Large top 20 | VW return | -0.01 | -1.29 | -0.00 | -0.01 | 248 | 248 |
| Large top 20 | IC | -0.00 | -0.11 | -0.01 | -0.01 | 248 | 248 |
| Mega top 10 | EW return | -0.01 | -1.57 | -0.00 | -0.01 | 248 | 248 |
| Mega top 10 | VW return | -0.01 | -2.09 | 0.00 | -0.01 | 248 | 248 |
| Mega top 10 | IC | -0.02 | -1.54 | -0.00 | -0.02 | 248 | 248 |

## 物理页 p85 · Table IA.23. Capacity Boundary Evidence

| Economic screen | Sample | Metric | Estimate | t-statistic | Economic interpretation |
| --- | --- | --- | ---: | ---: | --- |
| All firms state dependence | All firms | EW return | -0.03 | -7.41 | Full-universe state dependence is present |
| Outside microcaps | Outside microcaps | EW return | -0.02 | -4.58 | The mechanism extends beyond the bottom-size quintile |
| Midcap limits to arbitrage zone | Middle 60 | EW return | -0.01 | -3.67 | The mechanism remains strong where limits to arbitrage are plausible and capacity is greater than in microcaps |
| Top half capacity | Upper half | EW return | -0.01 | -1.58 | Tests whether the effect reaches the top half of market capitalization |
| Large top20 boundary | Large top 20 | EW return | 0.00 | 0.53 | Tests whether the effect is safe for large-stock-exclusive claims |
| Mega top10 boundary | Mega top 10 | EW return | 0.01 | 1.57 | Tests whether the effect is safe for mega-cap-exclusive claims |
| Ex micro value weighted | Outside microcaps | VW return | -0.01 | -3.73 | Tests whether the effect is solely equal-weighted |
| Ex micro confirmation | Outside microcaps | EW return | -0.00 | -0.51 | Tests whether the ex-micro effect survives the post-2005 holdout |
| Overall capacity boundary | Summary |  | -0.02 | -4.58 | The mechanism extends beyond microcaps and is shaped by capacity |

## 物理页 p88 · Table IA.24. Calendar and Random-State Comparisons

| Comparison | Allocation rule | Estimate (%) | t-statistic | Months |
| --- | --- | ---: | ---: | ---: |
| Macro shuffle minus full macro | Macro analog | -0.28 | -1.21 | 479 |
| Macro shuffle minus full macro | Macro ridge | -0.29 | -1.03 | 479 |
| Macro shuffle minus full macro | Attention memory | -0.33 | -1.36 | 479 |
| Macro shuffle minus full macro | Ensemble | -0.36 | -1.53 | 479 |
| Single-risk-state benchmark minus full macro | Macro analog | +0.22 | 1.00 | 479 |
| Single-risk-state benchmark minus full macro | Macro ridge | +0.15 | 0.75 | 479 |
| Single-risk-state benchmark minus full macro | Attention memory | +0.19 | 0.78 | 479 |
| Single-risk-state benchmark minus full macro | Ensemble | +0.01 | 0.04 | 479 |
| Calendar dummy minus full macro | Macro analog | +0.41 | 1.53 | 479 |
| Calendar dummy minus full macro | Macro ridge | +0.31 | 1.18 | 479 |
| Calendar dummy minus full macro | Attention memory | +0.65 | 2.41 | 479 |
| Calendar dummy minus full macro | Ensemble | +0.11 | 0.44 | 479 |
| Random macro minus full macro | Macro analog | -0.14 | -0.66 | 479 |
| Random macro minus full macro | Macro ridge | -0.17 | -0.72 | 479 |
| Random macro minus full macro | Attention memory | -0.21 | -1.01 | 479 |
| Random macro minus full macro | Ensemble | -0.21 | -0.95 | 479 |

## 物理页 p89 · Table IA.25. Macro-Block Drop Tests

| Block comparison | Allocation rule | Estimate (%) | t-statistic | Months |
| --- | --- | ---: | ---: | ---: |
| Drop Inflation block minus full macro states | Macro analog | -0.08 | -0.57 | 479 |
| Drop Inflation block minus full macro states | Macro ridge | +0.12 | 0.91 | 479 |
| Drop Inflation block minus full macro states | Attention memory | -0.13 | -0.88 | 479 |
| Drop Inflation block minus full macro states | Ensemble | +0.04 | 0.33 | 479 |
| Drop Growth block minus full macro states | Macro analog | +0.05 | 0.63 | 479 |
| Drop Growth block minus full macro states | Macro ridge | +0.02 | 0.30 | 479 |
| Drop Growth block minus full macro states | Attention memory | -0.05 | -0.48 | 479 |
| Drop Growth block minus full macro states | Ensemble | +0.04 | 0.52 | 479 |
| Drop Rates block minus full macro states | Macro analog | +0.00 | 0.05 | 479 |
| Drop Rates block minus full macro states | Macro ridge | +0.14 | 1.97 | 479 |
| Drop Rates block minus full macro states | Attention memory | -0.04 | -0.51 | 479 |
| Drop Rates block minus full macro states | Ensemble | +0.05 | 1.19 | 479 |
| Drop Credit block minus full macro states | Macro analog | +0.05 | 0.94 | 479 |
| Drop Credit block minus full macro states | Macro ridge | +0.05 | 0.62 | 479 |
| Drop Credit block minus full macro states | Attention memory | -0.06 | -0.86 | 479 |
| Drop Credit block minus full macro states | Ensemble | -0.03 | -0.57 | 479 |
| Drop Liquidity block minus full macro states | Macro analog | +0.03 | 0.59 | 479 |
| Drop Liquidity block minus full macro states | Macro ridge | +0.09 | 1.05 | 479 |
| Drop Liquidity block minus full macro states | Attention memory | +0.10 | 1.91 | 479 |
| Drop Liquidity block minus full macro states | Ensemble | +0.03 | 0.87 | 479 |
| Drop Risk block minus full macro states | Macro analog | +0.02 | 0.16 | 479 |
| Drop Risk block minus full macro states | Macro ridge | -0.02 | -0.23 | 479 |
| Drop Risk block minus full macro states | Attention memory | -0.06 | -0.36 | 479 |
| Drop Risk block minus full macro states | Ensemble | -0.04 | -0.27 | 479 |
| Drop Valuation block minus full macro states | Macro analog | +0.00 | 0.31 | 479 |
| Drop Valuation block minus full macro states | Macro ridge | -0.01 | -1.42 | 479 |
| Drop Valuation block minus full macro states | Attention memory | +0.01 | 0.46 | 479 |
| Drop Valuation block minus full macro states | Ensemble | +0.02 | 1.40 | 479 |
| Drop Trend block minus full macro states | Macro analog | -0.00 | -0.05 | 479 |
| Drop Trend block minus full macro states | Macro ridge | +0.01 | 0.14 | 479 |
| Drop Trend block minus full macro states | Attention memory | -0.03 | -0.31 | 479 |
| Drop Trend block minus full macro states | Ensemble | -0.08 | -1.23 | 479 |

## 物理页 p90 · Table IA.26. Release-Lag and Timing Comparisons

| Timing or construction comparison | Allocation rule | Estimate (%) | t-statistic | Months |
| --- | --- | ---: | ---: | ---: |
| Market beta residualized sleeves | Valuation | +1.28 | 7.12 | 742 |
| Market beta residualized sleeves | Continuation | +1.18 | 7.15 | 742 |
| Market beta residualized sleeves | Correction | -1.51 | -9.35 | 742 |
| Market beta residualized sleeves | Profitability/quality | +0.74 | 5.27 | 742 |
| Market beta residualized sleeves | Investment/issuance | -0.64 | -7.90 | 742 |
| Market beta residualized sleeves | Safety/downside | -0.57 | -2.92 | 742 |
| Market beta residualized sleeves | Liquidity/limits | -0.97 | -6.37 | 742 |
| Market beta residualized sleeves | Expectations | +0.49 | 4.04 | 742 |
| Orthogonalized sleeves timed | Macro analog | +0.08 | 0.49 | 479 |
| Orthogonalized sleeves timed | Macro ridge | +0.05 | 0.32 | 479 |
| Orthogonalized sleeves timed | Attention memory | +0.10 | 0.66 | 479 |
| Orthogonalized sleeves timed | Ensemble | +0.09 | 0.46 | 479 |
| Extra lag minus equal weight | Macro analog | +1.23 | 5.90 | 479 |
| Extra lag minus equal weight | Macro ridge | +1.45 | 7.08 | 479 |
| Extra lag minus equal weight | Attention memory | +1.08 | 5.39 | 479 |
| Extra lag minus equal weight | Ensemble | +1.58 | 7.61 | 479 |

## 物理页 p91 · Table IA.27. Prespecified Holdout Evidence

| Family-state pair | Period | H-L ret. (%) | t-stat. | High months | Low months |
| --- | --- | ---: | ---: | ---: | ---: |
| Liquidity/limits × Trend | Formation period, 1985–2004 | -4.26 | -5.69 | 80 | 80 |
| Liquidity/limits × Trend | Confirmation period, 2005 onward | -1.86 | -3.11 | 62 | 107 |
| Continuation × Valuation | Formation period, 1985–2004 | +0.05 | 0.05 | 80 | 80 |
| Continuation × Valuation | Confirmation period, 2005 onward | +0.00 | 0.00 | 223 | 2 |

## 物理页 p92 · Table IA.28. Placebo and Permutation Evidence

| Family-state pair | Comparison | Actual t | Comparison mean abs. t | Comparison max abs. t | Estimate (%) |
| --- | --- | ---: | ---: | ---: | ---: |
| Liquidity/limits × Trend | Actual macro-family pair | -7.41 | 0.00 | 0.00 | -3.13 |
| Liquidity/limits × Trend | Circularly shifted macro state | -7.41 | 0.56 | 1.07 | -3.13 |
| Liquidity/limits × Trend | Calendar-month state | -7.41 | 1.10 | 1.10 | +0.43 |
| Liquidity/limits × Trend | Family-label relabeling | -7.41 | 2.00 | 4.61 | -3.13 |
| Continuation × Valuation | Actual macro-family pair | -2.39 | 0.00 | 0.00 | -1.18 |
| Continuation × Valuation | Circularly shifted macro state | -2.39 | 1.92 | 3.27 | -1.18 |
| Continuation × Valuation | Calendar-month state | -2.39 | 0.53 | 0.53 | +0.25 |
| Continuation × Valuation | Family-label relabeling | -2.39 | 2.28 | 3.38 | -1.18 |

## 物理页 p94 · Table IA.29. Frontier Model Benchmarks

| Model | Role | Mean IC | IC t | Incremental IC vs pooled ridge | Incremental t | Alpha t |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Ridge plus macro residual | Macro residual after full-panel ridge | 0.07 | 15.63 | 0.00 | 0.21 | 14.22 |
| Pooled all-212 ridge | Full-panel stock-level benchmark | 0.07 | 15.93 | 0.00 | 0.00 | 14.48 |
| Decay-weighted ridge | Decay-aware linear benchmark | 0.07 | 15.08 | -0.00 | -0.13 | 13.08 |
| Ridge-decay blend | Decay-aware linear benchmark | 0.07 | 15.18 | -0.00 | -0.74 | 13.42 |
| Ridge plus validation residual | Macro residual after full-panel ridge | 0.07 | 15.64 | -0.00 | -0.67 | 13.62 |
| Ridge plus macro-analog residual | Macro residual after full-panel ridge | 0.07 | 15.59 | -0.00 | -0.90 | 13.16 |
| Ridge plus attention residual | Macro residual after full-panel ridge | 0.07 | 15.71 | -0.00 | -1.17 | 13.55 |
| Ridge plus ensemble residual | Macro residual after full-panel ridge | 0.07 | 15.69 | -0.00 | -0.94 | 13.76 |
| Family-balanced ridge | Family-balanced linear benchmark | 0.07 | 16.32 | -0.00 | -2.32 | 14.40 |
| SGD Huber | Regularized stock-level benchmark | 0.07 | 10.48 | -0.01 | -1.77 | 12.62 |
| SGD elastic net | Regularized stock-level benchmark | 0.06 | 13.01 | -0.01 | -4.25 | 11.41 |
| Neural network benchmark | Neural stock-level benchmark | 0.05 | 9.84 | -0.02 | -5.15 | 10.41 |
| Hierarchical validation ensemble | Macro-regime hierarchical 212 benchmark | 0.05 | 10.70 | -0.03 | -7.39 | 5.92 |
| Hierarchical macro ridge | Macro-regime hierarchical 212 benchmark | 0.05 | 9.83 | -0.03 | -7.32 | 8.36 |
| Hierarchical ensemble | Macro-regime hierarchical 212 benchmark | 0.05 | 10.20 | -0.03 | -7.26 | 6.46 |
| Hierarchical macro analog | Macro-regime hierarchical 212 benchmark | 0.04 | 8.79 | -0.03 | -7.60 | 5.54 |
| Hierarchical attention memory | Macro-regime hierarchical 212 benchmark | 0.04 | 8.24 | -0.03 | -8.01 | 5.27 |
| Static 212 equal weight | Static 212-characteristic baseline | 0.03 | 9.42 | -0.04 | -13.69 | 6.52 |

## 物理页 p95 · Table IA.30. Compute-Heavy Model Benchmarks

| Model | Mean IC | IC t | Incremental IC vs pooled ridge | Incremental t | EW L-S (%) | Alpha (%) | Alpha t |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Pooled all-212 ridge | 0.07 | 15.93 | 0.00 | 0.00 | 3.88 | 3.44 | 14.48 |
| Ridge plus validation residual | 0.07 | 15.64 | -0.00 | -0.67 | 3.77 | 3.31 | 13.62 |
| SGD Huber | 0.07 | 10.48 | -0.01 | -1.77 | 3.24 | 2.53 | 12.62 |
| SGD elastic net | 0.06 | 13.01 | -0.01 | -4.25 | 3.30 | 2.97 | 11.41 |
| Neural network benchmark | 0.05 | 9.84 | -0.02 | -5.15 | 2.83 | 2.42 | 10.41 |

## 物理页 p99 · Table IA.31. Evidence Map for the Main Result

| Evidence block | Where reported | Economic interpretation |
| --- | --- | --- |
| Allocation value | Main Tables 3–4; IA.6–IA.10 | Macro-regime memory changes how capital is assigned across economic anomaly families. |
| Full-panel breadth | Main Table 5; IA.12–IA.16 | The allocation structure remains connected to the full 212-characteristic panel. |
| Lead mechanism | Main Tables 8–9; IA.17A–IA.19 | Liquidity/limits × trend is the sharpest family-state channel. |
| Capacity shape | Main Table 10; IA.22–IA.23 | The mechanism is strongest where limits to arbitrage should matter most. |
| State specificity | Main Tables 11–13; IA.24–IA.28 | Perturbed state definitions and relabeling exercises produce materially smaller evidence. |
| Model benchmarks | Main Tables 6–7 and 12; IA.14–IA.16 and IA.29–IA.30 | The pooled all-212 ridge provides a demanding stock-level benchmark. |

## 物理页 p101 · Table IA.32. Macro Conditioning Variable Classification

| Classification | Count | Variables |
| --- | ---: | --- |
| Market prices, rates, spreads, and direct market states | 11 | VIX; federal funds rate; three-month Treasury bill; two-year Treasury yield; ten-year Treasury yield; BAA-Treasury spread; corporate OAS; S&P 500; market return; 12-month market trend; 12-month market drawdown |
| Panel-derived cross-sectional market states | 4 | market volatility proxy; cross-sectional dispersion; aggregate valuation; aggregate liquidity |
| Government real-activity and inflation states | 7 | CPIAUCSL; PCEPI; CPILFESL; INDPRO; UNRATE; PAYEMS; USREC |
| Fully covered ALFRED real-time external series | 3 | INDPRO; PAYEMS; UNRATE |
| Mixed ALFRED and conservative-vintage external series | 8 | CPIAUCSL; CPILFESL; FEDFUNDS; GS10; GS2; PCEPI; TB3MS; USREC |
| Conservative external fallback series | 5 | BAA10Y; BAMLC0A0CM; SP500; STLFSI4; VIXCLS |
| Panel-derived prior-return-state variables | 7 | market return; market volatility proxy; cross-sectional dispersion; aggregate valuation; aggregate liquidity; 12-month market trend; 12-month market drawdown |

## 物理页 p102 · Table IA.34. Publication-Year Coverage of the 212-Signal Universe

### Panel A. Family coverage by first out-of-sample year

| Family | Available by 1985 | Published after 1985 |
| --- | ---: | ---: |
| Continuation | 0 | 27 |
| Correction | 0 | 4 |
| Expectations | 3 | 22 |
| Investment/issuance | 0 | 46 |
| Liquidity/limits | 2 | 19 |
| Profitability/quality | 0 | 27 |
| Safety/downside | 1 | 25 |
| Valuation | 3 | 33 |

### Panel B. Published-signal availability over prediction years

| Prediction year | Eligible signals | Share of 212 | Continuation | Valuation | Liquidity/limits |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1985 | 9 | 4.25% | 0 | 3 | 2 |
| 1990 | 13 | 6.13% | 0 | 3 | 2 |
| 1995 | 24 | 11.32% | 2 | 8 | 4 |
| 2000 | 49 | 23.11% | 5 | 14 | 5 |
| 2005 | 85 | 40.09% | 7 | 17 | 9 |
| 2010 | 165 | 77.83% | 21 | 32 | 16 |
| 2015 | 206 | 97.17% | 26 | 36 | 21 |
| 2020 | 212 | 100.00% | 27 | 36 | 21 |
| 2024 | 212 | 100.00% | 27 | 36 | 21 |

## 物理页 p104 · Table IA.33. Liquidity/Limits Trend Reversal by Episode Exclusion

| Sample | High-trend mean | Low-trend mean | High-minus-low | Welch t-stat | High / low months |
| --- | ---: | ---: | ---: | ---: | --- |
| All months | -1.79% | 1.41% | -3.20% | -6.77 | 160 / 160 |
| Excluding 1987 crash | -1.79% | 1.35% | -3.15% | -6.69 | 160 / 158 |
| Excluding LTCM/Russia 1998 | -1.79% | 1.40% | -3.20% | -6.76 | 160 / 157 |
| Excluding dot-com 2000–2002 | -1.65% | 1.50% | -3.15% | -6.73 | 149 / 146 |
| Excluding GFC 2007–2009 | -1.74% | 1.44% | -3.18% | -6.50 | 155 / 140 |
| Excluding eurozone/debt-ceiling 2011 | -1.82% | 1.41% | -3.23% | -6.85 | 159 / 156 |
| Excluding Q4 2018 | -1.79% | 1.44% | -3.23% | -6.87 | 160 / 158 |
| Excluding COVID 2020 | -1.78% | 1.42% | -3.21% | -6.70 | 156 / 157 |
| Excluding reopening 2021 | -1.81% | 1.42% | -3.23% | -6.70 | 150 / 159 |
| Excluding inflation/rate shock 2022 | -1.79% | 1.48% | -3.27% | -6.84 | 160 / 149 |

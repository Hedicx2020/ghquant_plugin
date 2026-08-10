# R1-R10 表格证据层（PDF 终审补齐）

- 文档页数：18 页。
- 证据来源：`report_text.md` 与 PDF 原页逐格终审。
- 空白规则：原表空白格写为 `n/a`，不推算。
- 覆盖范围：R1-R10；Exhibit 8-17 中全部数值表，以及 p8-p9 的风险状态计数。

## R1 · p8-p9 · 风险状态数量与样本占比

来源定位：p8 Exhibit 6-7；p9 状态占比正文。

| 项目 | 数值 |
| --- | ---: |
| 肘部法选择的聚类数 | 3 |
| Normal market risk regime | 77.5% |
| Market correction regime | 18.7% |
| Bear market regime | 3.8% |

## R2 · p9 · Exhibit 8 · Accuracy Rate of Stacking Classification Mode

| 指标 | 数值 |
| --- | ---: |
| Accuracy (cross-validation five folds) | 71% |
| Precision | 0.753 |
| Recall | 0.721 |

来源：Authors’ calculations based on data from FRED database and Factset。

## R3 · p9 · Exhibit 9 · Feature Importance of Selected Variables

| 特征 | Feature Importance |
| --- | ---: |
| Equity Valuation | 19.7% |
| Financial Turbulence | 26.9% |
| Financial Conditions | 34.1% |
| Monetary Policy Expectation | 19.3% |

来源：Authors’ calculations based on data from FRED database and Factset。

## R4 · p10 · Exhibit 10 · Cross Correlation throughout the Entire Sample Period

原表为下三角矩阵；上三角空白以 `n/a` 登记。

| 行/列 | Value | Growth | Momentum | Low Vol | Quality | Small |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Value | 1 | n/a | n/a | n/a | n/a | n/a |
| Growth | 0.66 | 1 | n/a | n/a | n/a | n/a |
| Momentum | 0.68 | 0.93 | 1 | n/a | n/a | n/a |
| Low Vol | 0.76 | 0.70 | 0.71 | 1 | n/a | n/a |
| Quality | 0.85 | 0.86 | 0.83 | 0.87 | 1 | n/a |
| Small | 0.86 | 0.76 | 0.77 | 0.64 | 0.80 | 1 |

来源：Authors’ calculations based on data from FRED database and Factset。

## R5 · p10 · Exhibit 11 · Cross Correlation throughout Each Market Risk Regime（Normal Risk）

原表为下三角矩阵；上三角空白以 `n/a` 登记。

| 行/列 | Value | Growth | Momentum | Low Vol | Quality | Small |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Value | 1 | n/a | n/a | n/a | n/a | n/a |
| Growth | 0.46 | 1 | n/a | n/a | n/a | n/a |
| Momentum | 0.46 | 0.89 | 1 | n/a | n/a | n/a |
| Low Vol | 0.63 | 0.56 | 0.55 | 1 | n/a | n/a |
| Quality | 0.73 | 0.79 | 0.75 | 0.80 | 1 | n/a |
| Small | 0.77 | 0.63 | 0.64 | 0.43 | 0.66 | 1 |

来源：Authors’ calculations based on data from FRED database and Factset。

## R6 · p10 · Exhibit 11 · Cross Correlation throughout Each Market Risk Regime（Correction）

原表为下三角矩阵；上三角空白以 `n/a` 登记。

| 行/列 | Value | Growth | Momentum | Low Vol | Quality | Small |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Value | 1 | n/a | n/a | n/a | n/a | n/a |
| Growth | 0.54 | 1 | n/a | n/a | n/a | n/a |
| Momentum | 0.61 | 0.86 | 1 | n/a | n/a | n/a |
| Low Vol | 0.76 | 0.57 | 0.60 | 1 | n/a | n/a |
| Quality | 0.86 | 0.70 | 0.68 | 0.88 | 1 | n/a |
| Small | 0.88 | 0.64 | 0.69 | 0.67 | 0.81 | 1 |

来源：Authors’ calculations based on data from FRED database and Factset。

## R7 · p10 · Exhibit 12 · Historical Frequency Counting on Outperforming

| 因子 | 胜出频率 |
| --- | ---: |
| Value | 19.9% |
| Growth | 15.9% |
| Momentum | 14.4% |
| Low Volatility | 21.3% |
| Quality | 4.0% |
| Small Size | 24.5% |

来源：Authors’ calculations based on data from FRED database and Factset。

## R8 · p11 · Exhibit 14 · Feature Importance within Each Market Risk Regime

| 特征 | Normal Risk Regime | Market Correction Regime |
| --- | ---: | ---: |
| Equity Valuation | 36.4% | 42.5% |
| Financial Turbulence | 12.4% | 13.1% |
| Inflation | 16.3% | 17.9% |
| Financial Conditions | 22.4% | 15.3% |
| Monetary Policy Expectations | 9.3% | 9.9% |
| GDP Growth | 3.2% | 1.3% |

来源：Authors’ calculations based on data from FRED database and Factset。

## R9 · p12 · Exhibit 15 · Business Cycle Strategy

| 因子 | Expansion | Slowdown | Contraction | Recovery |
| --- | --- | --- | --- | --- |
| Value | n/a | – | n/a | + |
| Growth | n/a | – | + | – |
| Momentum | + | + | n/a | n/a |
| Low Volatility | n/a | + | – | – |
| Quality | n/a | + | – | n/a |
| Small-Cap | – | – | + | + |

原表空白保持为 `n/a`；正负方向原样登记。

## R10 · p13 · Exhibit 17 · Compound Return with Different Approaches

| 方法 | Annualized Return | Annualized Volatility | Sharpe Ratio | Annualized Excess Return | Annualized Tracking Error | Information Ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Russell 1000 | 8.40% | 15.49% | 0.52 | n/a | n/a | n/a |
| Equal Weighted | 8.63% | 15.19% | 0.54 | 0.18% | 2.40% | 0.07 |
| Business Cycle Tilt | 9.84% | 16.06% | 0.59 | 1.50% | 3.95% | 0.36 |
| ML Approach | 11.47% | 16.81% | 0.66 | 2.89% | 6.68% | 0.45 |

来源：Authors’ calculations based on data from FRED database and Factset。

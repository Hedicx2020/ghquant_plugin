=== SPEC_CODEX_BEGIN ===
独立盲提取清单

D 类
D1（p2,p10,p27,p54）：Chen–Zimmermann/OpenAP 212 个特征的美股股票—月面板。
D2（p10）：观察单元为 stock-month。
D3（p10,p27,p54）：逐信号统一方向，使较高值对应较高预期收益；总计正向 132、负向 80。
D4（p10-p11,p27,p54）：固定八家族映射：Valuation 36、Continuation 27、Correction 4、Profitability/quality 27、Investment/issuance 46、Safety/downside 26、Liquidity/limits 21、Expectations 25。
D5（p11,p53,p101）：23 个宏观条件变量，分为 Inflation、Growth、Rates、Credit、Liquidity、Risk、Trend、Valuation 八块。
D6（p11,p53,p55,p101）：外部宏观序列来自 FRED/ALFRED，按实时或 conservative-vintage 口径处理。
D7（p11,p53,p101）：面板衍生状态包括 market volatility proxy、cross-sectional dispersion、aggregate valuation、aggregate liquidity，以及 prior-return-state variables。
D8（p12,p29,p33,p60,p68,p72）：Fama–French 五因子加 momentum 的月度收益，用于 alpha。
D9（p18-p19,p35-p36,p77-p78,p84-p86）：市值、行业、beta、流动性代理及 EW/VW 权重数据，用于横截面控制和容量区域划分。
D10（p10,p102-p103）：212 个信号的 publication year 元数据；预测年 Y 可用条件为 publication year≤Y−1。

F 类
F1（p10）：全部特征先统一预期收益方向。
F2（p10-p11,p27,p54）：将 212 信号固定映射到八个经济异常家族，映射不按样本外表现重分组。
F3（p11,p28,p53,p56-p57）：23 个宏观变量组成八个可解释状态块，并形成宏观状态历史。
F4（p12-p13）：Macro-regime memory 使用历史家族收益、家族 IC 和宏观状态历史估计家族状态条件收益。
F5（p12-p13）：主规则 mixture of experts，结合状态依赖家族信息和验证表现配置资本。
F6（p12-p13）：validation ensemble 对通过验证的强配置规则取平均。
F7（p13,p28,p61）：比较规则包括 Bayesian dynamic、Ensemble、Macro ridge、Macro analog、Attention memory、Factor momentum、Regime probability、Trailing Sharpe/IC/return、EWMA sleeve performance、Contextual bandit、Equal weight。
F8（p12-p13）：家族权重非负且跨八家族合计为 1；主版本为 nonnegative softmax，附录另报 long-short l1。
F9（p13-p14,p16,p31,p67-p69）：层级 212 信号层把家族权重施加到各家族全部底层信号。
F10（p14,p16-p17,p32,p38,p71）：pooled all-212 ridge 直接做股票层下一月收益排序，是主要股票层基准。
F11（p14,p16-p17,p32）：ridge plus macro residual 在 pooled ridge 后加入状态依赖残差信息。
F12（p12,p16）：月度横截面 IC 衡量股票排序能力。
F13（p12,p33,p70,p72）：Fama–MacBeth 月度横截面斜率及其受控 t 值。
F14（p12,p29,p33,p60,p68,p72）：按信号形成十分位多空组合，同时报告 EW、VW 和 FF5+momentum alpha。
F15（p17-p20,p34-p36,p75-p86,p104）：Liquidity/limits × Trend 为主机制；比较高低趋势状态，并沿市值容量区域检验衰减。
F16（p102-p103）：发表年份可用信号口径为预测年 Y 之前至少一年已发表。

B 类
B1（p2,p11,p27,p52）：特征历史起点 1963。
B2（p2,p11,p27,p52）：首个样本外预测年 1985。
B3（p2,p11,p27,p52）：首次训练期 1963–1972，共 10 年。
B4（p2,p11,p27,p52）：首次验证期 1973–1984；验证窗口固定为 12 年。
B5（p2,p11,p27,p52）：按年滚动；训练期扩展，验证期向前滚动且长度固定。
B6（p2,p11,p27,p52）：样本外区间 1985-01 至 2024-11，共 479 个月；2024 年含 11 个月。
B7（p12,p55）：特征、收益历史和宏观状态必须在预测期收益实现前可用。
B8（p13）：候选配置规则先在前一验证窗口选择，再冻结用于下一预测年。
B9（p15,p29）：月度时间序列 Newey–West 推断；具体滞后阶数未披露。
B10（p29）：多空列使用十分位组合。
B11（p29,p33）：alpha 控制 FF5+momentum。
B12（p12,p29,p35-p36）：同时报告 equal-weight 和 value-weight 多空收益。
B13（p7,p19,p36,p84）：容量区域为 All firms、Micro bottom 20、Outside microcaps、Middle 60、Upper half、Upper third、Large top 20、Mega top 10。
B14（p19,p39,p91）：机制形成期 1985–2004，确认期 2005 onward；确认期沿用形成期确定的符号方向。
B15（p17,p104）：逐一剔除 1987 crash、LTCM/Russia 1998、dot-com 2000–2002、GFC 2007–2009、2011 eurozone/debt-ceiling、Q4 2018、COVID 2020、reopening 2021、2022 inflation/rate shock。

R 类关键数值
R1（p28，月度百分比）：Mixture of experts 2.13、NW t=9.21、Sharpe=1.51、Concentration=0.77；Bayesian dynamic 2.05、8.98、1.44、0.71；Validation ensemble 2.08、9.09、1.43、0.75。
R2（p29，月度百分比）：Mixture of experts mean=2.13、NW t=9.21、Sharpe=1.51、EW L-S=2.51、EW t=9.71、VW L-S=1.39、alpha=2.07、alpha t=7.63、max drawdown=-22.71；Validation ensemble mean=2.08、NW t=9.09；Equal weight mean=0.38、NW t=5.81。
R3（p30）：Mixture-of-experts 平均权重为 Continuation 60.74%、Valuation 17.44%、Profitability/quality 14.40%、Liquidity/limits 3.64%、Expectations 1.98%、Safety/downside 0.93%、Correction 0.60%、Investment/issuance 0.27%；Trend corr. 与 Valuation corr. 两列整表为空，应记 n/a。
R4（p16,p31）：Mixture-of-experts hierarchical mean IC 精确值 0.0508；相对 static 212 的 incremental IC=0.0197、t=6.25；EW L-S=2.40%/月；factor alpha=1.89%/月、t=7.63。主表显示为 0.05、0.02 的两位小数。
R5（p16-p17,p32）：Pooled all-212 ridge mean IC=0.0725、IC t=15.93；ridge plus macro residual mean IC=0.0727、IC t=15.63，相对 pooled ridge 增量 0.0002、增量 t=0.21。主表四舍五入为 0.07 和 0.00。
R6（p33）：Pooled ridge controlled FMB t=12.83、EW L-S=3.88%、VW L-S=2.09%、alpha=3.44%、alpha t=14.48；hierarchical validation ensemble FMB t=3.08、EW=2.29%、VW=1.40%、alpha=1.68%、t=5.92；family-allocation mixture of experts FMB t=10.59、EW=2.51%、VW=1.39%、alpha=2.07%、t=7.63。
R7（p34,p76）：Trend × Liquidity/limits：high=-1.79%、low=1.41%、high-low=-3.20%、return t=-6.77、IC spread=-0.06、IC t=-7.14。Valuation × Continuation high-low=-3.09%、t=-4.76；Trend × Safety/downside high-low=+2.39%、t=3.50。
R8（p35,p77）：另一套 across-universe 构造采用 low-high 符号；All firms=3.13%、t=7.41、high=-2.23%、low=0.89%；Outside microcaps=1.71%、t=4.58；Industry neutral=2.76%、t=7.06；Beta neutral=3.00%、t=7.24；Large stocks=-0.18%、t=-0.53。各主行 high/low months=248/248。
R9（p36,p84）：容量前沿 low-high：All firms EW=3.13%、t=7.41，VW=2.74%、t=6.16，IC=0.07、t=8.32；Outside microcaps 1.71%、4.58，1.46%、3.73，0.05、6.69；Middle 60 1.42%、3.67，1.14%、3.02，0.04、4.90；Large top 20 为 -0.18%、-0.53，-0.52%、-1.29，-0.00、-0.11；Mega top 10 为 -0.58%、-1.57，-0.93%、-2.09，-0.02、-1.54。
R10（p37,p88-p92）：Macro shuffle minus full macro（Ensemble）=-0.36%、t=-1.53；Drop Trend block minus full macro（Ensemble）=-0.08%、t=-1.23；实际 Liquidity/limits × Trend=-3.13%、actual t=-7.41；calendar-month estimate=+0.43%，comparison mean/max absolute t=1.10/1.10。
R11（p38,p94-p95）：Pooled ridge mean IC=0.07、IC t=15.93、FMB t=12.83、alpha t=14.48；ridge plus macro residual IC t=15.63、incremental t=0.21、alpha t=14.22；SGD elastic net mean IC=0.06、incremental IC=-0.01、t=-4.25；neural benchmark mean IC=0.05、incremental IC=-0.02、t=-5.15。
R12（p39,p91）：按 predicted direction，Liquidity/limits × Trend 形成期收益=4.26%、t=5.69、80/80 月；确认期=1.86%、t=3.11、62/107 月。IA.27 原始 high-low 符号分别为 -4.26% 和 -1.86%。Continuation × Valuation 形成期=0.05%、t=0.05、80/80 月；确认期=0.00%、t=0.00、223/2 月。
R13（p41）：Continuation only 保留权重 60.74%、收益 1.96%、NW t=7.06；Continuation+Valuation 78.18%、2.08%、9.24；再加 Profitability 92.58%、2.12%、9.11；全八家族 100%、2.13%、9.21。
R14（p55）：所有列示系列 timing violations=0；CPIAUCSL 为 vintage months 743、nonmissing 743、real-time 629、conservative 114；INDPRO 为 743/743/743/0；BAA10Y 为 743/466/0/743；VIXCLS 为 743/419/0/743。
R15（p59）：Mixture of experts future-return slope=0.01、return t=4.24、future-IC slope=0.02、IC t=4.23、family-months=3832；Bayesian dynamic 的 t=4.17/3.94；Equal weight 各斜率与 t 为 0。
R16（p60）：Mixture of experts EW=2.51%、t=9.71，VW=1.39%、t=5.36，alpha=2.07%、t=7.63，turnover=0.61；Validation ensemble turnover=0.61；Trailing Sharpe turnover=0.37。
R17（p61）：Nonnegative-softmax mixture mean=2.13%、NW t=9.21、Sharpe=1.51、drawdown=-22.71%、concentration=0.77；Equal weight=0.38%、5.81、0.94、-13.25%、0.12；long-short-l1 mixture=1.44%、10.23、1.57、-18.87%、0.18。
R18（p62）：Continuation 权重 min/P25/median/P75/max=0/12.80/80.08/98.33/100%；Valuation=0/0.02/0.87/19.45/99.94%；Liquidity/limits=0/0/0/0.07/99.98%。
R19（p65）：Table IA.11 报告家族内信号构成；Continuation 27 个、average IC=0.01、average IC t=5.98、max signal t=13.63；Valuation 36 个、0.01、4.26、12.58；Liquidity/limits 21 个、-0.00、-1.76、5.80。
R20（p67-p68）：IA.12/IA.13 层级 212 结果中 mixture mean IC=0.05、IC t=11.02、incremental IC=0.02、t=6.25；EW L-S=2.40%、EW t=8.84、VW=1.46%、VW t=4.46、alpha=1.89%、alpha t=7.63、months=479。
R21（p70）：IA.14 配置规则股票层 IC/FMB：mixture mean IC=0.05、IC t=11.46、incremental IC=0.02、incremental t=6.10、FMB slope=0.03、FMB t=8.56、months=479；validation ensemble IC t=11.52、FMB t=9.48。
R22（p71-p72）：IA.15/IA.16 股票层 horse race 与受控结果：pooled ridge EW L-S=3.88%、alpha=3.44%、alpha t=14.48；family-balanced ridge IC t=16.32 但相对 pooled incremental t=-2.32；neural benchmark EW=2.83%、alpha=2.42%、alpha t=10.41。
R23（p75-p76）：完整 8×8 状态—家族收益面共 64 个单元；除主机制外，Credit×Correction=-2.27%、t=-3.94；Inflation×Profitability/quality=+1.82%、t=3.15；Valuation×Expectations=-2.32%、t=-5.12。
R24（p77-p78）：机制跨控制和年代：Non-crisis low-high=3.28%、t=8.03；Crisis=3.27%、t=2.45；1990s=4.46%、t=4.21；2020s=2.15%、t=1.49。
R25（p79-p80）：逐家族剔除中，Mixture 删除 Continuation 后收益 1.49%、贡献 0.64%、贡献 t=3.05；删除 Liquidity/limits 后收益 2.09%、贡献 0.04%、t=1.28；删除 Valuation 后收益 2.08%、贡献 0.05%、t=0.46。
R26（p82）：状态局部可靠性中 Valuation-low/static-212 mean IC=0.05、IC t=11.10、incremental IC=-0.05、t=-11.06；Trend-low/static mean IC=0.04、incremental IC=-0.04、t=-7.76；Valuation-low/neural mean IC=0.07、incremental IC=-0.03、t=-4.62。
R27（p102）：已发表信号覆盖：1985 年 9 个（4.25%）；2005 年 85 个（40.09%）；2010 年 165 个（77.83%）；2020 与 2024 年均 212 个（100%）。
R28（p104）：逐事件剔除采用 high-low 符号；全月=-3.20%、Welch t=-6.77；剔除 1987=-3.15%、-6.69；剔除 GFC=-3.18%、-6.50；剔除 2022 shock=-3.27%、-6.84。

SA 类
SA1（p28,p61）：比较 nonnegative-softmax 和 long-short-l1 配置规则及完整规则集合。
SA2（p30,p43,p62-p64）：年度权重热图、均值、分位数、最大值和箱线图检验权重时变性。
SA3（p41,p79-p81）：保留家族组合并逐月重新归一化，以及逐家族剔除贡献。
SA4（p34,p46,p75-p76）：八宏观块×八家族完整 high-low 收益和 IC 面。
SA5（p35,p47,p77-p78）：Raw all firms、Ex micro、Large stocks、Liquid proxy、Industry neutral、Beta neutral 横截面构造。
SA6（p77-p78）：All months、Non-crisis、Crisis 及 1960s—2020s 分年代比较。
SA7（p36,p48-p49,p84-p86）：八容量区域的 EW、VW、IC 数值、t 值和滚动时序。
SA8（p39,p91）：1985–2004 形成方向、2005 onward 确认。
SA9（p37,p88,p92-p93）：Macro shuffle、Random macro、Calendar dummy/month、Circular shift、Family-label relabeling。
SA10（p37,p89）：逐一删除 Inflation、Growth、Rates、Credit、Liquidity、Risk、Valuation、Trend 宏观块。
SA11（p55,p90）：实时信息违规审计、market-beta residualized sleeves、orthogonalized sleeves、extra-lag 比较。
SA12（p38,p45,p71-p73,p94-p97）：ridge、decay ridge、family-balanced ridge、SGD、neural、hierarchical 模型类别基准。
SA13（p102-p103）：按 publication year 审计预测年可用信号数。
SA14（p104）：九个具名市场事件逐一剔除。

图表编号登记
主文表：Table 1（p27）、2（p28）、3（p29）、4（p30）、5（p31）、6（p32）、7（p33）、8（p34）、9（p35）、10（p36）、11（p37）、12（p38）、13（p39）、14（p40）、15（p41）。
主文图：Figure 1（p42）、2（p43）、3（p44）、4（p45）、5（p46）、6（p47）、7（p48）、8（p49）。
附录表：IA.1（p52）、IA.2（p53）、IA.3（p54）、IA.4（p55）、IA.5（p56）、IA.6（p59）、IA.7（p60）、IA.8（p61）、IA.9（p62）、IA.10（p63，只有 Family 表头，表体为空）、IA.11（p65）、IA.12（p67）、IA.13（p68）、IA.14（p70）、IA.15（p71）、IA.16（p72）、IA.17A（p75）、IA.17B（p76）、IA.18（p77）、IA.19（p78）、IA.20A（p79）、IA.20B（p80）、IA.21（p82）、IA.22（p84）、IA.23（p85）、IA.24（p88）、IA.25（p89）、IA.26（p90）、IA.27（p91）、IA.28（p92）、IA.29（p94）、IA.30（p95）、IA.31（p99）、IA.32（p101）、IA.34（p102）、IA.33（p104）。
附录图：Figure IA.1（p57）、IA.2（p64）、IA.3（p69）、IA.4（p73）、IA.5（p81）、IA.6（p83）、IA.7（p86）、IA.8（p93）、IA.9（p96）、IA.10（p97）、IA.11（p103）。

页码原文真实性抽查
D：p10 “The panel contains 212 characteristics”；p10 “The unit of observation is the stock-month.”；p11 “The empirical package contains 23 macro series.”
F：p12 “The main allocation rule is a mixture-of-experts design.”；p12-p13 “The allocation weights are constrained to be nonnegative and to sum to one.”；p14 “The stock-level benchmark layer uses a pooled all-212 ridge”。
B：p2 “The sample starts in 1963.”；p2 “a fixed 12-year validation window”；p29 “Newey–West inference is monthly.”
R：p16 “mean hierarchical IC of 0.0508”；p16 “mean IC of 0.0725”；p39 “Table 13: Holdout and Mechanism Persistence Evidence”；p104 “Table IA.33. Liquidity/Limits Trend Reversal by Episode Exclusion”。
SA：p61 “evaluated on the same prediction sample”；p91 “the sign learned in the formation period”；p92 “shifted, calendar, and relabeled alternatives”。以上抽查均可在所引页面定位。
=== SPEC_CODEX_END ===
{
  "checkpoint": "spec",
  "verdict": "pass_with_issues",
  "dimensions_checked": [
    {
      "dimension": "盲提取diff",
      "result": "CDX-S-01, CDX-S-02"
    },
    {
      "dimension": "遗漏检查",
      "result": "CDX-S-01, CDX-S-02"
    },
    {
      "dimension": "R表逐格核对",
      "result": "CDX-S-01, CDX-S-02"
    },
    {
      "dimension": "编号完整性独立重算",
      "result": "no_findings"
    },
    {
      "dimension": "页码真实性抽查",
      "result": "no_findings"
    }
  ],
  "findings": [
    {
      "id": "CDX-S-01",
      "severity": "major",
      "category": "遗漏",
      "location": "spec.md 页面覆盖表与图表登记清单的 p65、p68、p70、p71；coverage_matrix.md R19-R22",
      "description": "四张附录数值结果表未获得与其内容相符的 R 要素：p65 Table IA.11 被关联到 R19，但 R19 实际是 p75-p76 的状态—家族收益面；p68 Table IA.13 被关联到 R20，但 R20 实际是 p77 的机制控制；p70 Table IA.14 被关联到 R21，但 R21 实际是 p80 的逐家族剔除；p71 Table IA.15 被关联到 R22，但 R22 实际是 p82 的局部状态可靠性。因而 IA.11 的家族内 IC、IA.13 的 EW/VW t 与月份、IA.14 的配置规则股票层 IC/FMB、IA.15 的完整 horse-race 数值没有被对应 R 表登记，coverage_matrix 也只登记了无关页面。",
      "suggestion": "为 IA.11、IA.13、IA.14、IA.15 分别新增或扩展内容匹配的 R 要素，并同步修正页面覆盖表、图表登记关联和 coverage_matrix 页码；至少登记各表关键行的数值、单位、符号与月份。",
      "confidence": "high"
    },
    {
      "id": "CDX-S-02",
      "severity": "major",
      "category": "遗漏",
      "location": "spec.md R12；原文 p39 Table 13 与 p91 Table IA.27",
      "description": "R12 的数值表漏掉 Continuation × Valuation 的 formation-period 行。原表明确给出 formation period 1985–2004、Pred. ret.=0.05%、t=0.05、High months=80、Low months=80；R12 只登记该通道的 confirmation-period 行以及 Liquidity/limits 两行，导致四行表缺一行，也缺少比较通道形成期基准。",
      "suggestion": "在 R12 补入 Continuation × Valuation formation-period 行，并注明主表 predicted-direction 为 +0.05%、IA.27 原始 high-minus-low 同样为 +0.05%。",
      "confidence": "high"
    }
  ]
}

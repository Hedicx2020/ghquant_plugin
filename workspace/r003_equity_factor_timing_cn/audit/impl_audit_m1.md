# m1 第2轮修复后最终独立代码复审

- 审计模式: code
- 案例: `r003_equity_factor_timing_cn`
- milestone: `m1`
- 复审轮次: round 2
- 重点: CA-A03、CA-A12；回归检查CA-A01、CA-A04—CA-A11
- 输入: 当前代码、AS36/AS37、`audit/m1_fix_round2.md`、当前 `verify_report.md`
- 独立性: 未采信修复记录或验证报告中的通过声明；全部关键结论由当前代码和真实Parquet重新执行得到。当前verify_report只记录至第1轮失败，本审计不把它作为第2轮通过证据

## 一、最终结论

CA-A03与CA-A12均已修复，CA-A01及CA-A04—CA-A11未发生回归。m1当前实现能够生成132个月六因子底座；严格84月金融湍流从2022-02开始有效，核心OOS 2023-04至2025-12为33/33个月有效；OOS个股PB覆盖最低98.37%，33/33个月通过70%且不少于100只门槛并形成全部六因子。

AS36与AS37属于中国市场迁移的显著数据假设，后续结果报告必须继续披露，但实现忠实、时点安全且证据链完整，不再构成m1代码门禁阻断。

## 二、CA-A03独立复核：2Y插值与真实84月湍流

### 2.1 插值约束

- 原始表固定 `curve_code=10`、`yield_type=到期`，主期限仍为1Y/2Y/10Y。
- 仅2Y原始月末水平缺失、且同一信号月份的1Y和3Y均存在时插值；1Y、10Y不插值。
- 35个2Y月末水平使用 `(1Y+3Y)/2` 横截面插值；因2Y月收益涉及本月和上月，36个月收益被正确标记 `is_interpolated_2y`。
- 审计者用原始曲线重新构造同月1Y/2Y/3Y/10Y月末水平，复算2Y收益与实现输出的最大绝对差为0。
- 35个插值月全部满足：原始2Y确实缺失；1Y/3Y来源与目标属于同一月份；两者来源日均不晚于信号日。
- 代码及AST未发现对国债期限的 `ffill`、`bfill`、backfill或跨月替代；仅使用相邻期限的当月横截面。
- 插值2Y审计记录中 `available_date > signal_date` 为0。

### 2.2 真实覆盖与湍流

- 132个信号月中三期限收益共同非空131个月，最长连续有效段131个月。
- 使用真实全市场前复权价格、30个中信一级行业、修复后国债代理独立运行：行业收益共3,960行，覆盖132个月×30行业。
- 严格过去84月湍流首个非空月为2022-02-28，恰在具备84个历史月后出现。
- 全样本湍流非空47个月；2023-04至2025-12 OOS为33/33个月非空；最大历史月数为84。

结论：CA-A03 resolved。AS36所述“同月1Y/3Y曲线插值、无时间填充”与实现及真实数据一致。

## 三、CA-A12独立复核：PIT派生PB、覆盖门槛与六因子

### 3.1 派生口径与时点

- `reported_pb`仅接受正的已报告PB。
- 缺失时严格按 `signal_date` 当日总市值除以最近一条可得的正股东权益生成 `derived_pb`。
- 股东权益来自资产负债表 `total_shareholder_equity`，通过 backward as-of按 `equity_available_date=info_publ_date` 匹配；未使用 `end_date` 直接对齐。
- 全量当前代码运行中，OOS入选成分的 `equity_available_date > signal_date` 为0，`financial_available_date > signal_date` 为0。
- 市值和股东权益量纲抽查与已报告PB同阶，未发现单位数量级错误。

### 3.2 覆盖门槛

- 配置门槛为PB可用数不少于100只且覆盖当期中证800成分不少于70%，两个条件同时满足才允许Value/Growth进入候选。
- 合成800股边界复算：559只PB可用时Value/Growth均不生成；560只可用时门槛生效并各选186只，证明70%边界真实执行。
- 每月 `data_quality` 留存 members、pb_available、pb_coverage、reported/derived数量、pb_eligible、Value/Growth选择数、factor_count和six_factor_complete。

### 3.3 全量与OOS实测

- 全量正式入口独立运行：`monthly_features=(132,39)`、`factor_returns=(792,10)`、`factor_constituents=(512295,16)`；792=132×6，132个月均形成六因子。
- OOS 33个月全部通过门槛，PB覆盖最低98.37%，最高100%；PB可用数最低786只。
- 2023-04为788/799，覆盖98.62%，其中reported 20、derived 768；2025-12为797/799，覆盖99.75%，全部reported。
- OOS因子收益共198个“月-因子”组，198=33×6；每月因子数均为6。

结论：CA-A12 resolved。原始PB低覆盖不再导致静默缩样，派生PB、门槛和逐月证据均与AS37一致。

## 四、此前修复回归检查

| issue | 状态 | 回归证据 |
| --- | --- | --- |
| CA-A01 | no_regression | 全日历132/132严格满足 `signal < execution < return`，零持有期为0 |
| CA-A04 | no_regression | `financial_risk`仍含信用利差、期限利差、10Y收益率和中证800252日波动率 |
| CA-A05 | no_regression | SHIBOR观测日PIT、LPR回退未变；OOS短端利率33/33有值 |
| CA-A06 | no_regression | EP/PB扩展历史分位仍仅使用当月及此前数据 |
| CA-A07 | no_regression | 三月回撤仍使用过去三个日历月全部日度收盘峰值 |
| CA-A08 | no_regression | Momentum仍在2014年起完整月末历史上计算12-1后再截取样本 |
| CA-A09 | no_regression | 未执行/入口缺价/退出缺价仍保留原权重并按现金0收益，不重归一 |
| CA-A10 | no_regression | Quality仍为五项各20%，只在当月中证800截面标准化 |
| CA-A11 | no_regression | 衍生字段PIT审计仍存在，非空记录无可得日晚于信号日 |

## 五、m1 coverage done行最终核对

| 要素 | 实现位置 | 最终结论 |
| --- | --- | --- |
| D1-D4 | found | 中国CPI/GDP/周期代理及PIT证据完整 |
| D5-D9 | found | 风险、信用、杠杆、短端利率、政策预期代理与当前假设一致 |
| D10-D11 | found | 000906估值分位、日度三月回撤真实实现 |
| D12 | found | 中信37静态映射按AS30披露 |
| D13 | found | 1Y/2Y/10Y主期限真实；AS36插值有逐月留痕 |
| D14 | found | 132个月六因子完整，PIT派生PB按AS37执行 |
| F6 | found | 严格过去84月；真实首月2022-02，OOS 33/33 |
| F11-F12 | found | PB低/高1/3且受70%/100只门槛保护 |
| F13-F16 | found | Momentum、LowVol、Quality、Small-Cap定义未回归 |
| B1 | found | 2015-01至2025-12共132个月，月度底座完整 |
| B2 | found | 过去三个月日度峰值回撤 |
| B10 | found | 五风格因子用历史000906，Small-Cap正式路径用全A |

不存在空壳、pass/TODO或实现位置失真。

## 六、issue清单

本轮未发现新的critical、major或minor issue。CA-A03、CA-A12均关闭。

## 七、五维度结论

| 维度 | 结论 | 说明 |
| --- | --- | --- |
| 公式一致 | pass | 84月湍流、六因子分组、T+1、PIT派生PB均按已登记口径实现 |
| 参数一致 | pass | 84月、1Y/3Y插2Y、70%/100只、252日、分位最少12月等一致 |
| 实现位置真实 | pass | m1全部done位置存在且非空壳 |
| 代码反查 | pass | 全量入口、真实国债/行业、OOS PB与六因子均独立运行通过 |
| 简化声明 | pass | AS30-AS37覆盖静态行业、SHIBOR、现金、波动率、估值分位、曲线插值与派生PB |

## 八、已检查维度清单

- [x] CA-A03、CA-A12逐项复审
- [x] CA-A01、CA-A04—CA-A11回归检查
- [x] 2Y插值严格同月curve10 1Y/3Y、原始2Y缺失、来源日不晚于信号日
- [x] 国债无ffill/bfill/跨月填充，插值收益与原始曲线独立复算
- [x] 真实全市场30行业、84月湍流首月与OOS 33/33
- [x] 派生PB公式、市场价值日期、`info_publ_date <= signal_date`
- [x] PB门槛边界、OOS逐月覆盖及data_quality留痕
- [x] 全量132个月与OOS33个月六因子完整
- [x] m1全部done行公式、参数、位置、代码反查、简化声明

verdict: pass

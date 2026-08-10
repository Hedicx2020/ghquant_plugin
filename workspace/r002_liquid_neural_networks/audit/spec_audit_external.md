Phase 2 cross-check complete. I've verified: the blind-extraction diff (my independent list is fully subsumed by the spec — no systematic omission), all seven R-elements cell-by-cell against the page-13/14/18 prose (all numbers correct), the figure/table numbering sets (FIG1-24, TBL1-10 — complete, max matches), and 10 page citations (all truthful, no hallucination). The spec is high quality. One minor inconsistency surfaced in the figure registry.

Below are the two required deliverables: the Phase-1 blind-extraction block (for slicing into `spec_codex.md`) and the Phase-2 verdict JSON.

---

一句话结论：**spec.md 质量很高——D/F/B/R/SA 五类全覆盖，7 张 R 结果数值逐格无误，页码引用无幻觉，图/表编号集合完整；仅 1 条 minor（图表登记中 FIG3 题名与正文唯一的"图3"引用相矛盾）。判定 pass_with_issues，不阻断。**

```
=== SPEC_CODEX_BEGIN ===
（盲提取，仅依据 report_text.md + tables_extracted.md；注：本 PDF 为搜狐网页转制，正文有效内容在 p2-p18，p1/p19/p20 及各页两侧为新闻/广告噪声；结果表 表6-10 与 图15-24 均为空白图片，tables_extracted.md 36 张"表"全为网页版式噪声、无任何结果表，故结果数值只能取自 p14 正文散文）

— D 数据要求 —
个股日频价量特征 | D | p5 | 开盘价/最高价/最低价/收盘价/成交量/成交金额；x_t=单交易日特征向量
回看窗口 | D | p5 | T 个交易日序列 X=[x_1..x_T]，取最后时间步隐藏状态
选股范围-全市场 | D | p13 | 全市场
选股处理-过滤 | D | p13 | 剔除非上市/摘牌/ST/*ST/涨跌停板/上市未满1年
训练区间 | D | p13 | 2008-01~2016-12 全市场
验证区间 | D | p13 | 2017-02~2019-11（与训练间隔1月防暴露）
回测区间 | D | p13 | 2020-01~2024-12（与验证间隔1月防暴露）
未来收益率标签 | D | p5 | FFN 降维结果拟合未来收益率标签（口径未披露）

— F 因子/策略定义 —
神经常微分方程定义 | F | p3,p18 | h_{t+1}=f(h_t,θ_t)+h_t；dh_t/dt=f(h(t),t,θ)；伴随灵敏度法
主干网络对比框架 | F | p2,p13 | 固定输入/目标函数/非主干结构，仅替换 backbone
RNN 通式/GRU 基准 | F | p5,p13 | h_t=f(x_t,h_{t-1},θ_1)；y_t=g(h_t,θ_2)；GRU 为基准
LTC 液态时间常数网络 | F | p6-p7 | 微分方程 τ/θ/A 参数；半隐式欧拉求解器；梯度反传更新
NCP(LTC) 神经电路策略 | F | p7-p9 | 线虫四层稀疏结构（感觉/中间/命令/运动）；每神经元=1个LTC隐状态
CFC 闭式连续时间网络 | F | p11-p12 | LTC 微分方程闭式近似解 + 门控优化；f/g/h 三网络共享主干
NCP(CFC) | F | p13 | 五模型之一，正文仅列名
模型预测因子排序方向 | F | p13 | 预测因子值从大到小分10档

— B 回测设置 —
分档 | B | p13 | 按当期预测因子值从大到小分10档
回测路径 | B | p13 | 多路径回测均值（路径数/种子未给）
调仓周期 | B | p13 | 每20个交易日
交易执行 | B | p13 | t日预测，t+1日均价买入，t+1+n日均价卖出
交易费用 | B | p13 | 千分之三（卖出收取），展示值均为计费后
评价指标 | B | p13-p14 | RankIC、分组年化收益率、夏普比率、分年度收益、多头/多空

— R 核心数值结果 —
显存依赖 | R | p13,p18 | GRU120Gb；LTC/NCP(LTC)≈80Gb；CFC/NCP(CFC)≈6Gb（=GRU的5%）
因子相关系数区间 | R | p13,p18 | 0.69~0.82（逐模型矩阵为空白图，无数值）
多头2020~2024 | R | p14 | 年化 GRU24.21/LTC22.21/NCP(LTC)24.38/CFC23.23/NCP(CFC)23.65 %；夏普 0.88/0.87/0.95/0.93/0.91
多头2024 | R | p14 | 年化 13.43/9.53/13.50/10.05/11.36 %；夏普 0.28/0.20/0.30/0.21/0.24
多空2020~2024 | R | p14 | 年化 65.57/58.89/62.41/60.80/62.69 %；夏普 5.22/5.66/5.26/5.53/5.50
多空2024 | R | p14 | 年化 51.50/39.36/46.60/42.64/41.25 %；夏普 2.58/2.48/2.82/2.69/2.23
整体表现表(RankIC/分组年化) | R | p13 | 仅定性"未拉开明显差异"，表为空白图片、无数值
LTC文献性能提升(reference) | R | p7 | 时间序列任务 5%~70% 提升
ODE-Net vs ResNet MNIST(reference) | R | p4 | 同等测试误差下参数量/计算消耗更小（表为空白图）

— SA 敏感性/稳健性 —
2024子样本对比 | SA | p14,p18 | 单列2024与全区间并列（多头/多空、年化/夏普）
因子相关性分析 | SA | p13 | 五模型两两相关 0.69~0.82，结论"学到不一样价量特征"
分年度表现统计 | SA | p14-p17,p18 | 表6-10/图分年度，结论"NCP结构通常更好"（表为空白图）
说明：全文无参数敏感性扫描（无回看窗口/费率/档数等 sweep）

— 图表编号（独立重算）—
正文明确出现图号：3(显存,p2)、5(NCP四层,p8)、6(简单RNN,p7)、7(NCP vs LTC,p8)、9/10(NCP自驾误差,p9)、11(闭式解模拟,p11)、12(CFC示意,p11)、15-24(结果,p14)；最大图号=24；未显式点名但连续存在：1/2/4/8/13/14
正文明确出现表号：6/7/8/9/10(p14)；最大表号=10；另有未编号表：ODE-Net对比(p4)、整体表现(p13)、相关性(p13)、LTC时序(p7)
=== SPEC_CODEX_END ===
```

```json
{
  "checkpoint": "spec",
  "verdict": "pass_with_issues",
  "dimensions_checked": [
    {"dimension": "盲提取diff", "result": "no_findings（阶段一独立列出的 D/F/B/R/SA 全部要素均被 spec.md 登记；spec.md 反而更细粒度拆分 B1-B12，无系统性遗漏）"},
    {"dimension": "遗漏检查", "result": "no_findings（正文所有数据说明/模型定义/回测参数/结果数值/分年度稳健性均已登记；文献背景图表以 reference_only 归档）"},
    {"dimension": "R表逐格核对", "result": "no_findings（R1-R7 全部数值与 p13/p14/p18 正文散文逐格一致，含正负号/百分号/小数位；tables_extracted.md 无任何结果表——36张均为网页版式噪声——故核对基准为 report_text.md 正文，R3 相关矩阵与 TBL4/5/6 逐格标 n/a 系原图为空白、判定正确，非抄录不完整）"},
    {"dimension": "编号完整性独立重算", "result": "CDX-S-01（编号集合 FIG1-24/TBL1-10 完整、fig_max=24/tbl_max=10 与独立重算一致、无缺口；唯 FIG3 登记题名与正文唯一"图3"引用相矛盾）"},
    {"dimension": "页码真实性抽查", "result": "no_findings（抽查 D1/D2/D5/F2/F4/B9/R2/R4/R6/F1 共10条，含 R 类4条，登记页码与原文摘录均真实存在于对应页，无幻觉引用）"}
  ],
  "findings": [
    {
      "id": "CDX-S-01",
      "severity": "minor",
      "category": "图表登记-题名错配",
      "location": "spec.md 第六节 FIG3（登记题名"LTC隐藏神经元/时间常数示意"，p6，reference_only）; 原文 report_text.md p2",
      "description": "spec.md 将 FIG3 登记为"LTC隐藏神经元/时间常数示意"，但全文中唯一以编号出现的"图3"在 p2 明确为显存对比图——原文 p2："仅为GRU所需显存的5%（如右图3所示）"。spec.md 的 FIG1-FIG4 采用"按出现位置顺序编号"（FIG1=p4、FIG2=p5、FIG3=p6、FIG4=p7），与研报正文实际"图3=显存图"的编号不一致（FIG5-FIG24 反而与正文图5-图24吻合）。因图片均为空白占位、物理归属无法确证，且 FIG3 为 reference_only、显存数据已由 R2 完整捕获，不影响复现，仅为登记题名的事实性错配。",
      "suggestion": "将 FIG3 题名修正为"显存/计算资源对比图（图3）"并对齐 p2 引用，或在第六节表头注明 FIG1-FIG4 系空白占位下的位置推断、其编号未必对应正文图1-图4；据此复核 FIG1/FIG2/FIG4 的题名与页码归属。",
      "confidence": "medium"
    }
  ]
}
```

**补充说明（供主会话记账，不计入意见数）**：本次为 codex 外审降级路径下由我（Claude）执行的等价审查。核心结论——该 spec 的 7 张结果基准（R4-R7 四组多头/多空年化与夏普、R2 显存、R3 相关系数区间、R1 文献提升）数值全部正确，是后续 verify 阶段比对的可靠锚点；数据/模型/回测设置无遗漏；唯一 finding 为 minor 且非阻断。**不需要打回 extract 重做，可放行至 plan/implement。**

<!-- 以下为编排器对上方外审 finding 的机器可读索引；不改变外审原文与裁决。 -->

| ID | severity | 摘要 |
| --- | --- | --- |
| CDX-S-01 | minor | FIG3 题名与页码错配，已按 p2 原文修正并复核通过。 |

VERDICT: pass_with_issues

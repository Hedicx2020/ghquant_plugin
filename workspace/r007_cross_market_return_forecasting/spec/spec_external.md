=== SPEC_CODEX_BEGIN ===
要素名 | 类别 | 页码 | 关键参数/数值
研究主题：有向二分图跨市场（中美）个股收益预测 | D | p.1 | 摘要；利用中美交易时段不重叠的时间序结构
关键词/JEL | D | p.2 | Return prediction, cross-market, ML, bipartite graphs; JEL G17, G15, C58
预测目标：次日 OPCL（开盘到收盘）收益 | D | p.3 | 十个 ML 模型预测 next-session OPCL
事前声明：结果为交易成本前、非可实施 alpha | B | p.3, p.20-21 | pre-transaction-cost，无流动性优化权重
美股市场范围 NYSE/Nasdaq；A股 SSE/SZSE | D | p.8 | 全球最大市值市场
数据源：美股 CRSP，A股 Wind | D | p.8 | 日频数据
样本区间 2014–2021 | D | p.8 | 全样本
pvCLCL 对数收益定义 式（1) | F | p.8 | R=log(p_cl^(t)/p_cl^(t-1))
OPCL 对数收益定义 式（2) | F | p.9 | R=log(p_cl^(t)/p_op^(t))
市场超额收益 式（3)(4) | F | p.9 | r = R_stock − R_ETF（pvCLCL 与 OPCL 两版）；美股 ETF=SPY，A股 ETF=513500.SH
股票池：每国平均市值最高 500 只 | D | p.9 | 全样本平均市值选股
脚注3：股票池用全样本市值，存在机械性前视 | SA | p.9 | 作者自认 look-ahead 成分，主结论（方向不对称）不受影响
缩尾：训练样本内每只股票 0.5%/99.5% 分位 | D | p.9 | winsorization 仅作用于 training-sample returns
二分图定义 G=(V,E)、biadjacency 矩阵 B | F | p.10 | 源市场 X→目标市场 Y 有向边
训练窗向量定义 x（源，t−l−w…t−l−1) 与 y（目标，t−w…t−1) | F | p.10 | 交易日历而非自然日历；滞后参数 l 体现时段不重叠
配对单变量回归 t 统计量筛选 式（5) | F | p.11 | t_β=β/(se/√Σ(x−x̄)²)；β=cov/var；se=√(SSE/(w−2))
筛选性质声明：边际筛选为稀疏化启发式，非多重检验校正 | SA | p.11-12 | 引 Fan&Lv(2008)、Harvey et al.(2015)
Figure 1 二分图示意 | R | p.11 | 参考性示意图
Figure 2 示例：CDNS(pvCLCL) vs 002410.XSHE(OPCL)，三日平滑 | R | p.12 | l=1, w=250
阈值 τ=2，|t_β|>τ 选边 | F | p.12 | 约对应常规显著性水平
Figure 3 双邻接矩阵热图（2021-10-21) | R | p.13 | 每行业取≤25只代表股，可视化含美股254只、A股235只；跨行业连接非块对角
Figure 4 行业级热图：时均矩阵各行业块 |t| 中位数 | R | p.14 | 例：中国金融服务行业与美国公用事业行业强链接
Figure 5 目标节点入度 25/50/75 分位随时间演化 | R | p.14-15 | 双向入度随时间上升
训练/预测窗示意 Figure 6 | R | p.15-16 | 目标窗 [t−w, t−1]，源窗 [t−l−w, t−l−1]
交易时段：美 9:30–16:00 ET；中 9:30–11:30、13:00–15:00 CST(UTC+8) | D | p.15 | 夏令时调整后仍无重叠（Figure 7）
滞后设定：美→中 l=1；中→美 l=0 | F | p.15, p.21-22 | 保证源信息在目标开盘前可观测
预测模型 式（6) | F | p.15 | r_Yi^(t)=F_i(r_X1^(t−l),…,r_Xn^(t−l); θ)+ε
十个 ML 模型清单 | F | p.17-20 | OLS、LASSO、RIDGE、SVM、XGBoost、LGBM、RF、AdaBoost、ensemble-avg、ensemble-med
OLS 式（7)(8) | F | p.17 | min‖y−α1−Xw‖²；d=w 为训练窗长度
LASSO 式（9) | F | p.17-18 | min (1/2d)‖·‖²+λ‖w‖₁
RIDGE 式（10) | F | p.18 | min‖·‖²+λ‖w‖₂²
SVM 式（11) | F | p.18 | RBF 核；对偶问题，0≤α_j≤C
XGBoost 式（12)(13)(14) | F | p.18-19 | Ω(f)=γM+½λ‖w‖²
LGBM：GOSS + EFB | F | p.19 | 无显式超参在正文
RF：bootstrap + 随机特征子集 | F | p.19 | —
AdaBoost：基学习器为决策树回归器 | F | p.19 | 按绝对误差重加权
ensemble-avg/med：对前八个模型预测取均值/中位数 | F | p.19-20 | 每股每日
评价指标：PnL 与 SR | B | p.20 | 无交易成本/市场冲击建模
PnL 式（15)：Σ sign(ŝ)·r·b | B | p.20 | b_i=min(0.001×mdv_i^(21), L)；mdv=前21日成交额中位数
头寸上限 L | B | p.20 | 美股预测 L=100,000 USD；A股预测 L=1,500,000 CNY
年化 SR 式（16) | B | p.21 | (μ/σ)×√252
局限性声明（多重检验/无成本/无容量控制） | SA | p.21 | 引 Cartea et al.(2025)
实验设置：训练窗 250 日，图与模型每 10 日更新 | B | p.21 | rolling
预测区间：2016 年首个交易日至 2021 年最后交易日 | B | p.21 | 严格样本外
方向一：X=美，Y=中，l=1 | B | p.21 | —
方向二：X=中，Y=美，l=0 | B | p.22 | 中国当日收盘早于美国当日开盘
基线1 非图同市场：前 25 日收益为特征 式（17) | B | p.22 | 训练窗250日、10日更新；特征全 pvCLCL 或全 OPCL，目标 OPCL
基线2 图同市场：X=Y，l=1 | B | p.22 | 隔离跨市场信息增量
六层嵌套分位组合 | B | p.22-23 | qr1全部、qr2前80%、qr3前60%、qr4前40%、qr5前20%、qr6前10%（按|预测收益|）
排序仅用当日预测值，不用已实现收益 | B | p.23 | 避免组合构建前视
Figure 8：美pvCLCL/美OPCL→中OPCL 的 SR | R | p.23 | RIDGE/LGBM/ensemble-avg/ensemble-med 强；SVM 多数 SR<1；其余多数分位 SR>1、部分接近 2；pvCLCL 特征优于 OPCL
Figure 10：美pvCLCL→中OPCL 累计 PnL | R | p.23-25 | 各模型各分位上行
Figure 9：中→美OPCL 的 SR | R | p.24 | 各方法各分位 SR 明显更低（方向不对称核心证据）
Figure 11：中→中（图）SR | R | p.24, p.26 | —
Figure 12：三类设定 SR 对比（pvCLCL 特征） | R | p.24, p.26 | 图同市场>非图基线（多数模型/分位，尤其 OLS、LGBM、qr5）
Figure 13：相对非图基线的 SR 差值 | R | p.24, p.27 | 跨市场+图组合最强
敏感性1 特征替换：随机替换 20/40/60/80/100% 边 | SA | p.27 | 保持各目标节点入度不变；仅从未连接节点中选替代；按分位取10法中位数
Figure 14a：替换比例↑→SR↓ | R | p.27-28 | qr6 韧性最强；中低分位退化最明显
敏感性2 时间滞后：l=2,3,… | SA | p.28 | 按分位取10法中位数
Figure 14b：l↑→SR↓；Lag 4 后轻微企稳 | R | p.28 | 解释为周交易周期效应
结论：方向不对称+图结构与时效性均关键 | R | p.28-29 | 美pvCLCL→中OPCL 最强
Appendix A 超参敏感性（Table A.1，p.36） | SA | p.35-36 | LASSO/RIDGE λ={1e-4,1e-3,1e-2,1e-1,1,10,100,1000}；SVM C={0.1,1,10,100,1000}；XGBoost max_depth={3,6,9}、lr={0.01,0.1,0.2}、n_est={50,100,300}；LGBM num_leaves={10,31,90}、lr、n_est 同上；RF n_est={50,100,300}、max_depth={5,10,50}；AdaBoost max_depth={1,5,10}、n_est={50,100,300}、lr={0.01,0.1,0.2}
Table A.1 数值（mean±std, qr1–qr6) | R | p.36 | LASSO 0.848/0.969/1.238/1.65/1.821/1.777；RIDGE 1.238/1.293/1.437/1.715/1.668/1.55；SVM 0.743/0.751/0.782/0.719/1.02/0.836；XGBoost 1.445/1.48/1.587/1.539/1.381/0.964；LGBM 1.32/1.457/1.541/1.44/1.652/1.424；RF 1.481/1.558/1.639/1.799/1.747/1.09；AdaBoost 1.389/1.405/1.549/1.548/1.1/0.667
Table A.1 定性：SVM 各配置 SR 多<1；其余模型多数>1 | R | p.35 | 对超参不敏感
Appendix B：OPCL 作预测因子的基线对比 | SA | p.35, p.37 | Figure B.1、B.2；图结构普遍有增益，但跨市场信息增量较 pvCLCL 设定明显弱
Appendix C：SPY 大幅波动日条件分析 | SA | p.35, p.38 | 按 |SPY pvCLCL| 分嵌套分位 qr1–qr6（qr2=前80%天数）；取冲击日 t_i 次日 t_i+1 的中国 OPCL 预测算 SR
Figure C.1：非线性集成（XGB/LGBM/RF/AdaBoost）在 qr4–qr6 高 SR | R | p.38 | OLS 在 qr6 最高；LASSO/SVM 部分分位为负；RIDGE 不稳
Appendix D：分行业 SR | SA | p.38-39 | Figure D.1；科技与必需消费（consumer defensive）行业 SR 较高；行业股票数不同需谨慎解读
Appendix E：预测集含美中两国股票→中国 | SA | p.39-40 | Figure E.1 四面板（pvCLCL/OPCL×两国组合）；部分设定 SR 超过仅用美股（对比 Figure 8）
图表编号独立统计（正文） | — | p.11-28 | Figure 1–14 共 14 幅（Fig8/9/11/14 含 a/b 子图）
图表编号独立统计（附录） | — | p.36-40 | Table A.1 ×1；Figure B.1、B.2、C.1、D.1、E.1 共 5 幅（E.1 含 a–d 子图）
表格提取备注 | — | — | tables_extracted.md 显示"未检测到表格"，Table A.1 仅以正文文本形式存在于 p.36
=== SPEC_CODEX_END ===

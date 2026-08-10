---
report_name: style_factor_subdomain
spec_version: 1
row_count: 45
---

| 要素ID | 类别 | 描述(短) | 页码 | 优先级 | milestone | 状态 | 状态理由 | 实现位置 | 验证结果 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| D1 | D | Barra十风格因子(特征/分域) | p4 | core | | pending | | | | extract |
| D2 | D | 约220特征因子(含~70分钟因子) | p11 | core | | pending | | | | extract |
| D3 | D | 未来收益率标签(月度/未来10日) | p13 | core | | pending | | | | extract |
| D4 | D | 个股行情收益率与流通市值 | p6 | support | | pending | | | | extract |
| D5 | D | 月度无风险利率 | p5 | support | | pending | | | | extract |
| D6 | D | 三指数成分股与权重 | p9 | core | | pending | | | | extract |
| D7 | D | 中信一级行业分类 | p10 | support | | pending | | | | extract |
| D8 | D | 交易状态标记(不在市/ST/涨跌停) | p13 | support | | pending | | | | extract |
| F1 | F | 面板树全局分裂准则(Sharpe²) | p4 | core | | pending | | | | extract |
| F2 | F | 叶内股票权重公式(市值加权) | p6 | core | | pending | | | | extract |
| F3 | F | 叶子权重公式(均值-方差最优) | p6 | core | | pending | | | | extract |
| F4 | F | 股票权重公式(单棵树) | p6 | core | | pending | | | | extract |
| F5 | F | 面板树生长过程Step1-3 | p5 | core | | pending | | | | extract |
| F6 | F | 面板树超参数(表2) | p5 | core | | pending | | | | extract |
| F7 | F | 面板树特征预处理[0,1]缩放 | p5 | support | | pending | | | | extract |
| F8 | F | 面板树标签预处理(超额+截尾) | p5 | support | | pending | | | | extract |
| F9 | F | 面板树滚动训练设定 | p4 | core | | pending | | | | extract |
| F10 | F | XGB分域训练三步骤 | p12 | core | | pending | | | | extract |
| F11 | F | XGB特征预处理(稳健ZScore/85%) | p11 | support | | pending | | | | extract |
| F12 | F | XGB对抗训练(市值/流动性/特波) | p12 | support | | pending | | | | extract |
| F13 | F | domainXGB因子定义 | p13 | core | | pending | | | | extract |
| F14 | F | 面板树改造-代表域 | p14 | core | | pending | | | | extract |
| F15 | F | repDomainXGB因子定义 | p17 | core | | pending | | | | extract |
| B1 | B | 单因子回测设定 | p13 | core | | pending | | | | extract |
| B2 | B | 指数增强通用设定 | p22 | core | | pending | | | | extract |
| B3 | B | 指数增强三池差异化约束 | p22 | core | | pending | | | | extract |
| R1 | R | 表1三指数增强超额汇总 | p2 | core | | pending | | | | extract |
| R2 | R | 表5基础面板树组合表现 | p9 | support | | pending | | | | extract |
| R3 | R | 表6基础分域Rank IC | p13 | core | | pending | | | | extract |
| R4 | R | 表7面板树改造前后表现 | p17 | support | | pending | | | | extract |
| R5 | R | 表8改造分域Rank IC | p20 | core | | pending | | | | extract |
| R6 | R | 表9沪深300增强-近期 | p23 | core | | pending | | | | extract |
| R7 | R | 表10沪深300增强分年度-长期 | p25 | core | | pending | | | | extract |
| R8 | R | 表11中证500增强-近期 | p26 | core | | pending | | | | extract |
| R9 | R | 表12中证500增强分年度-长期 | p28 | core | | pending | | | | extract |
| R10 | R | 表13中证1000增强-近期 | p28 | core | | pending | | | | extract |
| R11 | R | 表14中证1000增强分年度-长期 | p30 | core | | pending | | | | extract |
| R12 | R | 图20因子间相关性矩阵 | p22 | support | | pending | | | | extract |
| R13 | R | 图10/18分位数组合L-S夏普 | p14 | support | | pending | | | | extract |
| SA1 | SA | 分域vs成分股分组差异 | p9 | support | | pending | | | | extract |
| SA2 | SA | 分域vs行业分域差异 | p10 | support | | pending | | | | extract |
| SA3 | SA | 改造参与股票数/正负平衡 | p16 | support | | pending | | | | extract |
| SA4 | SA | 代表域特征重要性差异 | p18 | support | | pending | | | | extract |
| SA5 | SA | 三因子与风格因子相关性 | p21 | support | | pending | | | | extract |
| SA6 | SA | 增强策略风格暴露 | p24 | support | | pending | | | | extract |

## 变更日志（只追加，禁止修改/删除历史行）

| 时间 | 事件 | 来源 | 说明 |
| --- | --- | --- | --- |
| 2026-07-11 extract | 初始化 45 行 | quant-extractor | 首次提取建矩阵（D8/F15/B3/R13/SA6） |

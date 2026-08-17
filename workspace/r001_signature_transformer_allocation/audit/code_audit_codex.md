{
  "checkpoint": "code",
  "verdict": "fail",
  "dimensions_checked": [
    {
      "dimension": "公式逐要素对照",
      "result": "CDX-C-08"
    },
    {
      "dimension": "未来函数/前视检查",
      "result": "CDX-C-01"
    },
    {
      "dimension": "数据对齐检查",
      "result": "CDX-C-03,CDX-C-05"
    },
    {
      "dimension": "config vs B类核对",
      "result": "CDX-C-05,CDX-C-06,CDX-C-07,CDX-C-08"
    },
    {
      "dimension": "作弊模式排查(K1/K5/K6)",
      "result": "CDX-C-02,CDX-C-04,CDX-C-05"
    }
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "critical",
      "category": "未来函数",
      "location": "src/r001_signature_transformer_allocation/main.py:92",
      "description": "监督集仅按决策日所属 split 过滤，随后 realized_forward_returns 从全局调仓日历取得未来 K=12 期且不检查标签终点是否仍在该 split（signatures.py:327-337）。因此训练期尾部样本使用验证期收益，验证期尾部样本使用测试期收益；后者参与 early stopping、网格选优和 DLinear 验证，测试集未被封存。",
      "suggestion": "标签构造必须接收 split_end，仅保留第 K 个未来锚点不晚于 split_end 的样本；训练集和验证集尾部应分别 purge K 个决策点并增加边界断言。"
    },
    {
      "id": "CDX-C-02",
      "severity": "critical",
      "category": "硬编码",
      "location": "src/r001_signature_transformer_allocation/main.py:48",
      "description": "R4 原文结果被硬编码为 R4_ANCHOR_CSI300_50，命中给定 R 类字面量，包括 1.9373、2.3399、1.2804、1.1695、1.6717 等。该字典位于正常运行可达路径，不是注释：既被打印和导出，又在 main.py:308 参与“实测 Sharpe−原文锚”的计算，符合本次 K1 判据。",
      "suggestion": "将原文基准移出 src 计算模块，放入独立验证基准文件；正式回测只生成实测结果，由 verify/result-audit 阶段读取基准并比较。"
    },
    {
      "id": "CDX-C-03",
      "severity": "major",
      "category": "ST/停牌时点错误",
      "location": "src/r001_signature_transformer_allocation/backtest.py:48",
      "description": "ST 和停牌状态只在固定股票池锚点选样时检查一次。测试期 tradable_mask_at 仅判断 close.notna 及 first_date/last_date，从未查询调仓日的 ST、停牌表；仍有非空价格的 ST 或停牌股票会被误判为可交易。assumptions.md 未登记放弃持有期动态 ST/停牌过滤。",
      "suggestion": "在每个实际执行日使用点时 ST 与停牌状态构造可交易掩码，不能以价格非空替代状态数据。"
    },
    {
      "id": "CDX-C-04",
      "severity": "major",
      "category": "静默吞错",
      "location": "src/r001_signature_transformer_allocation/baselines.py:129",
      "description": "min_cvar_weights 捕获 linprog 的 ValueError/LinAlgError 后无日志直接返回等权；res.success=False 时同样静默回退。该核心函数同时服务传统 CVaR 和 DLinear 第二阶段，求解失败会把两个基线悄然伪装成 EW。",
      "suggestion": "记录异常、求解状态、日期和 universe；正式运行应抛错或显式标记 fallback，不得静默输出等权结果。"
    },
    {
      "id": "CDX-C-05",
      "severity": "major",
      "category": "范围缩水",
      "location": "src/r001_signature_transformer_allocation/main.py:196",
      "description": "权重只从 test 区间内的月末开始生成，而公共回测引擎只使用严格晚于信号月末的下一期收益。代码没有 2019-12 的预热权重承接 2020-01 收益，最后一个测试信号也因无后续月末收益被丢弃；实际约为 2020-02 至 2024-11 的 58 期，而非声明的 2020-01-01 至 2024-12-27。该缩水未在 assumptions.md 登记。",
      "suggestion": "从测试期前一个月末生成首个纯推断权重，并按 test_start/test_end 裁剪收益实现日；对非月末 test_end 增加终端结算规则和首末日期断言。"
    },
    {
      "id": "CDX-C-06",
      "severity": "major",
      "category": "参数不符",
      "location": "src/r001_signature_transformer_allocation/main.py:129",
      "description": "AS6 要求主表温度 τ 从 {0.8,1.0,1.2,1.3,1.4} 由验证集选优，但 select_hyperparams 只搜索 d_model、d_ff 和 n_heads。训练及最终测试均未传入选中的 τ，实际固定使用 config.sit_tau=1.0。",
      "suggestion": "将 τ 纳入验证搜索，保存选中值，并在最终多种子训练及测试权重生成中一致使用。"
    },
    {
      "id": "CDX-C-07",
      "severity": "major",
      "category": "种子聚合不符",
      "location": "src/r001_signature_transformer_allocation/main.py:188",
      "description": "代码虽然训练三个种子，却按最小验证损失挑选单个 best seed，只对该模型回测并报告单点指标；DLinear 也仅运行 seed 0。此行为违反 AS5“固定3个随机种子、报告mean±std”，并引入 seed 层面的择优偏差。",
      "suggestion": "每个种子独立完成测试回测，对四项指标聚合 mean±std；随机种子不得作为验证集择优超参，DLinear 也应采用同一聚合口径。"
    },
    {
      "id": "CDX-C-08",
      "severity": "major",
      "category": "指标公式错误",
      "location": "src/r001_signature_transformer_allocation/backtest.py:247",
      "description": "传给 calculate_max_drawdown 的 NAV 首条已经包含首期收益，但 common/utils.py:239 直接从该首条开始计算 cummax，未把初始财富1纳入峰值。若首期下跌10%后持平，NAV=[0.9,0.9]，代码会得到 MDD=0，而正确值为10%，会系统性漏计期初回撤。",
      "suggestion": "计算回撤时显式加入初始净值1，或保证 running peak 的初值至少为1。"
    }
  ]
}
{
  "checkpoint": "code",
  "verdict": "fail",
  "dimensions_checked": [
    {
      "dimension": "公式逐要素对照",
      "result": "no_findings"
    },
    {
      "dimension": "未来函数/前视检查",
      "result": "no_findings"
    },
    {
      "dimension": "数据对齐检查",
      "result": "CDX-C-01"
    },
    {
      "dimension": "config vs B类核对",
      "result": "CDX-C-01"
    },
    {
      "dimension": "作弊模式排查(K1/K5/K6)",
      "result": "CDX-C-02"
    }
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "major",
      "category": "股票池时点不符",
      "location": "src/ssrn_6115073/data_prep.py:508",
      "description": "prepare_market 分别生成 member_mask 与 tradeable_mask，但未将二者合并；后续 portfolio.py:427-463 仅使用 md.tradeable_mask 建仓。因此，训练期曾入选候选集、但调仓月已经调出对应指数的股票，仍可能进入组合。代码与 B1 的时点指数成分股要求及 assumptions.md AS56 所称“建仓前过滤非成分股”不一致，且该偏差没有被登记。",
      "suggestion": "构造最终可建仓掩码时使用 member_mask & tradeable_mask，或在所有建仓入口同时传入并检查调仓月的 member_mask；并覆盖内部模型、HRP/HERC/NCO 和 OLMAR 路径。"
    },
    {
      "id": "CDX-C-02",
      "severity": "major",
      "category": "静默吞错",
      "location": "src/ssrn_6115073/data_prep.py:436",
      "description": "F12 核心因子筛选用裸 except Exception 捕获所有异常后直接返回 degraded_all，既不记录异常也不区分预期的依赖缺失与 BorutaShap 运行错误。算法接口、输入数据或实现错误都会被静默伪装成已登记的依赖退化，命中 K5 核心路径。",
      "suggestion": "仅对明确的 ImportError 或 ModuleNotFoundError执行已登记的依赖降级；其他异常至少记录堆栈并重新抛出，或把异常类型与信息写入可审计状态后中止。"
    }
  ]
}
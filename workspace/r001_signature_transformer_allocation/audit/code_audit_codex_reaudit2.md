{
  "checkpoint": "code",
  "verdict": "fail",
  "reaudit": [
    {
      "id": "CDX-C-01",
      "status": "partial",
      "note": "src/r001_signature_transformer_allocation/main.py:76 已将 split_end/next_split_start 改为必填；main.py:255-258、strategy.py:130-133、ablation.py:152-155 的 6 个调用均传入正确边界，实测 val 保留 24 条且最大标签终点为 2019-12-31 < test_start。仍有旁路：signatures.py:313-318,326-330,339-340 保留 split_end=None 默认且明确不做过滤，直接调用可生成终点至 2020-12-31 的验证标签；main.py:94-95 未拒绝 None/NaT，main.py:118-123 又仅靠可被 python -O 移除的 assert，优化模式下显式传 None 实测保留全部 36 条并越界至 2020-12-31。"
    },
    {
      "id": "CDX-C-04",
      "status": "resolved",
      "note": "src/r001_signature_transformer_allocation/main.py:332-345 对传统基线及 DLinear 均传 log_fn=log；backtest.py:240-244,260-265 原样透传至 min_cvar_weights；baselines.py:68-78 的 fallback 同时告警并调用日志回调，baselines.py:112-160 的非法输入、求解异常、求解失败及退化解均进入该路径。"
    },
    {
      "id": "CDX-C-05",
      "status": "partial",
      "note": "主管线已修复：main.py:287-298 加入 2019-12-31 预热并传 terminal_date=test_end，backtest.py:117-150 追加终端锚；实测得到准确 60 期，首末为 2020-01-23/2024-12-27。但 strategy.py:180,203-207 与 ablation.py:156-157 仍使用纯 test 信号且不传 terminal_date，实测仍为 58 期、2020-02-28 至 2024-11-29；main.py:197-213,319-328 的宽松断言也允许该旧 58 期结果通过。"
    },
    {
      "id": "CDX-C-07",
      "status": "resolved",
      "note": "src/r001_signature_transformer_allocation/config.py:70 定义完整档 seeds=(0,1,2)；main.py:282-285 按 cfg.seeds 分别训练 DLinear，main.py:341-349 逐种子预测、生成权重并回测，main.py:185-194,350-353 聚合并记录 mean±std；baselines.py:231-254 确实将 seed 用于模型初始化及批次随机序列。"
    }
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "critical",
      "category": "未来函数/边界泄漏",
      "location": "src/r001_signature_transformer_allocation/signatures.py:317,330,339; src/r001_signature_transformer_allocation/main.py:94-95,118-123",
      "description": "当前仓内训练调用虽然均正确传界，但底层标签 API 仍保留默认无边界路径；监督集入口也未显式拒绝 None/NaT，最终保护依赖可被优化模式移除的 assert，因此“无 None/default/直接绕过”尚未闭环。",
      "suggestion": "将 realized_forward_returns.split_end 改为必填并显式拒绝 None/NaT；build_supervised_set 对两个边界及其顺序做强制校验，并用 ValueError/RuntimeError 替代边界 assert。"
    },
    {
      "id": "CDX-C-05",
      "severity": "major",
      "category": "范围缩水/覆盖断言不完整",
      "location": "src/r001_signature_transformer_allocation/strategy.py:180,203-207; src/r001_signature_transformer_allocation/ablation.py:156-157; src/r001_signature_transformer_allocation/main.py:197-213,319-328",
      "description": "主管线已达到 60 期，但公开 SITStrategy 组件路径和消融路径仍复现旧的 58 期缩水；主管线断言只检查首末月附近及 60±3，无法拦截原缺陷。",
      "suggestion": "抽取并复用统一的测试决策日、预热日和终端锚构造函数；所有回测入口强制使用同一覆盖口径，并显式要求 n_periods==60、首日==2020-01-23、末日==test_end，避免使用可被 -O 移除的 assert。"
    }
  ]
}
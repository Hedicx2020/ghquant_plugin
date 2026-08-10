{
  "checkpoint": "code",
  "verdict": "fail",
  "reaudit": [
    {
      "id": "CDX-C-01",
      "status": "partial",
      "note": "主管线已闭环：main.py:97、113-118 与 signatures.py:332-340 实施 split_end 过滤/断言，main.py:245-248 传入 train_end/val_end；实测 val 由36降至24、purge 12个，最大标签终点2019-12-31 < test_start。仍未全闭环：strategy.py:125-126 的公开 SITStrategy.fit 未传 split_end，命中 main.py:76、85 的 None 非 purge 路径，val 最后标签终点可到2020-12-31。"
    },
    {
      "id": "CDX-C-02",
      "status": "resolved",
      "note": "R4 字面量仅见 benchmarks.py:22-28；实测 perf 由 main.py:287-309 生成，锚值只在 main.py:341-344 打印对照及 main.py:408-411 导出对照/偏差列。对 R4 全部数值扫描未发现 benchmarks.py 之外的 src 命中。"
    },
    {
      "id": "CDX-C-03",
      "status": "resolved",
      "note": "backtest.py:49-67 加载并缓存 ST/停牌表，backtest.py:70-93 以传入调仓日合并价格有效性、ST 与 if_suspend；SIT/基线分别在 backtest.py:181-184、213-215 调用。ST 半开区间与停牌日期字段由 common/data_loader.py:240-260、410-434 实现。"
    },
    {
      "id": "CDX-C-04",
      "status": "partial",
      "note": "baselines.py:68-78 已统一 RuntimeWarning、可选 log_fn 与显式 EW fallback，baselines.py:112-160 的空输入、异常、求解失败及退化解均进入该路径；但 baseline_weight_panel 的 log_fn 默认 None（backtest.py:191-200），主管线 main.py:301-306 未传 log_fn=log，动态失败会 warning+EW，却不会进入主管线日志回调。"
    },
    {
      "id": "CDX-C-05",
      "status": "partial",
      "note": "main.py:192-205 只在裁剪后检查界内，不能补缺期且末端无覆盖断言；main.py:276-290 只生成 test 内信号并在 main.py:277 未向 backtest.py:117-150 传 terminal_date。当前实际仍为58期、2020-02-28至2024-11-29，现有断言照常通过，而目标应为60期、2020-01-23至2024-12-27。"
    },
    {
      "id": "CDX-C-06",
      "status": "resolved",
      "note": "main.py:161-177 逐 tau 仅以 train/val 的 best_val 选优；main.py:260-267 将 best_tau 写回 cfg 并用于最终多种子训练，main.py:288-290 又以同一 cfg.sit_tau 生成各 seed 测试权重；tau 确实经 train.py:256-264 与 model.py:291-300 进入训练/验证 softmax。"
    },
    {
      "id": "CDX-C-07",
      "status": "partial",
      "note": "SIT 已由 train.py:283-306 独立训练各 seed，并在 main.py:266-294 逐 seed 生成面板、回测、指标后由 main.py:180-189 聚合 mean/std；但 DLinear 仍在 main.py:273 只训练 cfg.seeds[0]，main.py:301-309 仅回测一次并作单元素聚合，未满足 assumptions.md:56-64 的每配置3种子口径。"
    },
    {
      "id": "CDX-C-08",
      "status": "resolved",
      "note": "common/utils.py:230-250 以 nav.cummax().clip(lower=1.0) 纳入期初财富，backtest.py:292-298 将回测 NAV 传入该函数；边界验证 nav=[0.9,0.9] 得 MDD=0.10，先涨后跌及全正序列也与显式前置1.0公式一致。"
    }
  ],
  "findings": [
    {
      "id": "CDX-C-01",
      "severity": "critical",
      "category": "未来函数",
      "location": "src/r001_signature_transformer_allocation/strategy.py:125",
      "description": "run_pipeline 的 train/val 已做 split purge，但公开 SITStrategy.fit 仍以 split_end=None 构造两段监督集；验证集尾部 K=12 标签继续使用 2020 测试期收益并进入 early stopping，关键泄漏未在全部计算入口闭环。",
      "suggestion": "取消训练入口的 split_end=None 兼容路径，或至少在 SITStrategy.fit 的 train/val 调用分别强制传 cfg.train_end/cfg.val_end；对每个入口断言最大标签终点严格早于下一 split 起点。"
    },
    {
      "id": "CDX-C-04",
      "severity": "major",
      "category": "静默吞错/日志接线不完整",
      "location": "src/r001_signature_transformer_allocation/main.py:301",
      "description": "min_cvar_weights 已不再静默，能 warning 并显式回退；但主管线未把 log 回调传给 baseline_weight_panel，求解失败及 fallback 不会进入主管线运行日志，声称的 warn+log 只完成了 warn。",
      "suggestion": "调用 baseline_weight_panel 时传 log_fn=log，并把 fallback 的日期、基线、原因和次数写入结果/运行日志，避免仅依赖可被过滤的 RuntimeWarning。"
    },
    {
      "id": "CDX-C-05",
      "severity": "major",
      "category": "范围缩水",
      "location": "src/r001_signature_transformer_allocation/main.py:276",
      "description": "裁剪函数不能生成缺失收益期：测试权重从 2020 首个月末才开始，T+1 对齐丢失 2020-01；月度收益又未追加 test_end 终端锚，丢失 2024-12。当前仍仅58期（2020-02-28至2024-11-29），首末断言未拦截。",
      "suggestion": "加入测试前最后一个月末（2019-12-31）的纯推断预热权重，调用 build_monthly_returns(..., terminal_date=cfg.test_end)，并强断言首末实现日为2020-01-23/2024-12-27且期数为60。"
    },
    {
      "id": "CDX-C-07",
      "severity": "major",
      "category": "种子聚合不符",
      "location": "src/r001_signature_transformer_allocation/main.py:273",
      "description": "SIT 的多种子回测已修复，但随机训练的 DLinear 仍只跑 seed 0，随后按确定性单点回测并把单元素 std 置0；上一轮 finding 中 DLinear 的种子聚合部分仍未闭环。",
      "suggestion": "对 DLinear 按 cfg.seeds 逐 seed 独立训练、预测、回测并聚合四项指标 mean±std；正式导出同时保留 n_seeds 与各指标 std。"
    }
  ]
}
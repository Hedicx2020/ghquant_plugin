# result_audit 定向修复记录（round 2）

- 日期：2026-07-18
- 输入：`audit/result_fix_reaudit_round1.md`
- 修复项：RA-A02 唯一失败——`execution_exit_audit` 的 summary SHA-256 无法从交付 Excel sheet 回读复算
- 结论边界：本记录只陈述实现和 coder 定向回归，不代表独立复审已通过；正式 results 未覆盖。

## 根因

round 1 使用原始内存浮点值和17位有效数字生成哈希，但 Excel 写入/回读会改变部分等权分数的二进制浮点末位。例如 `1/266` 在内存与 Excel 回读后的17位字符串不同，导致业务内容、行数和计数完全一致时，summary 哈希仍不一致。

## 修复

`reporting.py` 新增版本化的 `execution_exit_audit_v2` canonicalization：

- `weight`、`exit_delay_days`、`exit_delay_trading_days` 在审计表写入前统一 round 12；哈希时再次按12位小数规范化并输出固定12位字符串。
- 日期字段不依赖推断 dtype，统一解析为 `YYYY-MM-DD`；空日期及其他空值统一为 `<NA>`。
- 布尔字段兼容内存 `True/False`、Excel回读布尔值及 `1/0`，统一序列化为小写 `true/false`。
- 六位纯数字股票代码兼容 Excel 默认回读为整数的情况，哈希时统一左补零至六位。
- 其他字段统一为字符串；哈希绑定 worksheet 表头列序和 `prediction_date,factor,stock_code` 行序。
- `metrics.json.execution_exit_audit.sha256_canonicalization` 将版本、数值精度、日期/布尔/空值/股票代码格式和行列顺序一并交付，便于复算。

固定精度仅作用于逐股票审计 sheet 的证据展示和哈希，不回写 m1-m4 对象，不参与模型、组合或指标计算，因此不改变策略参数及组合数值。

## 真实全市场回归

命令口径：

```bash
MPLCONFIGDIR=/private/tmp/r003-mpl-cache .venv/bin/python - <<'PY'
# 2025-09单信号月、smoke_stock_limit=None构建真实中国全市场m1
# _build_execution_exit_audit -> 临时returns_detail.xlsx
# pd.read_excel回读execution_exit_audit -> 同一_canonical_frame_sha256复算
PY
```

结果：

- 内存审计行数：4,726；
- Excel 回读行数：4,726；
- 内存/summary SHA-256：`1ecaacad9b2ac47f3da09542d725df0f1e5955df3ab0d4c05b3351389e3d7ee2`；
- Excel sheet 回读复算 SHA-256：`1ecaacad9b2ac47f3da09542d725df0f1e5955df3ab0d4c05b3351389e3d7ee2`；
- `hash_equal=true`；
- 数值规范精度：12位小数；
- 执行受限97、延迟退出58、20日窗超限3，业务计数与本次内存表一致。

另执行默认 `pd.read_excel`（不指定股票代码 dtype）的六位代码负担测试，回读 `stock_code` 被推断为 `int64`，经同一 canonicalization 左补零后哈希仍一致。

## 静态检查

```bash
python3 -m py_compile src/r003_equity_factor_timing_cn/reporting.py
```

结果：通过。真实数据运行只出现 PyArrow 受限环境无法读取 CPU cache 的 `sysctlbyname` 警告，不影响退出码和断言。

## 影响文件

- `src/r003_equity_factor_timing_cn/reporting.py`
- `workspace/r003_equity_factor_timing_cn/audit/result_fix_round2.md`

未修改正式 `output/r003_equity_factor_timing_cn/results/`、`state.json`、策略参数、组合逻辑或组合数值。

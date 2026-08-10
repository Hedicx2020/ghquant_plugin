# r007 code_audit 最终外审历史合并

你只做机械合并，不新增、不删除、不改写 findings，不读取其他文件。

读取：

- `workspace/r007_cross_market_return_forecasting/audit/code_audit_external.md`
- `workspace/r007_cross_market_return_forecasting/audit/code_audit_external_recheck_round2.md`
- `workspace/r007_cross_market_return_forecasting/audit/code_audit_external_recheck_round3.md`

输出一个 JSON：

- `checkpoint="code"`
- `verdict="pass_with_issues"`（最终复审无 open critical/major，仅历史发现和一个 minor）
- `dimensions_checked` 合并三份输入已有维度
- `findings` 恰好保留五条原始 finding，ID 为：
  - `CDX-C-01`
  - `CDX-C-R1-01`
  - `CDX-C-R2-01`
  - `CDX-C-R2-02`
  - `CDX-C-R3-01`
- 每条 finding 的 severity、category、location、description、suggestion、confidence 必须逐字取自对应输入，不得概括
- `review_chain` 列出三份输入的 checkpoint/verdict；round3 的 `closed` 数组原样放入 `final_closures`

只输出 JSON，可包裹单个 `json` fenced block。

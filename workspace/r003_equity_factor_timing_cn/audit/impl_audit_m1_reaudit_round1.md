# m1 第1轮修复复审摘要

- 模式: code reaudit
- 案例: `r003_equity_factor_timing_cn`
- 完整报告: `workspace/r003_equity_factor_timing_cn/audit/impl_audit_m1.md`

## 结论

CA-A01、CA-A04—CA-A11已通过独立代码与小样本复核；CA-A02只部分修复，CA-A03在真实数据上仍失败，并新增CA-A12。m1暂不能通过。

## 阻断项

1. `CA-A03 critical`：三期限国债虽有95个共同有效月，但最长连续仅83个月。严格84月窗口导致金融湍流全样本0个非空，2023-04至2025-12 OOS也是0/33。
2. `CA-A12 critical`：PB缺口持续到2025-02。OOS前21个月覆盖低于20%、前23个月低于80%；2023-04仅20/799只股票有PB，代码仍用约6只股票形成Value/Growth，没有最低覆盖门槛或逐月缩样审计。

## 已确认修复

- T+1日程132/132严格有效，无执行日等于结算日。
- SHIBOR真实接入并按观测日PIT；OOS短端利率33/33有值。
- 中证800波动率、EP/PB历史分位、日度三月峰值回撤已实现。
- Momentum使用样本前历史；退出缺价按现金0收益；Quality五项等权且在中证800截面标准化。
- 衍生字段PIT证据链无可得日晚于信号日。

verdict: fail

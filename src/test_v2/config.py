"""集中参数配置（test_v2：股债跷跷板效应研究及隔日反转择时策略改进）。

所有取值均可反查 spec.md / assumptions.md，禁止在其它模块出现魔法数字。
本文件承载 m1（数据/回测框架）所需参数，并前置登记 m2+ 参数（标注来源，供后续里程碑复用）。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Config:
    """test_v2 复现全局参数。字段旁注均标注 spec/assumptions 出处。"""

    # ---- 路径 ----
    data_dir: Path = Path.home() / "local_data"
    output_dir: Path = Path(__file__).resolve().parents[2] / "output" / "test_v2"

    # ---- 回测主区间（B1）----
    # 图9/表1 及改进策略系列（R1/R5/R6/R8/R9/R11/R13/R14）区间。
    main_start: str = "2015-03-24"
    main_end: str = "2023-08-02"
    # 隔日反转前作回顾（图14/表7，R7）区间起点更早（B1 原文）。m4 使用。
    reversal_start: str = "2015-03-20"
    reversal_end: str = "2023-08-02"

    # ---- 标的与信号源 ----
    hs300_code: str = "000300"                 # D2 沪深300指数 index_code
    # D1 10年期国债期货主力：contract_code 形如 T1512，且 main_contract==1。
    future_code_regex: str = r"^T\d{4}$"
    future_main_flag: float = 1.0

    # ---- F1 长短端跷跷板参数 ----
    long_window: int = 120                     # F1 长端 N_l（约6个月）
    short_window: int = 20                     # F1 短端 N_s（约1个月）
    quantile_lower: float = 1.0 / 3.0          # F1 下轨=基日以来 chg 的下 1/3 分位
    quantile_upper: float = 2.0 / 3.0          # F1 上轨=上 1/3 分位
    seesaw_base_date: str = "2004-12-31"       # F1/D2 注2：沪深300 基日（分位扩窗起点）

    # ---- F2 日度信号阈值（AS1，A2 auto 裁决）----
    daily_upper_threshold: float = 0.05        # l_upper=±5%（AS1）
    daily_lower_threshold: float = 0.03        # l_lower=±3%（AS1）

    # ---- R2/R3/R4 日度跷跷板效应统计阈值档位（spec R2/R3/R4 表头 15 档）----
    # 效应统计（非策略回测）：对每档阈值分「绝对值/正(涨)/负(跌)」三组，统计沪深300
    # 单日涨跌触发后下一交易日国债期货的胜率(R2)/赔率(R3)/平均涨跌幅(R4)+天数比例，
    # 佐证 ±5%/±3% 选值合理性（AS1 旁证）。口径重建见 AS6。
    daily_effect_thresholds: tuple[float, ...] = (
        0.0, 0.0025, 0.005, 0.0075, 0.01, 0.0125, 0.015, 0.0175,
        0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05,
    )

    # ---- F3 隔日反转因子 chg_t（AS4，A1 human 裁决；m4 使用）----
    # chg_t = settle_{T-2}/settle_{T-3} - 1；|chg_t|∈[0.03%,0.5%] 激活反转。
    reversal_lag_days: int = 2                 # AS4：T-2 日结算价涨跌幅
    reversal_min_abs: float = 0.0003           # AS4：激活下界 0.03%
    reversal_max_abs: float = 0.005            # AS4：激活上界 0.5%
    # AS3（A4 auto 裁决）：|chg_t|>2% 视同超阈值、延用跷跷板。m5+ 使用。
    seesaw_switch_upper: float = 0.02

    # ---- F5 周内效应（m7 使用）----
    calendar_weekday: int = 3                  # F5：星期四（Monday=0 → Thursday=3）
    # AS10（coder 推断，m7 F5/F8 周内信号时点对齐）：周内效应「周四国债期货偏多」偏多的是
    # 持仓/收益兑现日为周四那天。combo 决策日坐标框架下 combined[d] 经 signal_lag 兑现到下一
    # 交易日 d+1，故 True(默认口径B)=signal_calendar 在决策日 d 标记「兑现日 d+1 是否周四」
    # （is_thursday.shift(-1)，日历确定性前移非价格前视，见 AS10 防未来论证），使周四持仓偏多，
    # 与经济语义一致；False(备选口径A)=signal_calendar 标记决策日 d 自身是否周四（供 verify
    # 超差且归因周内对齐时切换重测）。
    calendar_align_to_settle_day: bool = True

    # ---- 回测口径（B1/B2）----
    periods_per_year: int = 240                # 年化交易日基准（iter_02 M2/SO-01：中国研报常用 240 交易日；T 基准探针 0.02301 精确命中研报 0.023，见 AS13）
    cost_bps: float = 0.0                      # B2 基准：以收盘价成交、不计交易费用
    signal_lag: int = 1                        # T 日信号 T+1 生效，防未来函数

    # ---- B2 成交价格与交易费用敏感性（m8：SA2/SA3/R13）----
    # spec B2（p16）：基准以收盘价成交、不计交易费用、不加杠杆；成交价敏感性档位
    # vwap_1/3/5/10（收盘前 X 分钟成交均价）依赖分钟级数据、本地无（实测 financial_future_price
    # 无任何 vwap/均价列）→ SA2/R13 vwap 档位降级不可复现（AS11），仅收盘价基准与 T 行可复现。
    reproducible_exec_prices: tuple[str, ...] = ("收盘价",)                 # R13 可复现成交价档
    missing_exec_prices: tuple[str, ...] = ("vwap_1", "vwap_3", "vwap_5", "vwap_10")  # R13 缺失档(AS11)
    # SA3 交易费用敏感性（研报仅定性"3元/手、平今仓免费、影响小"、未给对照表；coder 补充敏感性，AS12）。
    future_fee_per_lot_yuan: float = 3.0        # B2：中金所 10 年期国债期货手续费 3 元/手（单边）
    future_contract_face_value_yuan: float = 1_000_000.0  # AS12：每手面值约100万元(面值100元×合约乘数10000)
    # 单边 bp 压力倍数（× 由 3元/手÷面值 换算的单边 bp 估算值≈0.03bp；0=基准不计费、1=估算实际、10/100=压力）。
    cost_bps_stress_multiples: tuple[float, ...] = (0.0, 1.0, 10.0, 100.0)

    # ---- D3 现券指数代码（中债净价总值，B3）----
    # 代码 -> 研报名称；覆盖情况由 data_prep.load_bond_index 实测（见 AS5）。
    bond_index_codes: dict[str, str] = field(
        default_factory=lambda: {
            "CBA00102": "中债-新综合净价(总值)指数",
            "CBA00602": "中债-国债总净价(总值)指数",
            "CBA00902": "中债-银行间债券总净价(总值)指数",
            "CBA07702": "中债-1-3年国开行债券净价(总值)指数",
        }
    )

    def to_jsonable(self) -> dict[str, Any]:
        """返回 JSON 可序列化表示（路径转字符串）。"""
        data = asdict(self)
        data["data_dir"] = str(self.data_dir)
        data["output_dir"] = str(self.output_dir)
        return data


CONFIG = Config()

"""r004 中国全 A 风格箱的集中参数。

本模块集中声明 m1-m4 共用口径，不读取数据。日期、上市龄、交易成本均可反查
``workspace/r004_all_a_style_box/plan.md`` 与 ``assumptions.md``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from math import isfinite
from pathlib import Path

import pandas as pd

from common.data_loader import get_data_root


@dataclass(frozen=True)
class AllAStyleBoxConfig:
    """动态全 A 与 PIT 月度底座配置。"""

    data_root: Path = field(default_factory=get_data_root)
    security_transfer_data_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[2]
        / "workspace"
        / "r004_all_a_style_box"
        / "external_data"
        / "600466_to_400165"
    )

    # B1 / AS11 / AS24：这里的起止日指完整持有月份；信号日在持有月前一月月末。
    history_start: str = "2015-01-01"
    history_end: str = "2025-12-31"
    freeze_end: str = "2023-03-31"
    oos_start: str = "2023-04-01"
    oos_end: str = "2025-12-31"

    # plan 二、AS12：佣金与滑点买卖双边均收取；印花税仅卖出收取。
    commission_rate: float = 0.0003
    slippage_rate: float = 0.0005
    stamp_tax_before_2023_08_28: float = 0.001
    stamp_tax_from_2023_08_28: float = 0.0005
    stamp_tax_change_date: date = date(2023, 8, 28)

    # 单位净值与数值勾稽容差；不改变冻结策略参数或收益定义。
    initial_nav: float = 1.0
    weight_tolerance: float = 1.0e-10
    cash_tolerance: float = 1.0e-10
    numeric_tolerance: float = 1.0e-12

    # B10 / AS15：自上市日起按交易日历计数，满 120 个交易日方可入池。
    minimum_listing_trading_days: int = 120

    # iter_01 锁定修复：Value 核心项与中国市场证券生命周期门禁。
    minimum_core_value_components: int = 2
    dividend_max_age_trading_days: int = 5
    minimum_style_coverage: float = 0.95
    stable_style_coverage: float = 0.97
    minimum_stable_style_months: int = 24
    maximum_style_coverage_jump: float = 0.05
    minimum_box_members: int = 100
    minimum_box_share_of_eligible: float = 0.10
    maximum_single_stock_weight: float = 0.10
    maximum_top_ten_weight: float = 0.50
    maximum_unexplained_price_age_trading_days: int = 20
    maximum_zero_target_rebalances: int = 2
    # iter_03：只给600466→400165建立官方45交易日的有限转板退出链。
    # 普通证券的20日陈旧价门禁保持不变。
    security_transfer_old_code: str = "600466"
    security_transfer_new_code: str = "400165"
    security_transfer_new_name: str = "蓝光3"
    security_transfer_source_public_date: date = date(2023, 6, 5)
    security_transfer_delisting_date: date = date(2023, 6, 6)
    security_transfer_mapping_public_date: date = date(2023, 7, 26)
    security_transfer_effective_date: date = date(2023, 7, 26)
    security_transfer_ratio: float = 1.0
    security_transfer_max_wait_trading_days: int = 45
    security_transfer_old_mark: float = 0.40
    security_transfer_old_mark_date: date = date(2023, 6, 5)
    security_transfer_expected_exit_vwap: float = 0.38
    security_transfer_expected_first_volume_shares: float = 5_753_700.0
    security_transfer_market_row_count: int = 429
    security_transfer_market_start_yyyymmdd: str = "20230726"
    security_transfer_market_end_date: date = date(2026, 7, 17)
    security_transfer_price_factor: int = 100
    security_transfer_ohlc_field_count: int = 4
    security_transfer_issue_price_text: str = "0.40"
    security_transfer_market_volume_unit: str = "shares"
    security_transfer_market_amount_status: str = "unavailable"
    security_transfer_market_price_basis: str = "unadjusted"
    security_transfer_source_count: int = 3
    sha256_hex_length: int = 64
    security_transfer_manifest_filename: str = "source_manifest.json"
    security_transfer_manifest_sha256: str = (
        "926256a77dc5f882f4b592fc4874058d23feb34a9330f85ae49fc0ada08c1cbc"
    )
    security_transfer_sse_raw_filename: str = "sse_600466_delisting_20230605.pdf"
    security_transfer_neeq_raw_filename: str = "neeq_400165_company_report_20250828.pdf"
    security_transfer_market_raw_filename: str = "10jqka_400165_daily_all.js"
    security_transfer_market_parsed_filename: str = "10jqka_400165_daily_all.csv"
    security_transfer_market_source_id: str = "10jqka_400165_daily_all"
    security_transfer_market_callback: str = "quotebridge_v6_line_sb_400165_01_all"
    security_transfer_market_http_params: tuple[tuple[str, str], ...] = (
        ("market_code", "sb_400165"),
        ("period", "01"),
        ("range", "all"),
    )
    security_transfer_frozen_sha256: tuple[tuple[str, str], ...] = (
        (
            "sse_600466_delisting_20230605.pdf",
            "e9f53e9693106878aab293fe231a7385f53639b95b0eaea571c3644ee6cf7983",
        ),
        (
            "sse_delisting_facts.csv",
            "458f3b076ef1aa33f687f44d8e68da5df50ea9cce63b04c0b164329e9d9c6147",
        ),
        (
            "neeq_400165_company_report_20250828.pdf",
            "62d2177c2991dfe48ec2a734df7d3b3adb8d12b8a4890c90f41c9d79444d960d",
        ),
        (
            "neeq_successor_facts.csv",
            "40af0944e2bd7c744c529d072d1b4ee2b97f7f148ba0b51c74320b1cdce8bff5",
        ),
        (
            "10jqka_400165_daily_all.js",
            "6284dd992927823f269c5a6f11f60e9554f74199ab33996c77a249cf3e02539b",
        ),
        (
            "10jqka_400165_daily_all.csv",
            "e2517458d828009e545f8b53d1e75a0d9d4ebac4378210ee1caba6f819898eb8",
        ),
    )
    # iter_02：估值候选的固定优先级。数值越小优先级越高；行为事件本身
    # 不属于估值来源，只能作为同一唯一状态行中的审计证据保留。
    valuation_priority_observable_market: int = 10
    valuation_priority_explicit_settlement: int = 20
    valuation_priority_transfer_pending: int = 25
    valuation_priority_bounded_carry: int = 30
    valuation_priority_unpriced_asset: int = 90
    valuation_priority_behavior_evidence: int = 100
    # 证券生命周期只用明示公告日/生效日。本地 stock_name 存在静态回填，
    # 不得将其当作历史 ST/退市信号。
    security_risk_exit_events: tuple[tuple[str, str, str, str, str], ...] = tuple(
        (
            code,
            "2023-05-04",
            "2023-05-05",
            "risk_exit_on_next_trade",
            "https://www.szse.cn/disclosure/margin/business/t20230504_600265.html",
        )
        for code in (
            "000046", "000540", "000584", "000620", "000667", "000671",
            "000976", "000996", "002118", "002157",
        )
    ) + tuple(
        (
            code,
            "2023-05-04",
            "2023-05-05",
            "risk_exit_on_next_trade",
            "https://www.sse.com.cn/disclosure/magin/announcement/ssereport/c/c_20230504_5720923.shtml",
        )
        for code in ("600823", "600077", "601258", "688500")
    ) + tuple(
        (
            code,
            "2023-04-28",
            "2023-05-04",
            "risk_exit_on_next_trade",
            "https://www.sse.com.cn/disclosure/magin/announcement/ssereport/c/c_20230428_5720796.shtml",
        )
        for code in ("603559", "600466", "600543")
    ) + tuple(
        (
            code,
            "2024-04-30",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://www.sse.com.cn/disclosure/magin/announcement/ssereport/"
            "c/c_20240430_10753871.shtml",
        )
        for code in (
            "600220", "600277", "600360", "600381", "600565",
            "603377", "603959", "600213", "603363", "688282",
        )
    ) + (
        (
            "000918",
            "2023-04-28",
            "2023-05-04",
            "risk_exit_on_next_trade",
            "https://www.szse.cn/disclosure/margin/business/t20230428_600209.html;"
            "https://www.szse.cn/disclosure/notice/general/t20230728_602312.html",
        ),
        (
            "600393",
            "2023-05-22",
            "2023-05-23",
            "risk_exit_on_next_trade",
            "https://www.sse.com.cn/disclosure/announcement/listing/stock/c/c_20230522_89679795.shtml",
        ),
        (
            "002503",
            "2023-05-19",
            "2023-05-22",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/download/disc/disk03/finalpage/2023-05-19/"
            "ebf8f5bc-6359-46f2-9e3e-298da05963b7.PDF",
        ),
        (
            "600321",
            "2024-05-29",
            "2024-05-29",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-05-29/1220185726.PDF",
        ),
        (
            "000961",
            "2024-05-08",
            "2024-05-08",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/disc/disk03/finalpage/2024-05-07/"
            "ee7c7479-10ba-4d79-82a4-729eb3b31623.PDF",
        ),
        (
            "600836",
            "2024-06-15",
            "2024-06-17",
            "risk_exit_on_next_trade",
            "https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/listedinfo/"
            "announcement/c/new/2024-06-15/600836_20240615_SHY9.pdf",
        ),
        (
            "300116",
            "2024-05-15",
            "2024-05-16",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/disc/disk03/finalpage/2024-05-15/"
            "666c91a8-db95-4b13-a675-a28390ccdab4.PDF",
        ),
        (
            "002435",
            "2024-04-30",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-04-30/1219927871.PDF",
        ),
        (
            "002280",
            "2024-04-30",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-04-30/1219913916.PDF",
        ),
        (
            "002341",
            "2024-04-29",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/disc/disk03/finalpage/2024-04-29/"
            "7f8f6447-5fea-4750-997d-bb9592222dbc.PDF",
        ),
        (
            "002665",
            "2024-04-27",
            "2024-04-30",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-04-27/1219872522.PDF",
        ),
        (
            "000413",
            "2024-07-05",
            "2024-07-09",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-07-05/1220543312.PDF;"
            "https://www.szse.cn/disclosure/listed/bulletinDetail/index.html?"
            "6b3e22c5-dcaf-4e27-873a-de1a0f5c0894",
        ),
        (
            "600297",
            "2024-06-21",
            "2024-06-21",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-06-21/1220417373.PDF;"
            "https://www.sse.com.cn/disclosure/announcement/listing/stock/"
            "c/c_20240821_10760899.shtml",
        ),
        (
            "002505",
            "2024-05-24",
            "2024-05-24",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-05-24/1220146538.PDF;"
            "https://static.cninfo.com.cn/finalpage/2024-07-02/1220512277.PDF",
        ),
    )
    # 主动退市或换股期间的连续停牌属于明示持有受限，不能按陈旧行情残仓
    # 处理；事件仅使用停牌前已公告的信息。
    security_holding_restriction_events: tuple[
        tuple[str, str, str, str]
    ] = (
        (
            "000666",
            "2023-08-30",
            "2023-09-01",
            "https://disc.static.szse.cn/disc/disk03/finalpage/2023-08-30/"
            "deebf03d-2eb6-4a85-aaca-1e279d8d25d5.PDF;"
            "https://docs.static.szse.cn/www/market/periodical/month/"
            "W020230912344258642105.html",
        ),
        (
            "600837",
            "2024-09-06",
            "2024-09-06",
            "https://static.cninfo.com.cn/finalpage/2024-09-06/1221149206.PDF",
        ),
        (
            "600705",
            "2025-04-02",
            "2025-04-03",
            "https://static.cninfo.com.cn/finalpage/2025-04-02/1222984910.PDF",
        ),
        (
            "601028",
            "2025-03-26",
            "2025-03-27",
            "https://static.cninfo.com.cn/finalpage/2025-03-26/1222894279.PDF",
        ),
        (
            "601989",
            "2025-08-05",
            "2025-08-13",
            "https://static.cninfo.com.cn/finalpage/2025-08-05/1224387139.PDF",
        ),
    )
    security_cash_settlement_events: tuple[
        tuple[str, str, str, float, str]
    ] = (
        (
            "000666",
            "2023-10-17",
            "2023-10-20",
            9.24,
            "https://disc.static.szse.cn/disc/disk03/finalpage/2023-10-17/"
            "90d27795-d930-444b-8989-ad1a25fab54c.PDF;"
            "portfolio_policy:exercise_all_cash_choices_on_first_trading_day_after_deadline",
        ),
        (
            "600705",
            "2025-04-29",
            "2025-04-29",
            3.54,
            "https://static.cninfo.com.cn/finalpage/2025-04-15/1223096474.PDF;"
            "https://static.cninfo.com.cn/finalpage/2025-04-29/1223361233.PDF;"
            "portfolio_policy:exercise_all_eligible_cash_choices",
        ),
        (
            "601028",
            "2025-04-29",
            "2025-04-29",
            13.20,
            "https://static.cninfo.com.cn/finalpage/2025-04-09/1223031697.PDF;"
            "https://static.cninfo.com.cn/finalpage/2025-04-29/1223364520.PDF;"
            "portfolio_policy:exercise_all_eligible_cash_choices",
        ),
    )
    security_share_settlement_events: tuple[
        tuple[str, str, str, str, float, str]
    ] = (
        (
            "600837",
            "2025-03-14",
            "2025-03-17",
            "601211",
            0.62,
            "https://static.cninfo.com.cn/finalpage/2025-03-14/1222789432.PDF;"
            "https://www.sse.com.cn/disclosure/announcement/listing/stock/"
            "c/c_20250226_10773005.shtml;"
            "https://big5.sse.com.cn/site/cht/www.sse.com.cn/disclosure/"
            "listedinfo/announcement/c/new/2025-01-20/601211_20250120_9HL9.pdf",
        ),
        (
            "601989",
            "2025-09-04",
            "2025-09-16",
            "600150",
            0.1339,
            "https://static.cninfo.com.cn/finalpage/2025-09-04/1224636691.PDF;"
            "https://static.cninfo.com.cn/finalpage/2025-09-12/1224653312.PDF;"
            "https://www.sse.com.cn/disclosure/announcement/listing/stock/"
            "c/c_20250829_10790128.shtml",
        ),
    )
    security_delisting_risk_warning_exit_events: tuple[
        tuple[str, str, str, str, str]
    ] = (
        (
            "002621",
            "2024-04-29",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/disc/disk03/finalpage/2024-04-29/"
            "89e6358a-aed8-4266-8b50-3651c54f28e4.PDF",
        ),
        (
            "000836",
            "2024-04-29",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/download/disc/disk03/finalpage/2024-04-29/"
            "61338b02-baac-404d-bb8f-68326528dec0.PDF",
        ),
        (
            "002610",
            "2024-04-29",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/disc/disk03/finalpage/2024-04-29/"
            "1cca52de-0dc3-4db3-8ad6-347ad3315add.PDF",
        ),
        (
            "000982",
            "2024-06-17",
            "2024-06-17",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/disc/disk03/finalpage/2024-06-17/"
            "1a6ad3db-546e-4c96-8ee2-0aa6c1354ff3.PDF",
        ),
        (
            "002325",
            "2024-04-30",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-04-30/1219927919.PDF",
        ),
        (
            "002288",
            "2024-04-30",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-04-30/1219928670.PDF",
        ),
        (
            "300262",
            "2024-04-30",
            "2024-05-06",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2024-04-30/1219926734.PDF",
        ),
        (
            "002308",
            "2024-07-05",
            "2024-07-09",
            "risk_exit_on_next_trade",
            "https://disc.static.szse.cn/disc/disk03/finalpage/2024-07-05/"
            "4658dd68-8676-4445-a961-b79d8573c23d.PDF",
        ),
        (
            "600811",
            "2025-03-17",
            "2025-03-18",
            "risk_exit_on_next_trade",
            "https://static.cninfo.com.cn/finalpage/2025-03-17/1222816222.PDF;"
            "https://static.cninfo.com.cn/finalpage/2025-03-17/1222816224.PDF",
        ),
    )

    # 北京证券交易所于 2021-11-15 开市；此前相同代码号段属于全国股转系统，
    # 不能作为“沪深北全A”中的北交所证券。
    beijing_exchange_start: str = "2021-11-15"

    # 本地利润表字段编码：1=合并口径、1=完整报表、1=调整后口径。
    # 这些值只用于确定同一披露日的唯一数据行，不改变策略公式。
    financial_merged_flag: int = 1
    financial_complete_flag: int = 1
    financial_adjusted_flag: int = 1

    # 沪深北 A 股代码识别。北交所同时保留数据中出现的旧号段和 92 新号段，
    # 不做代码映射，原始代码始终保留在 stock_code 中以便审计。
    shanghai_prefixes: tuple[str, ...] = ("60", "68")
    shenzhen_prefixes: tuple[str, ...] = ("00", "30")
    beijing_prefixes: tuple[str, ...] = ("43", "83", "87", "88", "92")

    files: dict[str, str] = field(
        default_factory=lambda: {
            "stock_master": "ashare_stock.parquet",
            "calendar": "ashare_tradeday.parquet",
            "price_raw": "ashare_stock_price.parquet",
            "price_forward": "ashare_stock_price_forward.parquet",
            "trade": "ashare_stock_trade.parquet",
            "value": "ashare_stock_value.parquet",
            "balance": "ashare_stock_balance.parquet",
            "income": "ashare_stock_income.parquet",
            "st": "ashare_stock_st.parquet",
            "suspend": "ashare_stock_suspend.parquet",
            "limit": "ashare_stock_limit.parquet",
        }
    )

    def __post_init__(self) -> None:
        """在任何数据读取前验证成本、净值和数值容差接口。"""
        rate_fields = {
            "commission_rate": self.commission_rate,
            "slippage_rate": self.slippage_rate,
            "stamp_tax_before_2023_08_28": self.stamp_tax_before_2023_08_28,
            "stamp_tax_from_2023_08_28": self.stamp_tax_from_2023_08_28,
        }
        invalid_rates = {
            name: value
            for name, value in rate_fields.items()
            if not isfinite(value) or not 0.0 <= value < 1.0
        }
        if invalid_rates:
            raise ValueError(f"交易成本率必须有限且位于[0,1): {invalid_rates}")
        if self.stamp_tax_from_2023_08_28 > self.stamp_tax_before_2023_08_28:
            raise ValueError("2023-08-28后的印花税率不得高于调整前税率")
        if not isfinite(self.initial_nav) or self.initial_nav <= 0.0:
            raise ValueError("initial_nav必须为正且有限")
        tolerances = {
            "weight_tolerance": self.weight_tolerance,
            "cash_tolerance": self.cash_tolerance,
            "numeric_tolerance": self.numeric_tolerance,
        }
        invalid_tolerances = {
            name: value
            for name, value in tolerances.items()
            if not isfinite(value) or value <= 0.0
        }
        if invalid_tolerances:
            raise ValueError(f"数值容差必须为正且有限: {invalid_tolerances}")
        if not 1 <= self.minimum_core_value_components <= 3:
            raise ValueError("minimum_core_value_components 必须位于[1,3]")
        if self.dividend_max_age_trading_days < 0:
            raise ValueError("dividend_max_age_trading_days 不得为负")
        coverage_rates = {
            "minimum_style_coverage": self.minimum_style_coverage,
            "stable_style_coverage": self.stable_style_coverage,
            "minimum_box_share_of_eligible": self.minimum_box_share_of_eligible,
            "maximum_style_coverage_jump": self.maximum_style_coverage_jump,
            "maximum_single_stock_weight": self.maximum_single_stock_weight,
            "maximum_top_ten_weight": self.maximum_top_ten_weight,
        }
        invalid_coverages = {
            name: value
            for name, value in coverage_rates.items()
            if not isfinite(value) or not 0.0 <= value <= 1.0
        }
        if invalid_coverages:
            raise ValueError(f"覆盖/集中度门禁必须位于[0,1]: {invalid_coverages}")
        if self.stable_style_coverage < self.minimum_style_coverage:
            raise ValueError("stable_style_coverage 不得低于 minimum_style_coverage")
        if self.minimum_stable_style_months <= 0 or self.minimum_box_members <= 0:
            raise ValueError("月数与四箱最小成员数必须为正")
        if self.maximum_unexplained_price_age_trading_days < 0:
            raise ValueError("陈旧价格寿命不得为负")
        if self.maximum_zero_target_rebalances <= 0:
            raise ValueError("连续零目标调仓次数必须为正")
        if self.security_transfer_old_code == self.security_transfer_new_code:
            raise ValueError("退市转板旧代码与新代码不得相同")
        if self.security_transfer_ratio != 1.0:
            raise ValueError("600466→400165迁移比例必须严格为1:1")
        if self.security_transfer_max_wait_trading_days != 45:
            raise ValueError("600466转板等待窗口必须严格为45交易日")
        if not (
            self.security_transfer_source_public_date
            <= self.security_transfer_delisting_date
            <= self.security_transfer_mapping_public_date
            <= self.security_transfer_effective_date
        ):
            raise ValueError("600466转板公开/摘牌/映射/生效日期顺序异常")
        transfer_positive = (
            self.security_transfer_old_mark,
            self.security_transfer_expected_exit_vwap,
            self.security_transfer_expected_first_volume_shares,
            float(self.security_transfer_market_row_count),
            float(self.security_transfer_price_factor),
            float(self.security_transfer_ohlc_field_count),
            float(self.security_transfer_source_count),
            float(self.sha256_hex_length),
        )
        if any(not isfinite(value) or value <= 0 for value in transfer_positive):
            raise ValueError("退市转板价格、成交量、行数及解析参数必须为正")
        frozen_hashes = dict(self.security_transfer_frozen_sha256)
        if len(frozen_hashes) != len(self.security_transfer_frozen_sha256):
            raise ValueError("退市转板冻结文件名不得重复")
        if any(
            len(digest) != self.sha256_hex_length
            or any(character not in "0123456789abcdef" for character in digest)
            for digest in frozen_hashes.values()
        ):
            raise ValueError("退市转板冻结哈希必须为完整小写64位SHA-256")
        if (
            len(self.security_transfer_manifest_sha256) != self.sha256_hex_length
            or any(
                character not in "0123456789abcdef"
                for character in self.security_transfer_manifest_sha256
            )
        ):
            raise ValueError("退市转板source_manifest哈希必须为完整小写SHA-256")
        required_transfer_files = {
            self.security_transfer_sse_raw_filename,
            self.security_transfer_neeq_raw_filename,
            self.security_transfer_market_raw_filename,
            self.security_transfer_market_parsed_filename,
        }
        if not required_transfer_files.issubset(frozen_hashes):
            raise ValueError("退市转板冻结哈希缺必需原始或解析文件")
        valuation_priorities = (
            self.valuation_priority_observable_market,
            self.valuation_priority_explicit_settlement,
            self.valuation_priority_transfer_pending,
            self.valuation_priority_bounded_carry,
            self.valuation_priority_unpriced_asset,
            self.valuation_priority_behavior_evidence,
        )
        if any(priority <= 0 for priority in valuation_priorities):
            raise ValueError("估值来源优先级必须为正整数")
        if tuple(sorted(valuation_priorities)) != valuation_priorities:
            raise ValueError("估值来源优先级必须严格递增")

    def path(self, key: str) -> Path:
        """返回配置键对应的本地 Parquet 路径。"""
        return self.data_root / self.files[key]

    @property
    def calendar_start(self) -> str:
        """首个持有月之前一个月，供月末信号日定位。"""
        start = pd.Timestamp(self.history_start).to_period("M") - 1
        return str(start.start_time.date())

    @property
    def calendar_end(self) -> str:
        """多读两个月交易日，以获得末期收益端点。"""
        end = pd.Timestamp(self.history_end) + pd.DateOffset(months=2)
        return str(end.date())


DEFAULT_CONFIG = AllAStyleBoxConfig()


__all__ = ["AllAStyleBoxConfig", "DEFAULT_CONFIG"]

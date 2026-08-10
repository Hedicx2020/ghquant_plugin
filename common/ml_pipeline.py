"""机器学习研报共用的时点安全数据、特征、标签、窗口与回归接口。

本模块不绑定具体报告、模型参数或回测逻辑。关键约束是：

* 特征窗口只包含信号日及其之前的信息；
* 预处理器只能由训练样本实际使用的行拟合；
* 未来收益标签必须按交易日历核验 T+1 与 T+N 端点；
* split 归属由信号、买入和卖出日期决定，特征窗口可向段前读取纯历史；
* T+1 可交易状态只作为执行元数据，绝不参与 T 日股票池或特征。
* 滚动回归只接受严格早于预测日的完整历史样本，不做缺失填补；
* 集成预测必须由同一观测键下全部基础模型的有限预测共同形成。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


KEY_COLUMNS = ("stock_code", "date")
DEFAULT_FEATURE_COLUMNS = (
    "open_rel_prev_close",
    "high_rel_prev_close",
    "low_rel_prev_close",
    "close_rel_prev_close",
    "volume_log1p",
    "turn_value_log1p",
)


@dataclass(frozen=True)
class DateSegment:
    """互不重叠的样本分段，起止日期均为闭区间。"""

    name: str
    start: pd.Timestamp
    end: pd.Timestamp

    def __post_init__(self) -> None:
        start = pd.Timestamp(self.start).normalize()
        end = pd.Timestamp(self.end).normalize()
        if start > end:
            raise ValueError(f"分段 {self.name} 的 start 晚于 end")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)


@dataclass(frozen=True)
class FeaturePreprocessor:
    """仅由训练样本拟合的逐通道缩尾与标准化参数。"""

    feature_columns: tuple[str, ...]
    lower: pd.Series
    upper: pd.Series
    mean: pd.Series
    std: pd.Series
    fit_row_count: int
    fit_start: pd.Timestamp
    fit_end: pd.Timestamp
    lower_quantile: float
    upper_quantile: float

    def to_frame(self) -> pd.DataFrame:
        """返回可审计的逐通道参数表。"""
        return pd.DataFrame(
            {
                "feature": self.feature_columns,
                "winsor_lower": self.lower.reindex(self.feature_columns).to_numpy(),
                "winsor_upper": self.upper.reindex(self.feature_columns).to_numpy(),
                "train_mean": self.mean.reindex(self.feature_columns).to_numpy(),
                "train_std": self.std.reindex(self.feature_columns).to_numpy(),
                "fit_row_count": self.fit_row_count,
                "fit_start": self.fit_start,
                "fit_end": self.fit_end,
            }
        )


@dataclass
class PreparedMLData:
    """紧凑的特征面板、样本索引、预处理器和审计统计。"""

    feature_panel: pd.DataFrame
    samples: pd.DataFrame
    feature_columns: tuple[str, ...]
    preprocessor: FeaturePreprocessor
    quality_summary: dict[str, Any]

    _feature_values: np.ndarray = field(init=False, repr=False)
    _panel_row_starts: np.ndarray = field(init=False, repr=False)
    _panel_row_ends: np.ndarray = field(init=False, repr=False)
    _labels: np.ndarray = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """缓存一份所有 split/模型共享的紧凑训练数组。"""
        required = {"panel_row_start", "panel_row_end", "label", "split"}
        missing = sorted(required - set(self.samples.columns))
        if missing:
            raise KeyError(f"样本索引缺少数据集字段: {missing}")
        feature_values = self.feature_panel.loc[
            :, self.feature_columns
        ].to_numpy(dtype=np.float32, copy=False)
        self._feature_values = np.ascontiguousarray(feature_values)
        self._feature_values.setflags(write=False)
        self._panel_row_starts = self.samples["panel_row_start"].to_numpy(
            dtype=np.int64, copy=True
        )
        self._panel_row_ends = self.samples["panel_row_end"].to_numpy(
            dtype=np.int64, copy=True
        )
        self._labels = pd.to_numeric(
            self.samples["label"], errors="coerce"
        ).to_numpy(dtype=np.float32, na_value=np.nan)

    @property
    def standardized_feature_values(self) -> np.ndarray:
        """返回训练/预测实际共享的只读float32特征底板，不额外复制。"""
        return self._feature_values

    def dataset(self, split: str) -> "PanelWindowDataset":
        """按 split 构造惰性窗口数据集，只保存样本位置而不复制面板。"""
        split_mask = self.samples["split"].astype("string").eq(split).fillna(False)
        selected_positions = np.flatnonzero(split_mask.to_numpy(dtype=bool))
        return PanelWindowDataset(
            feature_panel=self.feature_panel,
            samples=self.samples,
            feature_columns=self.feature_columns,
            feature_values=self._feature_values,
            sample_positions=selected_positions,
            panel_row_starts=self._panel_row_starts,
            panel_row_ends=self._panel_row_ends,
            labels=self._labels,
        )


class PanelWindowDataset(Sequence[tuple[np.ndarray, np.float32]]):
    """按需切片的面板窗口；支持DataLoader按Sampler顺序整批向量化取窗。

    ``__getitem__`` 保留原有单样本语义，``__getitems__`` 仅把DataLoader已经
    决定好的批索引一次性取出，不自行排序或打乱。因此训练shuffle及验证/预测
    顺序仍完全由原 ``RandomSampler`` / ``SequentialSampler`` 决定。
    """

    supports_prebatched_fetch = True

    def __init__(
        self,
        feature_panel: pd.DataFrame,
        samples: pd.DataFrame,
        feature_columns: Sequence[str],
        *,
        feature_values: np.ndarray | None = None,
        sample_positions: np.ndarray | None = None,
        panel_row_starts: np.ndarray | None = None,
        panel_row_ends: np.ndarray | None = None,
        labels: np.ndarray | None = None,
    ) -> None:
        self.feature_columns = tuple(feature_columns)
        index = samples.index
        self._metadata_source = (
            samples
            if isinstance(index, pd.RangeIndex)
            and index.start == 0
            and index.step == 1
            else samples.reset_index(drop=True)
        )
        self._sample_positions = (
            np.arange(len(self._metadata_source), dtype=np.int64)
            if sample_positions is None
            else np.asarray(sample_positions, dtype=np.int64)
        )
        self._features = (
            np.ascontiguousarray(
                feature_panel.loc[:, self.feature_columns].to_numpy(
                    dtype=np.float32, copy=False
                )
            )
            if feature_values is None
            else np.asarray(feature_values, dtype=np.float32)
        )
        self._panel_row_starts = (
            self._metadata_source["panel_row_start"].to_numpy(
                dtype=np.int64, copy=True
            )
            if panel_row_starts is None
            else np.asarray(panel_row_starts, dtype=np.int64)
        )
        self._panel_row_ends = (
            self._metadata_source["panel_row_end"].to_numpy(
                dtype=np.int64, copy=True
            )
            if panel_row_ends is None
            else np.asarray(panel_row_ends, dtype=np.int64)
        )
        self._labels = (
            pd.to_numeric(self._metadata_source["label"], errors="coerce").to_numpy(
                dtype=np.float32, na_value=np.nan
            )
            if labels is None
            else np.asarray(labels, dtype=np.float32)
        )
        source_length = len(self._metadata_source)
        for name, values in (
            ("panel_row_starts", self._panel_row_starts),
            ("panel_row_ends", self._panel_row_ends),
            ("labels", self._labels),
        ):
            if values.shape != (source_length,):
                raise ValueError(f"{name} 长度与样本元数据不一致")
        if self._sample_positions.ndim != 1:
            raise ValueError("sample_positions 必须为一维数组")
        if len(self._sample_positions) and (
            self._sample_positions.min() < 0
            or self._sample_positions.max() >= source_length
        ):
            raise IndexError("sample_positions 超出样本元数据范围")
        selected_starts = self._panel_row_starts[self._sample_positions]
        selected_ends = self._panel_row_ends[self._sample_positions]
        window_lengths = selected_ends - selected_starts + 1
        if len(window_lengths):
            unique_lengths = np.unique(window_lengths)
            if len(unique_lengths) != 1 or unique_lengths[0] <= 0:
                raise ValueError("PanelWindowDataset 要求所有窗口具有相同正长度")
            self.window_length = int(unique_lengths[0])
            if selected_starts.min() < 0 or selected_ends.max() >= len(self._features):
                raise IndexError("窗口行索引超出特征面板范围")
        else:
            self.window_length = 0
        self._window_offsets = np.arange(self.window_length, dtype=np.int64)
        self._samples_cache: pd.DataFrame | None = None

    @property
    def samples(self) -> pd.DataFrame:
        """兼容旧接口；仅在显式访问时才物化所选split元数据。"""
        if self._samples_cache is None:
            self._samples_cache = self._metadata_source.iloc[
                self._sample_positions
            ].reset_index(drop=True)
        return self._samples_cache

    def __len__(self) -> int:
        return len(self._sample_positions)

    def __getitem__(self, index: int) -> tuple[np.ndarray, np.float32]:
        source_position = int(self._sample_positions[index])
        start = int(self._panel_row_starts[source_position])
        end = int(self._panel_row_ends[source_position]) + 1
        return self._features[start:end].copy(), np.float32(
            self._labels[source_position]
        )

    def __getitems__(
        self,
        indices: Sequence[int],
    ) -> tuple[np.ndarray, np.ndarray]:
        """按DataLoader给定顺序批量取窗，避免逐样本pandas索引和小对象。"""
        local_indices = np.asarray(indices, dtype=np.int64)
        if local_indices.ndim != 1:
            raise ValueError("批量样本索引必须为一维")
        source_positions = self._sample_positions[local_indices]
        starts = self._panel_row_starts[source_positions]
        row_indices = starts[:, None] + self._window_offsets[None, :]
        features = np.ascontiguousarray(self._features[row_indices])
        labels = np.ascontiguousarray(self._labels[source_positions])
        return features, labels

    def metadata(self, index: int) -> pd.Series:
        """返回样本键、日期与执行状态等非特征元数据。"""
        source_position = int(self._sample_positions[index])
        return self._metadata_source.iloc[source_position].copy()


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], context: str) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise KeyError(f"{context} 缺少字段: {missing}")


def _assert_unique_keys(frame: pd.DataFrame, context: str) -> None:
    if frame.duplicated(list(KEY_COLUMNS)).any():
        duplicates = int(frame.duplicated(list(KEY_COLUMNS), keep=False).sum())
        raise ValueError(f"{context} 存在 {duplicates} 行重复 stock_code/date 键")


def build_features(panel: pd.DataFrame, feature_cfg: Mapping[str, Any]) -> pd.DataFrame:
    """构造六通道价量原始特征，尚不拟合或应用标准化参数。

    OHLC 均相对同一行的前一交易日收盘价取对数比率；成交量和成交金额
    取 ``log1p``。非正价格、负成交量/成交金额和无穷值均转为缺失，后续
    窗口构造会剔除含缺失的窗口。
    """
    price_columns = tuple(feature_cfg["price_columns"])
    if len(price_columns) != 4:
        raise ValueError("price_columns 必须依次包含 open/high/low/close 四个字段")
    previous_close = str(feature_cfg["previous_close_column"])
    volume = str(feature_cfg["volume_column"])
    turn_value = str(feature_cfg["turn_value_column"])
    output_columns = tuple(feature_cfg.get("output_columns", DEFAULT_FEATURE_COLUMNS))
    if len(output_columns) != 6:
        raise ValueError("output_columns 必须正好包含六个特征名")
    _require_columns(panel, (*KEY_COLUMNS, *price_columns, previous_close, volume, turn_value), "特征面板")

    result = panel.loc[:, KEY_COLUMNS].copy()
    denominator = pd.to_numeric(panel[previous_close], errors="coerce").where(lambda s: s > 0)
    for source, target in zip(price_columns, output_columns[:4]):
        numerator = pd.to_numeric(panel[source], errors="coerce").where(lambda s: s > 0)
        result[target] = np.log(numerator / denominator)
    result[output_columns[4]] = np.log1p(
        pd.to_numeric(panel[volume], errors="coerce").where(lambda s: s >= 0)
    )
    result[output_columns[5]] = np.log1p(
        pd.to_numeric(panel[turn_value], errors="coerce").where(lambda s: s >= 0)
    )
    result.loc[:, output_columns] = result.loc[:, output_columns].replace([np.inf, -np.inf], np.nan)
    return result


def derive_forward_adjusted_vwap(
    panel: pd.DataFrame,
    *,
    forward_close_col: str,
    raw_close_col: str,
    raw_low_col: str,
    raw_high_col: str,
    volume_col: str,
    turn_value_col: str,
    output_col: str,
    sanity_min_price_ratio: float,
    sanity_max_price_ratio: float,
    sanity_min_fraction: float,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """由成交额/成交量推导原始VWAP，再按收盘价复权比例转为前复权VWAP。

    按AS14，在复权前先用显式配置阈值断言 ``turn_value / volume`` 与未复权
    OHLC 同量纲。逐行不合格记录置为缺失；全部记录不可核验或全局合格率低于
    ``sanity_min_fraction`` 时中止整个数据流程，不允许静默生成标签。
    """
    required = (
        forward_close_col,
        raw_close_col,
        raw_low_col,
        raw_high_col,
        volume_col,
        turn_value_col,
    )
    _require_columns(panel, required, "VWAP推导面板")
    result = panel.copy()
    volume = pd.to_numeric(result[volume_col], errors="coerce")
    turn_value = pd.to_numeric(result[turn_value_col], errors="coerce")
    raw_close = pd.to_numeric(result[raw_close_col], errors="coerce")
    forward_close = pd.to_numeric(result[forward_close_col], errors="coerce")
    raw_low = pd.to_numeric(result[raw_low_col], errors="coerce")
    raw_high = pd.to_numeric(result[raw_high_col], errors="coerce")

    valid_base = (
        (volume > 0)
        & (turn_value >= 0)
        & (raw_close > 0)
        & (forward_close > 0)
        & (raw_low > 0)
        & (raw_high > 0)
    )
    raw_vwap = (turn_value / volume).where(valid_base)
    vwap_to_close = raw_vwap / raw_close
    ohlc_consistent = raw_vwap.between(raw_low * sanity_min_price_ratio, raw_high * sanity_max_price_ratio)
    magnitude_consistent = vwap_to_close.between(sanity_min_price_ratio, sanity_max_price_ratio)
    sanity = (ohlc_consistent & magnitude_consistent).where(raw_vwap.notna())
    valid_sanity = sanity.dropna()
    if valid_sanity.empty:
        raise ValueError("无法找到可核验的正成交量VWAP记录")
    sanity_fraction = float(valid_sanity.mean())
    if sanity_fraction < sanity_min_fraction:
        raise ValueError(
            "turn_value/volume 与未复权OHLC数量级不一致: "
            f"合格比例={sanity_fraction:.4f}, 下限={sanity_min_fraction:.4f}"
        )

    adjustment_ratio = (forward_close / raw_close).where(valid_base)
    result[output_col] = (raw_vwap * adjustment_ratio).where(sanity.fillna(False))
    diagnostics = {
        "source_rows": float(len(result)),
        "positive_volume_rows": float(valid_base.sum()),
        "zero_or_invalid_volume_rows": float((~valid_base).sum()),
        "vwap_sanity_fraction": sanity_fraction,
        "vwap_to_raw_close_median": float(vwap_to_close.dropna().median()),
        "adjustment_ratio_median": float(adjustment_ratio.dropna().median()),
    }
    return result, diagnostics


def build_forward_return_labels(
    panel: pd.DataFrame,
    trade_calendar: pd.DataFrame,
    *,
    vwap_col: str,
    entry_offset: int,
    exit_offset: int,
    label_col: str = "label",
) -> pd.DataFrame:
    """构造 T+entry 至 T+exit 的简单收益，日期端点独立于标签可得性。

    entry/exit 日期直接由全市场交易日历偏移得到，再按证券和日期精确查找
    VWAP。这样即使某证券的未来VWAP缺失，预测样本仍保留正确的交易日期，
    仅 ``label`` 为缺失；不会把该证券的“下一条记录”误当成下一交易日。
    """
    if not 0 < entry_offset < exit_offset:
        raise ValueError("必须满足 0 < entry_offset < exit_offset")
    _require_columns(panel, (*KEY_COLUMNS, vwap_col), "标签面板")
    _require_columns(trade_calendar, ("date",), "交易日历")
    _assert_unique_keys(panel, "标签面板")

    calendar = (
        pd.DataFrame({"date": pd.to_datetime(trade_calendar["date"]).dt.normalize()})
        .drop_duplicates()
        .sort_values("date")
        .reset_index(drop=True)
    )
    calendar["trade_index"] = np.arange(len(calendar), dtype=np.int64)
    working = panel.loc[:, list(KEY_COLUMNS)].copy()
    working["date"] = pd.to_datetime(working["date"]).dt.normalize()
    working = working.merge(calendar, on="date", how="left", validate="many_to_one")
    if working["trade_index"].isna().any():
        raise ValueError("标签面板含非交易日日期")
    working = working.sort_values(list(KEY_COLUMNS)).reset_index(drop=True)
    working["trade_index"] = working["trade_index"].astype(np.int64)
    index_to_date = calendar.set_index("trade_index")["date"]
    working["entry_date"] = (working["trade_index"] + entry_offset).map(index_to_date)
    working["exit_date"] = (working["trade_index"] + exit_offset).map(index_to_date)

    vwap_lookup = panel.loc[:, [*KEY_COLUMNS, vwap_col]].copy()
    vwap_lookup["date"] = pd.to_datetime(vwap_lookup["date"]).dt.normalize()
    entry_lookup = vwap_lookup.rename(
        columns={"date": "entry_date", vwap_col: "entry_vwap"}
    )
    exit_lookup = vwap_lookup.rename(
        columns={"date": "exit_date", vwap_col: "exit_vwap"}
    )
    working = working.merge(
        entry_lookup,
        on=["stock_code", "entry_date"],
        how="left",
        validate="many_to_one",
    )
    working = working.merge(
        exit_lookup,
        on=["stock_code", "exit_date"],
        how="left",
        validate="many_to_one",
    )

    endpoints_in_calendar = working["entry_date"].notna() & working["exit_date"].notna()
    valid_prices = (working["entry_vwap"] > 0) & (working["exit_vwap"] > 0)
    working[label_col] = (
        working["exit_vwap"] / working["entry_vwap"] - 1.0
    ).where(endpoints_in_calendar & valid_prices)
    working["label_valid"] = working[label_col].notna()
    return working.loc[
        :,
        [
            *KEY_COLUMNS,
            "trade_index",
            "entry_date",
            "exit_date",
            "entry_vwap",
            "exit_vwap",
            label_col,
            "label_valid",
        ],
    ]


def build_point_in_time_universe(
    panel: pd.DataFrame,
    stock_master: pd.DataFrame,
    st_intervals: pd.DataFrame,
    *,
    minimum_listing_years: int,
) -> pd.DataFrame:
    """按信号日构造股票池，不用当前 ``list_state`` 回填历史状态。

    每日行情存在性代表该日有可观察行情；上市起点优先采用 ``list_date``，
    缺失时回退为该证券首个行情日。当前快照 ``list_state`` 仅保留为审计字段，
    不参与历史时点资格，避免把今天的状态泄漏到过去。
    """
    _require_columns(panel, KEY_COLUMNS, "股票池面板")
    _require_columns(stock_master, ("stock_code", "list_date", "list_state"), "股票基础表")
    _require_columns(st_intervals, ("stock_code", "implement_date", "remove_date"), "ST区间表")
    _assert_unique_keys(panel, "股票池面板")

    keys = panel.loc[:, KEY_COLUMNS].copy()
    keys["date"] = pd.to_datetime(keys["date"]).dt.normalize()
    observed = (
        keys.groupby("stock_code", as_index=False)["date"]
        .min()
        .rename(columns={"date": "first_observed_date"})
    )
    master = stock_master.loc[:, ["stock_code", "list_date", "list_state"]].drop_duplicates("stock_code")
    master["list_date"] = pd.to_datetime(master["list_date"], errors="coerce").dt.normalize()
    basis = observed.merge(master, on="stock_code", how="left", validate="one_to_one")
    basis["effective_list_date"] = basis["list_date"].fillna(basis["first_observed_date"])
    basis["eligible_from"] = basis["effective_list_date"].map(
        lambda value: value + pd.DateOffset(years=minimum_listing_years)
    )
    result = keys.merge(basis, on="stock_code", how="left", validate="many_to_one")
    result["has_market_row"] = True
    result["listed_by_signal_date"] = result["date"] >= result["effective_list_date"]
    result["listing_age_eligible"] = result["date"] >= result["eligible_from"]

    result["is_st"] = False
    st = st_intervals.loc[:, ["stock_code", "implement_date", "remove_date"]].copy()
    st["implement_date"] = pd.to_datetime(st["implement_date"], errors="coerce").dt.normalize()
    st["remove_date"] = pd.to_datetime(st["remove_date"], errors="coerce").dt.normalize()
    positions = result.groupby("stock_code", sort=False).indices
    for stock_code, intervals in st.dropna(subset=["implement_date"]).groupby("stock_code", sort=False):
        row_positions = positions.get(stock_code)
        if row_positions is None:
            continue
        dates = result.iloc[row_positions]["date"].to_numpy(dtype="datetime64[ns]")
        stock_mask = np.zeros(len(row_positions), dtype=bool)
        for interval in intervals.itertuples(index=False):
            start = np.datetime64(interval.implement_date)
            end = np.datetime64(interval.remove_date) if pd.notna(interval.remove_date) else np.datetime64("2262-04-11")
            stock_mask |= (dates >= start) & (dates < end)
        result.iloc[row_positions, result.columns.get_loc("is_st")] = stock_mask

    result["eligible_signal"] = (
        result["has_market_row"]
        & result["listed_by_signal_date"]
        & result["listing_age_eligible"]
        & ~result["is_st"]
    )
    return result


def attach_entry_tradability(
    samples: pd.DataFrame,
    suspend_status: pd.DataFrame,
    limit_status: pd.DataFrame,
) -> pd.DataFrame:
    """附加 T+1 停牌/涨跌停状态；这些列不得用于 T 日样本筛选。"""
    _require_columns(samples, ("stock_code", "entry_date"), "样本索引")
    _require_columns(suspend_status, ("stock_code", "date", "if_suspend"), "停牌状态")
    _require_columns(
        limit_status,
        ("stock_code", "date", "surged_limit", "decline_limit"),
        "涨跌停状态",
    )
    result = samples.copy()
    suspend = suspend_status.loc[:, ["stock_code", "date", "if_suspend"]].copy()
    limit_ = limit_status.loc[:, ["stock_code", "date", "surged_limit", "decline_limit"]].copy()
    suspend = suspend.rename(columns={"date": "entry_date", "if_suspend": "entry_if_suspend"})
    limit_ = limit_.rename(
        columns={
            "date": "entry_date",
            "surged_limit": "entry_surged_limit",
            "decline_limit": "entry_decline_limit",
        }
    )
    result = result.merge(suspend, on=["stock_code", "entry_date"], how="left", validate="many_to_one")
    result = result.merge(limit_, on=["stock_code", "entry_date"], how="left", validate="many_to_one")
    for column in ("entry_if_suspend", "entry_surged_limit", "entry_decline_limit"):
        result[column] = result[column].fillna(0).astype("int8")
    result["entry_tradable"] = ~(
        result["entry_if_suspend"].eq(1)
        | result["entry_surged_limit"].eq(1)
        | result["entry_decline_limit"].eq(1)
    )
    return result


def build_window_index(
    features: pd.DataFrame,
    trade_calendar: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    window_length: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """生成连续全市场交易日窗口的惰性行索引。"""
    if window_length <= 0:
        raise ValueError("window_length 必须为正整数")
    feature_columns = tuple(feature_columns)
    _require_columns(features, (*KEY_COLUMNS, *feature_columns), "特征表")
    _assert_unique_keys(features, "特征表")
    calendar = pd.DataFrame({"date": pd.to_datetime(trade_calendar["date"]).dt.normalize()})
    calendar = calendar.drop_duplicates().sort_values("date").reset_index(drop=True)
    calendar["trade_index"] = np.arange(len(calendar), dtype=np.int64)

    working = features.copy()
    working["date"] = pd.to_datetime(working["date"]).dt.normalize()
    working = working.replace([np.inf, -np.inf], np.nan).dropna(subset=list(feature_columns))
    working = working.merge(calendar, on="date", how="left", validate="many_to_one")
    if working["trade_index"].isna().any():
        raise ValueError("特征表含非交易日日期")
    working = working.sort_values(list(KEY_COLUMNS)).reset_index(drop=True)
    working["panel_row_end"] = np.arange(len(working), dtype=np.int64)
    grouped = working.groupby("stock_code", sort=False)
    working["window_start_trade_index"] = grouped["trade_index"].shift(window_length - 1)
    working["window_start_date"] = grouped["date"].shift(window_length - 1)
    working["panel_row_start"] = grouped["panel_row_end"].shift(window_length - 1)
    complete = (
        working["trade_index"] - working["window_start_trade_index"] == window_length - 1
    )
    windows = working.loc[
        complete,
        [
            *KEY_COLUMNS,
            "window_start_date",
            "panel_row_start",
            "panel_row_end",
        ],
    ].copy()
    windows[["panel_row_start", "panel_row_end"]] = windows[
        ["panel_row_start", "panel_row_end"]
    ].astype(np.int64)
    return working.loc[:, [*KEY_COLUMNS, *feature_columns]], windows.reset_index(drop=True)


def assign_non_overlapping_splits(
    samples: pd.DataFrame,
    segments: Sequence[DateSegment],
) -> pd.DataFrame:
    """按AS19用信号、买入和卖出日期归属分段，窗口可向段前取纯历史。"""
    _require_columns(samples, ("date", "entry_date", "exit_date"), "样本索引")
    ordered = sorted(segments, key=lambda segment: segment.start)
    for previous, current in zip(ordered, ordered[1:]):
        if current.start <= previous.end:
            raise ValueError(f"分段 {previous.name} 与 {current.name} 的日期区间重叠")
    result = samples.copy()
    result["split"] = pd.Series(pd.NA, index=result.index, dtype="string")
    occupied = pd.Series(False, index=result.index)
    for segment in segments:
        mask = (
            result["date"].between(segment.start, segment.end)
            & result["entry_date"].between(segment.start, segment.end)
            & result["exit_date"].between(segment.start, segment.end)
        )
        if (occupied & mask).any():
            raise ValueError(f"分段 {segment.name} 与其他分段存在重叠")
        result.loc[mask, "split"] = segment.name
        occupied |= mask
    return result


def fit_feature_preprocessor(
    feature_panel: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    fit_mask: pd.Series | np.ndarray,
    lower_quantile: float,
    upper_quantile: float,
    std_epsilon: float,
) -> FeaturePreprocessor:
    """仅在显式 ``fit_mask`` 指定的训练输入行上拟合预处理参数。"""
    if not 0.0 <= lower_quantile < upper_quantile <= 1.0:
        raise ValueError("缩尾分位点必须满足 0 <= lower < upper <= 1")
    feature_columns = tuple(feature_columns)
    _require_columns(feature_panel, ("date", *feature_columns), "预处理拟合表")
    mask = np.asarray(fit_mask, dtype=bool)
    if mask.shape != (len(feature_panel),):
        raise ValueError("fit_mask 长度与特征面板不一致")
    train = feature_panel.loc[mask, feature_columns]
    if train.empty:
        raise ValueError("训练样本未提供任何可拟合特征行")
    lower = train.quantile(lower_quantile)
    upper = train.quantile(upper_quantile)
    clipped = train.clip(lower=lower, upper=upper, axis="columns")
    mean = clipped.mean()
    std = clipped.std(ddof=0).where(lambda values: values > std_epsilon, 1.0)
    fit_dates = pd.to_datetime(feature_panel.loc[mask, "date"])
    return FeaturePreprocessor(
        feature_columns=feature_columns,
        lower=lower,
        upper=upper,
        mean=mean,
        std=std,
        fit_row_count=int(mask.sum()),
        fit_start=fit_dates.min(),
        fit_end=fit_dates.max(),
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
    )


def transform_features(
    feature_panel: pd.DataFrame,
    preprocessor: FeaturePreprocessor,
) -> pd.DataFrame:
    """用已拟合的训练参数原样变换任意分段，不重新拟合。"""
    _require_columns(feature_panel, preprocessor.feature_columns, "预处理变换表")
    result = feature_panel.copy()
    columns = list(preprocessor.feature_columns)
    clipped = result.loc[:, columns].clip(
        lower=preprocessor.lower,
        upper=preprocessor.upper,
        axis="columns",
    )
    result.loc[:, columns] = (clipped - preprocessor.mean) / preprocessor.std
    return result


def _rows_used_by_windows(
    row_count: int,
    starts: np.ndarray,
    ends: np.ndarray,
) -> np.ndarray:
    """用差分数组标记一组闭区间窗口实际覆盖的面板行。"""
    marker = np.zeros(row_count + 1, dtype=np.int64)
    np.add.at(marker, starts.astype(np.int64), 1)
    after = ends.astype(np.int64) + 1
    np.add.at(marker, after[after < row_count], -1)
    return np.cumsum(marker[:-1]) > 0


def prepare_point_in_time_ml_data(
    panel: pd.DataFrame,
    stock_master: pd.DataFrame,
    st_intervals: pd.DataFrame,
    suspend_status: pd.DataFrame,
    limit_status: pd.DataFrame,
    trade_calendar: pd.DataFrame,
    *,
    feature_cfg: Mapping[str, Any],
    vwap_col: str,
    entry_offset: int,
    exit_offset: int,
    window_length: int,
    minimum_listing_years: int,
    segments: Sequence[DateSegment],
    train_split_name: str,
    label_required_splits: Sequence[str] | None = None,
    allow_missing_label_splits: Sequence[str] = (),
    lower_quantile: float,
    upper_quantile: float,
    std_epsilon: float,
) -> PreparedMLData:
    """端到端构造时点安全的特征窗口、标签、股票池和三段样本。"""
    feature_columns = tuple(feature_cfg.get("output_columns", DEFAULT_FEATURE_COLUMNS))
    raw_features = build_features(panel, feature_cfg)
    raw_feature_missing_rate = raw_features.loc[:, feature_columns].isna().mean().to_dict()
    feature_panel, windows = build_window_index(
        raw_features,
        trade_calendar,
        feature_columns=feature_columns,
        window_length=window_length,
    )
    labels = build_forward_return_labels(
        panel,
        trade_calendar,
        vwap_col=vwap_col,
        entry_offset=entry_offset,
        exit_offset=exit_offset,
    )
    universe = build_point_in_time_universe(
        panel,
        stock_master,
        st_intervals,
        minimum_listing_years=minimum_listing_years,
    )
    universe_columns = [
        *KEY_COLUMNS,
        "effective_list_date",
        "list_state",
        "listed_by_signal_date",
        "listing_age_eligible",
        "is_st",
        "eligible_signal",
    ]
    samples = windows.merge(labels, on=list(KEY_COLUMNS), how="left", validate="one_to_one")
    samples = samples.merge(
        universe.loc[:, universe_columns],
        on=list(KEY_COLUMNS),
        how="left",
        validate="one_to_one",
    )
    samples = assign_non_overlapping_splits(samples, segments)

    candidate_count = len(samples)
    segment_names = {segment.name for segment in segments}
    optional_label_splits = set(allow_missing_label_splits)
    required_label_splits = (
        segment_names - optional_label_splits
        if label_required_splits is None
        else set(label_required_splits)
    )
    if train_split_name not in required_label_splits:
        raise ValueError("训练分段必须属于label_required_splits")
    if required_label_splits & optional_label_splits:
        raise ValueError("label_required_splits 与 allow_missing_label_splits 不得重叠")
    unknown = (required_label_splits | optional_label_splits) - segment_names
    if unknown:
        raise ValueError(f"标签用途配置含未知split: {sorted(unknown)}")
    unassigned = segment_names - (required_label_splits | optional_label_splits)
    if unassigned:
        raise ValueError(f"以下split未声明标签用途: {sorted(unassigned)}")

    boundary_eligible = samples["split"].notna()
    signal_eligible = samples["eligible_signal"].fillna(False)
    label_eligible = samples["label_valid"].fillna(False)
    label_required = samples["split"].isin(required_label_splits)
    label_optional = samples["split"].isin(optional_label_splits)
    usage_eligible = label_required | label_optional
    final_mask = (
        boundary_eligible
        & signal_eligible
        & usage_eligible
        & (label_eligible | label_optional)
    )
    samples = samples.loc[final_mask].copy()
    if samples.empty:
        raise ValueError("按边界、股票池和标签约束后没有可用样本")
    required_samples = samples.loc[samples["split"].isin(required_label_splits)]
    if required_samples["label"].isna().any():
        raise AssertionError("训练/验证用途样本不得含缺失label")

    split_start = {segment.name: segment.start for segment in segments}
    samples["split_start"] = samples["split"].map(split_start)
    samples["window_pre_split"] = samples["window_start_date"] < samples["split_start"]
    samples = attach_entry_tradability(samples, suspend_status, limit_status)

    train_samples = samples.loc[samples["split"] == train_split_name]
    if train_samples.empty:
        raise ValueError(f"训练分段 {train_split_name} 没有可用样本")
    fit_mask = _rows_used_by_windows(
        len(feature_panel),
        train_samples["panel_row_start"].to_numpy(),
        train_samples["panel_row_end"].to_numpy(),
    )
    preprocessor = fit_feature_preprocessor(
        feature_panel,
        feature_columns=feature_columns,
        fit_mask=fit_mask,
        lower_quantile=lower_quantile,
        upper_quantile=upper_quantile,
        std_epsilon=std_epsilon,
    )
    transformed = transform_features(feature_panel, preprocessor)
    if not np.isfinite(transformed.loc[:, feature_columns].to_numpy()).all():
        raise ValueError("标准化后特征仍含 NaN 或无穷值")

    split_quality = (
        samples.groupby("split", observed=True)
        .agg(
            signal_start=("date", "min"),
            signal_end=("date", "max"),
            label_missing_count=("label", lambda values: int(values.isna().sum())),
            label_missing_rate=("label", lambda values: float(values.isna().mean())),
            window_pre_split_count=("window_pre_split", "sum"),
        )
        .reset_index()
    )
    quality_summary: dict[str, Any] = {
        "panel_rows": len(panel),
        "complete_feature_rows": len(feature_panel),
        "complete_window_candidates": candidate_count,
        "boundary_excluded": int((~boundary_eligible).sum()),
        "signal_universe_excluded": int((boundary_eligible & ~signal_eligible).sum()),
        "invalid_label_excluded": int(
            (boundary_eligible & signal_eligible & label_required & ~label_eligible).sum()
        ),
        "missing_label_prediction_samples": int(samples["label"].isna().sum()),
        "final_samples": len(samples),
        "train_fit_rows": int(fit_mask.sum()),
        "entry_untradable_samples": int((~samples["entry_tradable"]).sum()),
        "raw_feature_missing_rate": raw_feature_missing_rate,
        "split_quality": split_quality.to_dict(orient="records"),
    }
    return PreparedMLData(
        feature_panel=transformed,
        samples=samples.sort_values(["split", "date", "stock_code"]).reset_index(drop=True),
        feature_columns=feature_columns,
        preprocessor=preprocessor,
        quality_summary=quality_summary,
    )


@dataclass
class RegressionBatchResult:
    """一次固定特征集合的多模型训练与样本外预测结果。"""

    predictions: pd.DataFrame
    model_audit: pd.DataFrame
    fitted_models: dict[str, Any]


def _finite_row_mask(frame: pd.DataFrame, columns: Sequence[str]) -> np.ndarray:
    """返回指定数值列全部有限的逐行掩码。"""
    values = frame.loc[:, list(columns)].apply(
        pd.to_numeric,
        errors="coerce",
    )
    return np.isfinite(
        values.to_numpy(dtype=np.float64, na_value=np.nan)
    ).all(axis=1)


def fit_regression_model_batch(
    training_frame: pd.DataFrame,
    prediction_frame: pd.DataFrame,
    *,
    feature_columns: Sequence[str],
    target_column: str,
    model_factories: Mapping[str, Callable[[], Any]],
    prediction_key_columns: Sequence[str],
    training_date_column: str,
    prediction_date_column: str,
) -> RegressionBatchResult:
    """在一个固定特征集合上拟合多个回归器并预测。

    训练与预测分别执行 complete-case，不填补。为了让带截距 OLS 至少可
    识别，完整训练样本数必须不小于 ``特征数 + 1``；不满足时所有模型均
    明确标为 ``skipped_insufficient_training_samples``。训练日期最大值
    必须严格早于预测日期最小值，违反时直接中止，不能降级为警告。
    """
    features = tuple(str(column) for column in feature_columns)
    keys = tuple(str(column) for column in prediction_key_columns)
    if not features:
        raise ValueError("固定特征集合不得为空")
    if len(set(features)) != len(features):
        raise ValueError("固定特征集合存在重复列")
    if not model_factories:
        raise ValueError("model_factories 不得为空")
    _require_columns(
        training_frame,
        (*features, target_column, training_date_column),
        "滚动回归训练表",
    )
    _require_columns(
        prediction_frame,
        (*features, *keys, prediction_date_column),
        "滚动回归预测表",
    )

    train_dates = pd.to_datetime(
        training_frame[training_date_column],
        errors="raise",
    ).dt.normalize()
    predict_dates = pd.to_datetime(
        prediction_frame[prediction_date_column],
        errors="raise",
    ).dt.normalize()
    if len(train_dates) and len(predict_dates):
        if not train_dates.max() < predict_dates.min():
            raise AssertionError("滚动模型训练日期未严格早于预测日期")

    training_mask = _finite_row_mask(
        training_frame,
        (*features, target_column),
    )
    prediction_mask = _finite_row_mask(prediction_frame, features)
    training_complete = training_frame.loc[training_mask].copy()
    prediction_complete = prediction_frame.loc[prediction_mask].copy()
    required_training_rows = len(features) + 1
    common_audit = {
        "feature_count": len(features),
        "training_input_rows": len(training_frame),
        "training_complete_rows": len(training_complete),
        "training_dropped_rows": int((~training_mask).sum()),
        "required_training_rows": required_training_rows,
        "training_fit_start": (
            train_dates.loc[training_mask].min()
            if training_mask.any()
            else pd.NaT
        ),
        "training_fit_end": (
            train_dates.loc[training_mask].max()
            if training_mask.any()
            else pd.NaT
        ),
        "prediction_input_rows": len(prediction_frame),
        "prediction_complete_rows": len(prediction_complete),
        "prediction_missing_rows": int((~prediction_mask).sum()),
        "prediction_start": (
            predict_dates.loc[prediction_mask].min()
            if prediction_mask.any()
            else pd.NaT
        ),
        "prediction_end": (
            predict_dates.loc[prediction_mask].max()
            if prediction_mask.any()
            else pd.NaT
        ),
        "fit_end_strictly_before_prediction": bool(
            not training_mask.any()
            or not prediction_mask.any()
            or train_dates.loc[training_mask].max()
            < predict_dates.loc[prediction_mask].min()
        ),
    }
    skipped_status: str | None = None
    if len(training_complete) < required_training_rows:
        skipped_status = "skipped_insufficient_training_samples"
    elif prediction_complete.empty:
        skipped_status = "skipped_no_complete_prediction_rows"

    audit_rows: list[dict[str, Any]] = []
    fitted_models: dict[str, Any] = {}
    prediction_parts: list[pd.DataFrame] = []
    if skipped_status is not None:
        for model_name in model_factories:
            audit_rows.append(
                {
                    **common_audit,
                    "model": str(model_name),
                    "estimator_class": pd.NA,
                    "status": skipped_status,
                    "error_type": pd.NA,
                    "error_message": pd.NA,
                    "transaction_status": skipped_status,
                    "failed_models": pd.NA,
                }
            )
        return RegressionBatchResult(
            predictions=pd.DataFrame(
                columns=[*keys, "model", "prediction"]
            ),
            model_audit=pd.DataFrame(audit_rows),
            fitted_models=fitted_models,
        )

    x_train = training_complete.loc[:, features].to_numpy(
        dtype=np.float64,
        copy=True,
    )
    y_train = pd.to_numeric(
        training_complete[target_column],
        errors="raise",
    ).to_numpy(dtype=np.float64, copy=True)
    x_predict = prediction_complete.loc[:, features].to_numpy(
        dtype=np.float64,
        copy=True,
    )
    for model_name, factory in model_factories.items():
        estimator: Any | None = None
        try:
            estimator = factory()
            if not all(
                callable(getattr(estimator, method, None))
                for method in ("fit", "predict", "get_params")
            ):
                raise TypeError("模型工厂必须返回兼容 sklearn 的回归器")
            estimator.fit(x_train, y_train)
            prediction = np.asarray(estimator.predict(x_predict), dtype=np.float64)
            if prediction.shape != (len(prediction_complete),):
                raise ValueError("模型预测结果不是一维逐样本数组")
            if not np.isfinite(prediction).all():
                raise ValueError("模型预测包含 NaN 或无穷值")
        except Exception as exc:  # noqa: BLE001 - 失败必须逐模型落审计
            audit_rows.append(
                {
                    **common_audit,
                    "model": str(model_name),
                    "estimator_class": (
                        f"{type(estimator).__module__}.{type(estimator).__qualname__}"
                        if estimator is not None
                        else pd.NA
                    ),
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                }
            )
            continue
        fitted_models[str(model_name)] = estimator
        part = prediction_complete.loc[:, keys].reset_index(drop=True)
        part["model"] = str(model_name)
        part["prediction"] = prediction
        prediction_parts.append(part)
        audit_rows.append(
            {
                **common_audit,
                "model": str(model_name),
                "estimator_class": (
                    f"{type(estimator).__module__}.{type(estimator).__qualname__}"
                ),
                "status": "fitted",
                "error_type": pd.NA,
                "error_message": pd.NA,
            }
        )
    failed_models = [
        str(row["model"]) for row in audit_rows if row["status"] == "failed"
    ]
    if failed_models:
        failed_model_text = "|".join(failed_models)
        for row in audit_rows:
            row["transaction_status"] = "rolled_back_model_failure"
            row["failed_models"] = failed_model_text
            if row["status"] == "fitted":
                row["status"] = "discarded_peer_model_failure"
        return RegressionBatchResult(
            predictions=pd.DataFrame(
                columns=[*keys, "model", "prediction"]
            ),
            model_audit=pd.DataFrame(audit_rows),
            fitted_models={},
        )
    for row in audit_rows:
        row["transaction_status"] = "committed_all_base_models"
        row["failed_models"] = pd.NA
    predictions = (
        pd.concat(prediction_parts, ignore_index=True)
        if prediction_parts
        else pd.DataFrame(columns=[*keys, "model", "prediction"])
    )
    return RegressionBatchResult(
        predictions=predictions,
        model_audit=pd.DataFrame(audit_rows),
        fitted_models=fitted_models,
    )


def append_prediction_ensembles(
    base_predictions: pd.DataFrame,
    *,
    group_columns: Sequence[str],
    base_model_names: Sequence[str],
    average_name: str,
    median_name: str,
    model_column: str = "model",
    prediction_column: str = "prediction",
) -> pd.DataFrame:
    """仅对同一观测键下八个基础模型均有效的记录追加均值和中位数。"""
    groups = tuple(str(column) for column in group_columns)
    models = tuple(str(name) for name in base_model_names)
    if len(models) != 8 or len(set(models)) != 8:
        raise ValueError("B11 集成要求八个唯一基础模型")
    _require_columns(
        base_predictions,
        (*groups, model_column, prediction_column),
        "基础模型预测",
    )
    if base_predictions.duplicated([*groups, model_column]).any():
        raise ValueError("基础预测存在重复观测键/模型")
    unknown = set(base_predictions[model_column].dropna().astype(str)) - set(models)
    if unknown:
        raise ValueError(f"基础预测含未登记模型: {sorted(unknown)}")
    finite = base_predictions.loc[
        np.isfinite(
            pd.to_numeric(
                base_predictions[prediction_column],
                errors="coerce",
            ).to_numpy(dtype=np.float64, na_value=np.nan)
        )
    ].copy()
    if finite.empty:
        return finite
    wide = finite.pivot(
        index=list(groups),
        columns=model_column,
        values=prediction_column,
    )
    complete = wide.reindex(columns=models).dropna(how="any")
    if complete.empty:
        return finite.reset_index(drop=True)
    average = complete.mean(axis=1).rename(prediction_column).reset_index()
    average[model_column] = average_name
    median = complete.median(axis=1).rename(prediction_column).reset_index()
    median[model_column] = median_name
    ordered_columns = [*groups, model_column, prediction_column]
    return pd.concat(
        [
            finite.loc[:, ordered_columns],
            average.loc[:, ordered_columns],
            median.loc[:, ordered_columns],
        ],
        ignore_index=True,
    )


def _json_safe(value: Any) -> Any:
    """递归转换为标准 JSON 可序列化值，并保留对象类型证据。"""
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if np.isfinite(value) else str(value)
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    get_params = getattr(value, "get_params", None)
    if callable(get_params):
        return {
            "estimator_class": (
                f"{type(value).__module__}.{type(value).__qualname__}"
            ),
            "params": _json_safe(get_params(deep=True)),
        }
    return {
        "python_type": f"{type(value).__module__}.{type(value).__qualname__}",
        "repr": repr(value),
    }


def snapshot_estimator_params(estimator: Any) -> dict[str, Any]:
    """全量快照 ``get_params(deep=True)``，返回可直接 JSON 序列化的字典。"""
    get_params = getattr(estimator, "get_params", None)
    if not callable(get_params):
        raise TypeError("estimator 不提供 get_params")
    return {
        "estimator_class": f"{type(estimator).__module__}.{type(estimator).__qualname__}",
        "params_deep": _json_safe(get_params(deep=True)),
    }


def extract_estimator_feature_values(
    estimator: Any,
    feature_names: Sequence[str],
    *,
    model_name: str,
) -> pd.DataFrame:
    """统一提取线性系数或树模型特征重要性；无原生权重时返回空表。"""
    features = tuple(str(name) for name in feature_names)
    value_kind: str
    if hasattr(estimator, "coef_"):
        values = np.asarray(estimator.coef_, dtype=np.float64).reshape(-1)
        value_kind = "coefficient"
    elif hasattr(estimator, "feature_importances_"):
        values = np.asarray(
            estimator.feature_importances_,
            dtype=np.float64,
        ).reshape(-1)
        value_kind = "feature_importance"
    else:
        return pd.DataFrame(
            columns=[
                "model",
                "feature",
                "value_kind",
                "value",
                "absolute_value",
                "absolute_rank",
            ]
        )
    if len(values) != len(features):
        raise ValueError(
            f"{model_name} 权重长度 {len(values)} 与特征数 {len(features)} 不一致"
        )
    result = pd.DataFrame(
        {
            "model": model_name,
            "feature": features,
            "value_kind": value_kind,
            "value": values,
        }
    )
    result["absolute_value"] = result["value"].abs()
    result["absolute_rank"] = (
        result["absolute_value"]
        .rank(method="first", ascending=False)
        .astype("int64")
    )
    return result

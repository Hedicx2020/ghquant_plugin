"""m2：时点安全的滚动跨市场二部图与逐目标预测变量。

本模块只实现 r007 报告专属的图筛边和特征映射，不包含预测模型或回测
引擎。关键约束如下：

* 图更新锚点之前恰好取最近 ``250`` 个目标交易日，锚点当日不进训练窗；
* ``US_TO_CN`` 与 ``CN_TO_US`` 直接消费 m1 已按市场时段生成的因果映射，
  分别核验 ``l=1`` 与 ``l=0``，不再按自然日二次平移；
* 每 ``10`` 个目标交易日更新，区间内复用同一图快照；
* 对每个源—目标股票对按完整样本计算一元 OLS，仅保留全部
  ``|t_beta| > 2`` 的边，不做 top-n 截断；
* 回归按源股票分块，滚动接口逐快照 yield，只保留稀疏边，避免物化
  ``股票对 × 全样本日期`` 的三维对象。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from .config import DEFAULT_CONFIG, DirectionConfig, M1Config


EDGE_COLUMNS = (
    "direction",
    "anchor_date",
    "source_market",
    "target_market",
    "source_code",
    "target_code",
    "beta",
    "beta_se",
    "t_beta",
    "n_obs",
    "fit_start",
    "fit_end",
    "threshold",
)


@dataclass(frozen=True)
class GraphBuildConfig:
    """F5 与数值防护的集中配置。

    ``training_window_days``、``graph_update_days`` 和缩尾分位数沿用
    :class:`~.config.ReturnConfig`，避免在本模块重复声明 spec 参数。
    """

    t_threshold: float = 2.0
    minimum_observations: int = 3
    source_block_size: int = 64
    variance_epsilon: float = field(
        default_factory=lambda: float(np.finfo(np.float64).eps)
    )
    residual_variance_epsilon: float = field(
        default_factory=lambda: float(np.finfo(np.float64).eps)
    )
    indegree_quantiles: tuple[float, ...] = (0.25, 0.50, 0.75)
    dense_matrix_max_cells: int = 1_000_000

    def __post_init__(self) -> None:
        if not np.isfinite(self.t_threshold) or self.t_threshold <= 0:
            raise ValueError("t_threshold 必须为正的有限数")
        if self.minimum_observations < 3:
            raise ValueError("minimum_observations 至少为 3，以保证 n-2 > 0")
        if self.source_block_size <= 0:
            raise ValueError("source_block_size 必须为正整数")
        if self.variance_epsilon < 0 or self.residual_variance_epsilon < 0:
            raise ValueError("数值方差容差不得为负")
        if (
            not self.indegree_quantiles
            or any(not 0.0 <= value <= 1.0 for value in self.indegree_quantiles)
        ):
            raise ValueError("入度分位点必须落在 [0, 1]")
        if self.dense_matrix_max_cells <= 0:
            raise ValueError("dense_matrix_max_cells 必须为正整数")


DEFAULT_GRAPH_CONFIG = GraphBuildConfig()


@dataclass(frozen=True)
class UpdateBlock:
    """一个图更新锚点及其复用的目标预测日。"""

    anchor_date: pd.Timestamp
    prediction_dates: tuple[pd.Timestamp, ...]

    def __post_init__(self) -> None:
        anchor = pd.Timestamp(self.anchor_date).normalize()
        dates = tuple(pd.Timestamp(value).normalize() for value in self.prediction_dates)
        if not dates:
            raise ValueError("UpdateBlock.prediction_dates 不得为空")
        if dates[0] != anchor:
            raise ValueError("更新锚点必须等于本区间首个目标预测日")
        if any(current <= previous for previous, current in zip(dates, dates[1:])):
            raise ValueError("prediction_dates 必须严格递增且不重复")
        object.__setattr__(self, "anchor_date", anchor)
        object.__setattr__(self, "prediction_dates", dates)


@dataclass(frozen=True)
class SparseBiadjacency:
    """只保存过阈值边的稀疏二邻接矩阵。

    行对应源市场股票，列对应目标市场股票，元素为带符号 ``t_beta``。
    """

    source_codes: tuple[str, ...]
    target_codes: tuple[str, ...]
    row_indices: np.ndarray
    column_indices: np.ndarray
    values: np.ndarray

    def __post_init__(self) -> None:
        rows = np.asarray(self.row_indices, dtype=np.int64)
        columns = np.asarray(self.column_indices, dtype=np.int64)
        values = np.asarray(self.values, dtype=np.float64)
        if not (rows.ndim == columns.ndim == values.ndim == 1):
            raise ValueError("稀疏矩阵坐标和值必须是一维数组")
        if not (len(rows) == len(columns) == len(values)):
            raise ValueError("稀疏矩阵坐标和值长度不一致")
        if len(rows):
            if rows.min() < 0 or rows.max() >= len(self.source_codes):
                raise IndexError("稀疏矩阵源节点坐标越界")
            if columns.min() < 0 or columns.max() >= len(self.target_codes):
                raise IndexError("稀疏矩阵目标节点坐标越界")
            if not np.isfinite(values).all():
                raise ValueError("稀疏矩阵边权包含非有限值")
        rows.setflags(write=False)
        columns.setflags(write=False)
        values.setflags(write=False)
        object.__setattr__(self, "row_indices", rows)
        object.__setattr__(self, "column_indices", columns)
        object.__setattr__(self, "values", values)

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.source_codes), len(self.target_codes)

    @property
    def nnz(self) -> int:
        return len(self.values)

    def to_scipy_csr(self) -> Any:
        """按需转为 SciPy CSR；模块导入时不强制加载 SciPy。"""
        from scipy import sparse

        return sparse.csr_matrix(
            (self.values, (self.row_indices, self.column_indices)),
            shape=self.shape,
        )

    def to_dense_frame(
        self,
        *,
        max_cells: int = DEFAULT_GRAPH_CONFIG.dense_matrix_max_cells,
    ) -> pd.DataFrame:
        """仅在显式规模上限内展开稠密矩阵，防止误分配超大内存。"""
        cells = self.shape[0] * self.shape[1]
        if cells > max_cells:
            raise MemoryError(
                f"二邻接矩阵共有 {cells} 个单元，超过显式上限 {max_cells}"
            )
        values = np.zeros(self.shape, dtype=np.float64)
        values[self.row_indices, self.column_indices] = self.values
        return pd.DataFrame(
            values,
            index=pd.Index(self.source_codes, name="source_code"),
            columns=pd.Index(self.target_codes, name="target_code"),
        )


@dataclass(frozen=True)
class GraphSnapshot:
    """单方向、单锚点的稀疏图、特征映射与审计证据。"""

    direction: str
    source_market: str
    target_market: str
    lag_parameter: int
    anchor_date: pd.Timestamp
    prediction_dates: tuple[pd.Timestamp, ...]
    training_mapping: pd.DataFrame
    prediction_mapping: pd.DataFrame
    edges: pd.DataFrame
    adjacency: SparseBiadjacency
    feature_mapping: pd.DataFrame
    indegree: pd.DataFrame
    indegree_quantiles: pd.DataFrame
    graph_audit: pd.DataFrame
    daily_feature_audit: pd.DataFrame


@dataclass(frozen=True)
class TargetFeatureBatch:
    """一个目标股票在一个图快照下的训练与预测变量。

    训练表含 ``target_value``，且已执行 AS2 的逐目标—特征完整样本删除；
    预测表不附实际目标收益，只以 ``predictor_complete`` 标识能否交给 m3。
    """

    direction: str
    anchor_date: pd.Timestamp
    target_code: str
    feature_columns: tuple[str, ...]
    feature_lookup: pd.DataFrame
    training_frame: pd.DataFrame
    prediction_frame: pd.DataFrame
    winsor_limits: pd.DataFrame
    audit: pd.DataFrame


@dataclass(frozen=True)
class TargetFeatureMatrices:
    """同一源/目标面板的数值矩阵缓存，供多个目标与快照只读复用。"""

    source: pd.DataFrame
    target: pd.DataFrame


def _require_columns(
    frame: pd.DataFrame,
    required: Sequence[str],
    context: str,
) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise KeyError(f"{context} 缺少字段: {missing}")


def _normalize_panel(
    panel: pd.DataFrame,
    *,
    value_column: str,
    context: str,
) -> pd.DataFrame:
    _require_columns(panel, ("stock_code", "date", value_column), context)
    result = panel.loc[:, ["stock_code", "date", value_column]].copy()
    result["stock_code"] = result["stock_code"].astype("string")
    result["date"] = pd.to_datetime(result["date"], errors="raise").dt.normalize()
    if result.duplicated(["stock_code", "date"]).any():
        duplicate_count = int(
            result.duplicated(["stock_code", "date"], keep=False).sum()
        )
        raise ValueError(f"{context} 存在 {duplicate_count} 行重复 stock_code/date 键")
    result[value_column] = pd.to_numeric(
        result[value_column], errors="coerce"
    ).replace([np.inf, -np.inf], np.nan)
    return result


def _pivot_panel(
    panel: pd.DataFrame,
    *,
    value_column: str,
    context: str,
) -> pd.DataFrame:
    normalized = _normalize_panel(
        panel,
        value_column=value_column,
        context=context,
    )
    pivot = normalized.pivot(
        index="date",
        columns="stock_code",
        values=value_column,
    )
    pivot.index = pd.DatetimeIndex(pivot.index).normalize()
    return pivot.sort_index().sort_index(axis="columns")


def prepare_target_feature_matrices(
    source_panel: pd.DataFrame,
    target_panel: pd.DataFrame,
    *,
    source_value_column: str = "pvclcl_excess",
    target_value_column: str = "opcl_excess",
) -> TargetFeatureMatrices:
    """一次性规范化并展开特征/标签矩阵，避免逐目标重复 pivot 全市场。"""
    return TargetFeatureMatrices(
        source=_pivot_panel(
            source_panel,
            value_column=source_value_column,
            context="逐目标源市场特征面板",
        ),
        target=_pivot_panel(
            target_panel,
            value_column=target_value_column,
            context="逐目标目标市场标签面板",
        ),
    )


def _direction_mapping(
    calendar_mapping: pd.DataFrame,
    *,
    direction: DirectionConfig,
) -> pd.DataFrame:
    required = (
        "direction",
        "source_market",
        "target_market",
        "lag_parameter",
        "target_date",
        "source_date",
        "causal_available",
    )
    _require_columns(calendar_mapping, required, "因果日历映射")
    mapping = calendar_mapping.loc[
        calendar_mapping["direction"].astype("string").eq(direction.name)
    ].copy()
    if mapping.empty:
        raise ValueError(f"因果日历映射没有方向 {direction.name}")
    expected_values = {
        "source_market": direction.source_market,
        "target_market": direction.target_market,
        "lag_parameter": direction.lag_parameter,
    }
    for column, expected in expected_values.items():
        observed = set(mapping[column].dropna().tolist())
        if observed != {expected}:
            raise ValueError(
                f"{direction.name} 的 {column} 应为 {expected!r}，实际为 {observed}"
            )
    mapping["target_date"] = pd.to_datetime(
        mapping["target_date"], errors="raise"
    ).dt.normalize()
    mapping["source_date"] = pd.to_datetime(
        mapping["source_date"], errors="coerce"
    ).dt.normalize()
    mapping["causal_available"] = (
        mapping["causal_available"].astype("boolean").fillna(False)
    )
    if mapping.duplicated("target_date").any():
        duplicate_count = int(mapping.duplicated("target_date", keep=False).sum())
        raise ValueError(
            f"{direction.name} 因果映射存在 {duplicate_count} 行重复 target_date"
        )
    mapping = mapping.sort_values("target_date").reset_index(drop=True)
    available_without_date = mapping["causal_available"] & mapping["source_date"].isna()
    if available_without_date.any():
        raise ValueError("causal_available=True 但 source_date 缺失")
    if {"source_close_utc", "target_open_utc"}.issubset(mapping.columns):
        source_close = pd.to_datetime(mapping["source_close_utc"], errors="coerce", utc=True)
        target_open = pd.to_datetime(mapping["target_open_utc"], errors="coerce", utc=True)
        violation = mapping["causal_available"] & source_close.ge(target_open)
        if violation.any():
            raise AssertionError("因果映射包含源市场收盘不早于目标开盘的记录")
    return mapping


def build_update_blocks(
    direction_mapping: pd.DataFrame,
    *,
    prediction_start: str | pd.Timestamp,
    prediction_end: str | pd.Timestamp,
    update_days: int,
) -> tuple[UpdateBlock, ...]:
    """按 AS6 从目标预测期首日起每 ``update_days`` 个交易日切块。"""
    _require_columns(direction_mapping, ("target_date",), "单方向日历映射")
    if update_days <= 0:
        raise ValueError("update_days 必须为正整数")
    start = pd.Timestamp(prediction_start).normalize()
    end = pd.Timestamp(prediction_end).normalize()
    if start > end:
        raise ValueError("prediction_start 晚于 prediction_end")
    dates = (
        pd.to_datetime(direction_mapping["target_date"], errors="raise")
        .dt.normalize()
        .drop_duplicates()
        .sort_values()
    )
    dates = dates.loc[dates.between(start, end)].tolist()
    if not dates:
        raise ValueError(f"目标预测区间 {start.date()}–{end.date()} 没有交易日")
    return tuple(
        UpdateBlock(
            anchor_date=pd.Timestamp(dates[start_index]),
            prediction_dates=tuple(
                pd.Timestamp(value)
                for value in dates[start_index : start_index + update_days]
            ),
        )
        for start_index in range(0, len(dates), update_days)
    )


def select_training_mapping(
    direction_mapping: pd.DataFrame,
    *,
    anchor_date: str | pd.Timestamp,
    window_days: int,
) -> pd.DataFrame:
    """选取严格早于锚点的最近 ``window_days`` 个目标交易日。"""
    _require_columns(
        direction_mapping,
        ("target_date", "source_date", "causal_available"),
        "单方向训练日历映射",
    )
    if window_days <= 0:
        raise ValueError("window_days 必须为正整数")
    anchor = pd.Timestamp(anchor_date).normalize()
    historical = direction_mapping.loc[
        pd.to_datetime(
            direction_mapping["target_date"], errors="raise"
        ).dt.normalize().lt(anchor)
    ].tail(window_days).copy()
    if len(historical) != window_days:
        raise ValueError(
            f"锚点 {anchor.date()} 前仅有 {len(historical)} 个目标交易日，"
            f"不足 B5 要求的 {window_days} 日"
        )
    if not historical["target_date"].lt(anchor).all():
        raise AssertionError("训练映射包含锚点当日或未来目标日期")
    if historical["target_date"].duplicated().any():
        raise ValueError("训练映射包含重复目标交易日")
    return historical.reset_index(drop=True)


def _winsorize_matrix(
    values: pd.DataFrame,
    *,
    lower_quantile: float,
    upper_quantile: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """只用输入训练矩阵逐股票拟合并应用 AS5 分位缩尾。"""
    finite = values.replace([np.inf, -np.inf], np.nan).apply(
        pd.to_numeric,
        errors="coerce",
    )
    lower = finite.quantile(lower_quantile)
    upper = finite.quantile(upper_quantile)
    clipped = finite.clip(lower=lower, upper=upper, axis="columns")
    limits = pd.DataFrame(
        {
            "stock_code": finite.columns.astype("string"),
            "winsor_lower": lower.to_numpy(dtype=np.float64, na_value=np.nan),
            "winsor_upper": upper.to_numpy(dtype=np.float64, na_value=np.nan),
            "observation_count": finite.notna().sum().to_numpy(dtype=np.int64),
        }
    )
    return clipped, limits


def calculate_pairwise_ols_edges(
    source_values: pd.DataFrame,
    target_values: pd.DataFrame,
    *,
    direction: DirectionConfig,
    anchor_date: str | pd.Timestamp,
    fit_start: str | pd.Timestamp,
    fit_end: str | pd.Timestamp,
    graph_config: GraphBuildConfig = DEFAULT_GRAPH_CONFIG,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """分块向量化计算全部一元 OLS，并仅返回 ``|t_beta|`` 过阈值边。

    缺失值按 AS2 对每个股票对取完整样本。函数不保存未入选股票对明细，
    只返回聚合防护计数，内存复杂度由一个源块与全部目标节点决定。
    """
    if len(source_values) != len(target_values):
        raise ValueError("源与目标训练矩阵行数不一致")
    if not source_values.index.equals(target_values.index):
        raise ValueError("源与目标训练矩阵必须使用相同目标交易日索引")
    source_codes = tuple(str(value) for value in source_values.columns)
    target_codes = tuple(str(value) for value in target_values.columns)
    if not source_codes or not target_codes:
        raise ValueError("源或目标股票集合为空")

    x_all = source_values.to_numpy(dtype=np.float64, na_value=np.nan)
    y_all = target_values.to_numpy(dtype=np.float64, na_value=np.nan)
    valid_y = np.isfinite(y_all)
    y_filled = np.where(valid_y, y_all, 0.0)
    valid_y_float = valid_y.astype(np.float64)
    y_squared = y_filled * y_filled

    selected_blocks: list[pd.DataFrame] = []
    counters = {
        "candidate_pairs": len(source_codes) * len(target_codes),
        "sufficient_sample_pairs": 0,
        "insufficient_sample_pairs": 0,
        "zero_source_variance_pairs": 0,
        "zero_residual_variance_pairs": 0,
        "nonfinite_statistic_pairs": 0,
        "selected_edges": 0,
    }
    for block_start in range(0, len(source_codes), graph_config.source_block_size):
        block_stop = min(
            block_start + graph_config.source_block_size,
            len(source_codes),
        )
        x = x_all[:, block_start:block_stop]
        valid_x = np.isfinite(x)
        x_filled = np.where(valid_x, x, 0.0)
        valid_x_float = valid_x.astype(np.float64)

        n_obs = valid_x_float.T @ valid_y_float
        sum_x = x_filled.T @ valid_y_float
        sum_y = valid_x_float.T @ y_filled
        sum_xx = (x_filled * x_filled).T @ valid_y_float
        sum_yy = valid_x_float.T @ y_squared
        sum_xy = x_filled.T @ y_filled

        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            sxx = sum_xx - (sum_x * sum_x) / n_obs
            syy = sum_yy - (sum_y * sum_y) / n_obs
            sxy = sum_xy - (sum_x * sum_y) / n_obs
            sufficient = n_obs >= graph_config.minimum_observations
            source_variable = sufficient & np.isfinite(sxx) & (
                sxx > graph_config.variance_epsilon
            )
            beta = np.divide(
                sxy,
                sxx,
                out=np.full_like(sxy, np.nan),
                where=source_variable,
            )
            sse = np.maximum(syy - beta * sxy, 0.0)
            degrees_of_freedom = n_obs - 2.0
            residual_variance = np.divide(
                sse,
                degrees_of_freedom,
                out=np.full_like(sse, np.nan),
                where=source_variable & (degrees_of_freedom > 0),
            )
            residual_variable = source_variable & np.isfinite(residual_variance) & (
                residual_variance > graph_config.residual_variance_epsilon
            )
            beta_se = np.sqrt(
                np.divide(
                    residual_variance,
                    sxx,
                    out=np.full_like(sxx, np.nan),
                    where=residual_variable,
                )
            )
            t_beta = np.divide(
                beta,
                beta_se,
                out=np.full_like(beta, np.nan),
                where=residual_variable & (beta_se > 0),
            )

        finite_stat = np.isfinite(beta) & np.isfinite(beta_se) & np.isfinite(t_beta)
        selected = finite_stat & (np.abs(t_beta) > graph_config.t_threshold)
        counters["sufficient_sample_pairs"] += int(sufficient.sum())
        counters["insufficient_sample_pairs"] += int((~sufficient).sum())
        counters["zero_source_variance_pairs"] += int(
            (sufficient & ~source_variable).sum()
        )
        counters["zero_residual_variance_pairs"] += int(
            (source_variable & ~residual_variable).sum()
        )
        counters["nonfinite_statistic_pairs"] += int(
            (residual_variable & ~finite_stat).sum()
        )
        counters["selected_edges"] += int(selected.sum())

        source_positions, target_positions = np.nonzero(selected)
        if len(source_positions):
            selected_blocks.append(
                pd.DataFrame(
                    {
                        "direction": direction.name,
                        "anchor_date": pd.Timestamp(anchor_date).normalize(),
                        "source_market": direction.source_market,
                        "target_market": direction.target_market,
                        "source_code": [
                            source_codes[block_start + position]
                            for position in source_positions
                        ],
                        "target_code": [
                            target_codes[position] for position in target_positions
                        ],
                        "beta": beta[source_positions, target_positions],
                        "beta_se": beta_se[source_positions, target_positions],
                        "t_beta": t_beta[source_positions, target_positions],
                        "n_obs": n_obs[
                            source_positions, target_positions
                        ].astype(np.int64),
                        "fit_start": pd.Timestamp(fit_start).normalize(),
                        "fit_end": pd.Timestamp(fit_end).normalize(),
                        "threshold": graph_config.t_threshold,
                    }
                )
            )

    edges = (
        pd.concat(selected_blocks, ignore_index=True)
        if selected_blocks
        else pd.DataFrame(columns=EDGE_COLUMNS)
    )
    edges = edges.loc[:, EDGE_COLUMNS]
    audit = pd.DataFrame(
        [
            {
                **counters,
                "direction": direction.name,
                "anchor_date": pd.Timestamp(anchor_date).normalize(),
                "source_count": len(source_codes),
                "target_count": len(target_codes),
                "minimum_observations": graph_config.minimum_observations,
                "t_threshold": graph_config.t_threshold,
                "source_block_size": graph_config.source_block_size,
            }
        ]
    )
    return edges, audit


def build_sparse_biadjacency(
    edges: pd.DataFrame,
    *,
    source_codes: Sequence[str],
    target_codes: Sequence[str],
) -> SparseBiadjacency:
    """由稀疏边表构造行=源、列=目标、权重=t统计量的二邻接矩阵。"""
    _require_columns(edges, ("source_code", "target_code", "t_beta"), "稀疏边表")
    sources = tuple(str(value) for value in source_codes)
    targets = tuple(str(value) for value in target_codes)
    source_positions = {code: position for position, code in enumerate(sources)}
    target_positions = {code: position for position, code in enumerate(targets)}
    if len(source_positions) != len(sources) or len(target_positions) != len(targets):
        raise ValueError("源或目标股票代码存在重复")
    rows = edges["source_code"].astype("string").map(source_positions)
    columns = edges["target_code"].astype("string").map(target_positions)
    if rows.isna().any() or columns.isna().any():
        raise KeyError("边表包含不在指定节点集合中的代码")
    if edges.duplicated(["source_code", "target_code"]).any():
        raise ValueError("稀疏边表包含重复源—目标股票对")
    return SparseBiadjacency(
        source_codes=sources,
        target_codes=targets,
        row_indices=rows.to_numpy(dtype=np.int64),
        column_indices=columns.to_numpy(dtype=np.int64),
        values=pd.to_numeric(
            edges["t_beta"], errors="coerce"
        ).to_numpy(dtype=np.float64),
    )


def summarize_target_indegree(
    edges: pd.DataFrame,
    *,
    direction: str,
    anchor_date: str | pd.Timestamp,
    target_codes: Sequence[str],
    quantiles: Sequence[float] = DEFAULT_GRAPH_CONFIG.indegree_quantiles,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """对全部目标节点（含零入度节点）计算入度及 25/50/75 分位数。"""
    targets = tuple(str(value) for value in target_codes)
    counts = (
        edges.groupby("target_code", observed=True).size()
        if not edges.empty
        else pd.Series(dtype="int64")
    )
    degrees = pd.Series(
        [int(counts.get(code, 0)) for code in targets],
        index=pd.Index(targets, name="target_code"),
        dtype="int64",
        name="in_degree",
    )
    indegree = degrees.reset_index()
    indegree.insert(0, "anchor_date", pd.Timestamp(anchor_date).normalize())
    indegree.insert(0, "direction", direction)
    summary: dict[str, Any] = {
        "direction": direction,
        "anchor_date": pd.Timestamp(anchor_date).normalize(),
        "target_count": len(targets),
        "no_inbound_target_count": int(degrees.eq(0).sum()),
        "mean_in_degree": float(degrees.mean()) if len(degrees) else np.nan,
        "max_in_degree": int(degrees.max()) if len(degrees) else 0,
    }
    for quantile in quantiles:
        label = f"in_degree_q{int(round(float(quantile) * 100)):02d}"
        summary[label] = (
            float(degrees.quantile(float(quantile))) if len(degrees) else np.nan
        )
    return indegree, pd.DataFrame([summary])


def build_feature_mapping(
    edges: pd.DataFrame,
    *,
    direction: str,
    anchor_date: str | pd.Timestamp,
    target_codes: Sequence[str],
) -> pd.DataFrame:
    """按 AS14 为每个目标映射全部过阈值源节点，不排序截断。"""
    grouped: Mapping[str, tuple[str, ...]]
    if edges.empty:
        grouped = {}
    else:
        grouped = {
            str(target): tuple(
                sorted(group["source_code"].astype("string").tolist())
            )
            for target, group in edges.groupby("target_code", observed=True)
        }
    rows = [
        {
            "direction": direction,
            "anchor_date": pd.Timestamp(anchor_date).normalize(),
            "target_code": str(target),
            "source_codes": grouped.get(str(target), ()),
            "feature_count": len(grouped.get(str(target), ())),
            "has_predictors": bool(grouped.get(str(target), ())),
            "selection_rule": "all_abs_t_beta_gt_threshold",
        }
        for target in target_codes
    ]
    return pd.DataFrame(rows)


def build_daily_feature_audit(
    feature_mapping: pd.DataFrame,
    *,
    direction: str,
    anchor_date: str | pd.Timestamp,
    prediction_dates: Sequence[str | pd.Timestamp],
    quantiles: Sequence[float] = DEFAULT_GRAPH_CONFIG.indegree_quantiles,
) -> pd.DataFrame:
    """把十日复用图展开为逐日无入边、维度和缺失预测比例审计。"""
    _require_columns(
        feature_mapping,
        ("target_code", "feature_count", "has_predictors"),
        "逐目标特征映射",
    )
    dimensions = pd.to_numeric(
        feature_mapping["feature_count"], errors="raise"
    ).astype("int64")
    target_count = len(feature_mapping)
    no_inbound = int((dimensions == 0).sum())
    base: dict[str, Any] = {
        "direction": direction,
        "anchor_date": pd.Timestamp(anchor_date).normalize(),
        "target_count": target_count,
        "targets_with_predictors": target_count - no_inbound,
        "no_inbound_target_count": no_inbound,
        "missing_prediction_count_due_to_no_edges": no_inbound,
        "missing_prediction_ratio_due_to_no_edges": (
            no_inbound / target_count if target_count else np.nan
        ),
        "feature_dimension_min": int(dimensions.min()) if target_count else 0,
        "feature_dimension_mean": (
            float(dimensions.mean()) if target_count else np.nan
        ),
        "feature_dimension_max": int(dimensions.max()) if target_count else 0,
    }
    for quantile in quantiles:
        label = f"feature_dimension_q{int(round(float(quantile) * 100)):02d}"
        base[label] = (
            float(dimensions.quantile(float(quantile)))
            if target_count
            else np.nan
        )
    return pd.DataFrame(
        [
            {
                **base,
                "prediction_date": pd.Timestamp(date).normalize(),
            }
            for date in prediction_dates
        ]
    )


def audit_snapshot_causality(
    *,
    direction: DirectionConfig,
    anchor_date: str | pd.Timestamp,
    training_mapping: pd.DataFrame,
    prediction_mapping: pd.DataFrame,
    window_days: int,
    update_days: int,
) -> pd.DataFrame:
    """汇总 B5/B6/B8 的窗口、滞后和因果可得性证据。"""
    anchor = pd.Timestamp(anchor_date).normalize()
    if len(training_mapping) != window_days:
        raise AssertionError("训练映射长度不等于配置窗口")
    if not training_mapping["target_date"].lt(anchor).all():
        raise AssertionError("训练窗包含锚点或未来目标日期")
    if len(prediction_mapping) > update_days:
        raise AssertionError("图复用区间超过配置更新频率")
    causal_count = int(training_mapping["causal_available"].fillna(False).sum())
    source_missing = int(training_mapping["source_date"].isna().sum())
    return pd.DataFrame(
        [
            {
                "direction": direction.name,
                "anchor_date": anchor,
                "source_market": direction.source_market,
                "target_market": direction.target_market,
                "lag_parameter": direction.lag_parameter,
                "training_window_days": window_days,
                "training_fit_start": training_mapping["target_date"].min(),
                "training_fit_end": training_mapping["target_date"].max(),
                "fit_end_strictly_before_anchor": bool(
                    training_mapping["target_date"].max() < anchor
                ),
                "training_causal_available_rows": causal_count,
                "training_source_date_missing_rows": source_missing,
                "graph_reuse_prediction_days": len(prediction_mapping),
                "graph_update_days": update_days,
            }
        ]
    )


def _snapshot_from_matrices(
    *,
    source_matrix: pd.DataFrame,
    target_matrix: pd.DataFrame,
    direction_mapping: pd.DataFrame,
    direction: DirectionConfig,
    block: UpdateBlock,
    config: M1Config,
    graph_config: GraphBuildConfig,
) -> GraphSnapshot:
    training_mapping = select_training_mapping(
        direction_mapping,
        anchor_date=block.anchor_date,
        window_days=config.returns.training_window_days,
    )
    prediction_mapping = direction_mapping.loc[
        direction_mapping["target_date"].isin(block.prediction_dates)
    ].copy()
    if len(prediction_mapping) != len(block.prediction_dates):
        raise ValueError("图复用预测日未全部出现在因果日历映射")
    prediction_mapping = prediction_mapping.sort_values("target_date").reset_index(
        drop=True
    )

    target_dates = pd.DatetimeIndex(training_mapping["target_date"])
    source_dates = pd.DatetimeIndex(training_mapping["source_date"])
    aligned_source = source_matrix.reindex(source_dates)
    aligned_source.index = target_dates
    aligned_target = target_matrix.reindex(target_dates)
    aligned_target.index = target_dates
    source_winsorized, _ = _winsorize_matrix(
        aligned_source,
        lower_quantile=config.returns.winsor_lower_quantile,
        upper_quantile=config.returns.winsor_upper_quantile,
    )
    target_winsorized, _ = _winsorize_matrix(
        aligned_target,
        lower_quantile=config.returns.winsor_lower_quantile,
        upper_quantile=config.returns.winsor_upper_quantile,
    )
    fit_start = target_dates.min()
    fit_end = target_dates.max()
    edges, regression_audit = calculate_pairwise_ols_edges(
        source_winsorized,
        target_winsorized,
        direction=direction,
        anchor_date=block.anchor_date,
        fit_start=fit_start,
        fit_end=fit_end,
        graph_config=graph_config,
    )
    adjacency = build_sparse_biadjacency(
        edges,
        source_codes=source_winsorized.columns.astype("string"),
        target_codes=target_winsorized.columns.astype("string"),
    )
    indegree, indegree_quantiles = summarize_target_indegree(
        edges,
        direction=direction.name,
        anchor_date=block.anchor_date,
        target_codes=target_winsorized.columns.astype("string"),
        quantiles=graph_config.indegree_quantiles,
    )
    feature_mapping = build_feature_mapping(
        edges,
        direction=direction.name,
        anchor_date=block.anchor_date,
        target_codes=target_winsorized.columns.astype("string"),
    )
    daily_feature_audit = build_daily_feature_audit(
        feature_mapping,
        direction=direction.name,
        anchor_date=block.anchor_date,
        prediction_dates=block.prediction_dates,
        quantiles=graph_config.indegree_quantiles,
    )
    causal_audit = audit_snapshot_causality(
        direction=direction,
        anchor_date=block.anchor_date,
        training_mapping=training_mapping,
        prediction_mapping=prediction_mapping,
        window_days=config.returns.training_window_days,
        update_days=config.returns.graph_update_days,
    )
    graph_audit = causal_audit.merge(
        regression_audit,
        on=["direction", "anchor_date"],
        how="inner",
        validate="one_to_one",
        suffixes=("", "_regression"),
    )
    return GraphSnapshot(
        direction=direction.name,
        source_market=direction.source_market,
        target_market=direction.target_market,
        lag_parameter=direction.lag_parameter,
        anchor_date=block.anchor_date,
        prediction_dates=block.prediction_dates,
        training_mapping=training_mapping,
        prediction_mapping=prediction_mapping,
        edges=edges,
        adjacency=adjacency,
        feature_mapping=feature_mapping,
        indegree=indegree,
        indegree_quantiles=indegree_quantiles,
        graph_audit=graph_audit,
        daily_feature_audit=daily_feature_audit,
    )


def iter_rolling_graph_snapshots(
    source_panel: pd.DataFrame,
    target_panel: pd.DataFrame,
    calendar_mapping: pd.DataFrame,
    *,
    direction: str,
    prediction_start: str | pd.Timestamp,
    prediction_end: str | pd.Timestamp,
    source_value_column: str = "pvclcl_excess",
    target_value_column: str = "opcl_excess",
    config: M1Config = DEFAULT_CONFIG,
    graph_config: GraphBuildConfig = DEFAULT_GRAPH_CONFIG,
) -> Iterator[GraphSnapshot]:
    """逐锚点流式生成单方向滚动图快照。

    只在函数开始各物化一个 ``日期 × 股票`` 收益矩阵；每个锚点的股票对
    回归结果按源节点分块计算并在 yield 后可由调用方立即写盘/释放。
    """
    direction_config = config.calendar.direction(direction)
    mapping = _direction_mapping(
        calendar_mapping,
        direction=direction_config,
    )
    source_matrix = _pivot_panel(
        source_panel,
        value_column=source_value_column,
        context=f"{direction} 源市场收益面板",
    )
    target_matrix = _pivot_panel(
        target_panel,
        value_column=target_value_column,
        context=f"{direction} 目标市场收益面板",
    )
    blocks = build_update_blocks(
        mapping,
        prediction_start=prediction_start,
        prediction_end=prediction_end,
        update_days=config.returns.graph_update_days,
    )
    for block in blocks:
        yield _snapshot_from_matrices(
            source_matrix=source_matrix,
            target_matrix=target_matrix,
            direction_mapping=mapping,
            direction=direction_config,
            block=block,
            config=config,
            graph_config=graph_config,
        )


def iter_bidirectional_rolling_graphs(
    us_panel: pd.DataFrame,
    cn_panel: pd.DataFrame,
    calendar_mapping: pd.DataFrame,
    *,
    prediction_start: str | pd.Timestamp,
    prediction_end: str | pd.Timestamp,
    source_value_column: str = "pvclcl_excess",
    target_value_column: str = "opcl_excess",
    config: M1Config = DEFAULT_CONFIG,
    graph_config: GraphBuildConfig = DEFAULT_GRAPH_CONFIG,
) -> Iterator[GraphSnapshot]:
    """依次流式生成 US→A(l=1) 与 A→US(l=0) 两方向图。"""
    panels = {"US": us_panel, "CN": cn_panel}
    for direction in config.calendar.directions:
        yield from iter_rolling_graph_snapshots(
            panels[direction.source_market],
            panels[direction.target_market],
            calendar_mapping,
            direction=direction.name,
            prediction_start=prediction_start,
            prediction_end=prediction_end,
            source_value_column=source_value_column,
            target_value_column=target_value_column,
            config=config,
            graph_config=graph_config,
        )


def materialize_target_feature_batch(
    snapshot: GraphSnapshot,
    source_panel: pd.DataFrame,
    target_panel: pd.DataFrame,
    *,
    target_code: str,
    source_value_column: str = "pvclcl_excess",
    target_value_column: str = "opcl_excess",
    prepared_matrices: TargetFeatureMatrices | None = None,
    config: M1Config = DEFAULT_CONFIG,
) -> TargetFeatureBatch:
    """按快照为单一目标股票构造可供 m3 消费的变维训练/预测表。

    源收益通过快照内的因果 ``source_date`` 映射到目标日；缩尾上下界只由
    该快照的历史训练行拟合，并原样应用于预测区间。无入边目标返回空特征，
    不以其他股票或 top-n 规则补齐。
    """
    mapping_row = snapshot.feature_mapping.loc[
        snapshot.feature_mapping["target_code"].astype("string").eq(
            str(target_code)
        )
    ]
    if len(mapping_row) != 1:
        raise KeyError(
            f"{snapshot.direction}/{snapshot.anchor_date.date()} "
            f"目标股票 {target_code} 的特征映射不存在或不唯一"
        )
    source_codes = tuple(str(value) for value in mapping_row.iloc[0]["source_codes"])
    feature_columns = tuple(f"source::{code}" for code in source_codes)
    feature_lookup = pd.DataFrame(
        {
            "feature_column": feature_columns,
            "source_code": source_codes,
        }
    )
    base_audit = {
        "direction": snapshot.direction,
        "anchor_date": snapshot.anchor_date,
        "target_code": str(target_code),
        "feature_count": len(source_codes),
        "no_inbound_target": not source_codes,
    }
    if not source_codes:
        return TargetFeatureBatch(
            direction=snapshot.direction,
            anchor_date=snapshot.anchor_date,
            target_code=str(target_code),
            feature_columns=(),
            feature_lookup=feature_lookup,
            training_frame=pd.DataFrame(
                columns=["target_date", "source_date", "target_value"]
            ),
            prediction_frame=pd.DataFrame(
                columns=["target_date", "source_date", "predictor_complete"]
            ),
            winsor_limits=pd.DataFrame(
                columns=[
                    "variable",
                    "source_code",
                    "winsor_lower",
                    "winsor_upper",
                    "observation_count",
                ]
            ),
            audit=pd.DataFrame(
                [
                    {
                        **base_audit,
                        "training_input_rows": len(snapshot.training_mapping),
                        "training_complete_rows": 0,
                        "training_dropped_rows": len(snapshot.training_mapping),
                        "prediction_rows": len(snapshot.prediction_mapping),
                        "prediction_complete_rows": 0,
                        "prediction_missing_rows": len(snapshot.prediction_mapping),
                    }
                ]
            ),
        )

    matrices = (
        prepared_matrices
        if prepared_matrices is not None
        else prepare_target_feature_matrices(
            source_panel,
            target_panel,
            source_value_column=source_value_column,
            target_value_column=target_value_column,
        )
    )
    source_matrix = matrices.source.reindex(columns=list(source_codes))
    target_series = (
        matrices.target[str(target_code)].sort_index()
        if str(target_code) in matrices.target.columns
        else pd.Series(dtype="float64")
    )

    training_mapping = snapshot.training_mapping.loc[
        :, ["target_date", "source_date"]
    ].copy()
    prediction_mapping = snapshot.prediction_mapping.loc[
        :, ["target_date", "source_date"]
    ].copy()
    training_values = source_matrix.reindex(
        pd.DatetimeIndex(training_mapping["source_date"])
    )
    training_values.index = pd.DatetimeIndex(training_mapping["target_date"])
    prediction_values = source_matrix.reindex(
        pd.DatetimeIndex(prediction_mapping["source_date"])
    )
    prediction_values.index = pd.DatetimeIndex(prediction_mapping["target_date"])
    training_values, source_limits = _winsorize_matrix(
        training_values,
        lower_quantile=config.returns.winsor_lower_quantile,
        upper_quantile=config.returns.winsor_upper_quantile,
    )
    source_limits.insert(0, "variable", "feature")
    source_limits = source_limits.rename(columns={"stock_code": "source_code"})
    source_limits["feature_column"] = [
        f"source::{code}" for code in source_limits["source_code"]
    ]
    limit_index = source_limits.set_index("source_code")
    lower = limit_index["winsor_lower"].reindex(source_codes)
    upper = limit_index["winsor_upper"].reindex(source_codes)
    prediction_values = prediction_values.replace(
        [np.inf, -np.inf], np.nan
    ).clip(lower=lower, upper=upper, axis="columns")
    training_values.columns = feature_columns
    prediction_values.columns = feature_columns

    training_target = target_series.reindex(training_values.index).replace(
        [np.inf, -np.inf], np.nan
    )
    target_lower = training_target.quantile(config.returns.winsor_lower_quantile)
    target_upper = training_target.quantile(config.returns.winsor_upper_quantile)
    training_target = training_target.clip(lower=target_lower, upper=target_upper)
    target_limits = pd.DataFrame(
        [
            {
                "variable": "target",
                "source_code": pd.NA,
                "winsor_lower": target_lower,
                "winsor_upper": target_upper,
                "observation_count": int(training_target.notna().sum()),
                "feature_column": "target_value",
            }
        ]
    )
    winsor_limits = pd.concat(
        [source_limits, target_limits],
        ignore_index=True,
        sort=False,
    )

    training_frame = pd.concat(
        [
            training_mapping.reset_index(drop=True),
            training_values.reset_index(drop=True),
        ],
        axis=1,
    )
    training_frame["target_value"] = training_target.to_numpy()
    finite_training = np.isfinite(
        training_frame.loc[
            :, [*feature_columns, "target_value"]
        ].to_numpy(dtype=np.float64, na_value=np.nan)
    ).all(axis=1)
    training_complete = training_frame.loc[finite_training].reset_index(drop=True)

    prediction_frame = pd.concat(
        [
            prediction_mapping.reset_index(drop=True),
            prediction_values.reset_index(drop=True),
        ],
        axis=1,
    )
    predictor_complete = np.isfinite(
        prediction_frame.loc[:, feature_columns].to_numpy(
            dtype=np.float64,
            na_value=np.nan,
        )
    ).all(axis=1)
    prediction_frame["predictor_complete"] = predictor_complete
    audit = pd.DataFrame(
        [
            {
                **base_audit,
                "training_input_rows": len(training_frame),
                "training_complete_rows": len(training_complete),
                "training_dropped_rows": int((~finite_training).sum()),
                "prediction_rows": len(prediction_frame),
                "prediction_complete_rows": int(predictor_complete.sum()),
                "prediction_missing_rows": int((~predictor_complete).sum()),
            }
        ]
    )
    return TargetFeatureBatch(
        direction=snapshot.direction,
        anchor_date=snapshot.anchor_date,
        target_code=str(target_code),
        feature_columns=feature_columns,
        feature_lookup=feature_lookup,
        training_frame=training_complete,
        prediction_frame=prediction_frame,
        winsor_limits=winsor_limits,
        audit=audit,
    )

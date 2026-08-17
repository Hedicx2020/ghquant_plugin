"""m1：时点安全的数据、标签与样本切分装配。

本文件只做本报告的数据源映射和审计摘要；通用特征、标签、窗口与切分逻辑
全部复用 :mod:`common.ml_pipeline`。不包含模型训练、组合回测或正式结果输出。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from common.data_loader import (
    load_limit_status,
    load_st_data,
    load_stock_price_forward,
    load_suspend_status,
    load_trade_calendar,
)
from common.ml_pipeline import (
    DateSegment,
    PreparedMLData,
    derive_forward_adjusted_vwap,
    prepare_point_in_time_ml_data,
)
from src.r002_liquid_neural_networks.config import DEFAULT_CONFIG, M1Config


@dataclass
class M1Inputs:
    """已对齐到 stock_code/date 的 m1 输入及源数据审计信息。"""

    panel: pd.DataFrame
    stock_master: pd.DataFrame
    st_intervals: pd.DataFrame
    suspend_status: pd.DataFrame
    limit_status: pd.DataFrame
    trade_calendar: pd.DataFrame
    source_summary: pd.DataFrame
    vwap_diagnostics: dict[str, float]


def _read_parquet_date_range(
    path: Path,
    columns: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """按日期下推读取大型parquet，避免加载与报告区间无关的数据。"""
    frame = pd.read_parquet(
        path,
        columns=columns,
        filters=[
            ("date", ">=", pd.Timestamp(start_date)),
            ("date", "<=", pd.Timestamp(end_date)),
        ],
    )
    frame["date"] = pd.to_datetime(frame["date"]).dt.normalize()
    return frame


def _source_record(name: str, frame: pd.DataFrame) -> dict[str, Any]:
    """生成单个输入源的行数、证券数和日期覆盖记录。"""
    record: dict[str, Any] = {"source": name, "rows": len(frame)}
    if "stock_code" in frame.columns:
        record["stocks"] = int(frame["stock_code"].nunique())
    else:
        record["stocks"] = np.nan
    date_columns = [column for column in ("date", "list_date", "implement_date") if column in frame.columns]
    if date_columns:
        dates = pd.to_datetime(frame[date_columns[0]], errors="coerce")
        record["date_start"] = dates.min()
        record["date_end"] = dates.max()
    else:
        record["date_start"] = pd.NaT
        record["date_end"] = pd.NaT
    return record


def load_m1_inputs(config: M1Config = DEFAULT_CONFIG) -> M1Inputs:
    """读取并对齐报告 m1 所需全部本地数据。

    前复权行情实际不含 ``vwap``，因此先用 ``turn_value/volume`` 推导未复权
    VWAP，按AS14配置的0.1/10.0逐行阈值断言其与未复权OHLC同量纲后，
    再乘 ``forward_close/raw_close`` 的复权比例。volume<=0或逐行不合格的
    记录不生成VWAP；全局合格率低于0.95时中止m1。
    """
    root = Path(config.data.root).expanduser()
    required_files = [
        config.data.forward_price,
        config.data.raw_price,
        config.data.trade,
        config.data.stock_master,
        config.data.st_status,
        config.data.suspend_status,
        config.data.limit_status,
        config.data.trade_calendar,
    ]
    missing = [name for name in required_files if not (root / name).is_file()]
    if missing:
        raise FileNotFoundError(f"m1 缺少本地数据文件: {missing}")

    splits = config.splits
    # 仅作上市日期缺失回退与状态缓冲；样本窗口仍由分段断言限制在2008年以后。
    start_date = str(
        (
            pd.Timestamp(splits.train_start)
            - pd.DateOffset(years=config.universe.minimum_listing_years)
        ).date()
    )
    end_date = splits.backtest_end
    forward_price = load_stock_price_forward(
        root,
        columns=["stock_code", "date", "prev_close", "open", "high", "low", "close"],
        start_date=start_date,
        end_date=end_date,
    )
    raw_price = _read_parquet_date_range(
        root / config.data.raw_price,
        ["stock_code", "date", "close", "low", "high"],
        start_date,
        end_date,
    ).rename(columns={"close": "raw_close", "low": "raw_low", "high": "raw_high"})
    trade = _read_parquet_date_range(
        root / config.data.trade,
        ["stock_code", "date", "volume", "turn_value"],
        start_date,
        end_date,
    )
    stock_master = pd.read_parquet(
        root / config.data.stock_master,
        columns=["stock_code", "list_date", "list_state"],
    )
    stock_master["list_date"] = pd.to_datetime(stock_master["list_date"], errors="coerce").dt.normalize()
    st_intervals = load_st_data(root)
    suspend_status = load_suspend_status(root, start_date=start_date)
    limit_status = load_limit_status(root, start_date=start_date)
    trade_calendar = load_trade_calendar(root, start_date=start_date, end_date=end_date)
    suspend_status = suspend_status.loc[suspend_status["date"] <= pd.Timestamp(end_date)].copy()
    limit_status = limit_status.loc[limit_status["date"] <= pd.Timestamp(end_date)].copy()

    panel = (
        forward_price.merge(raw_price, on=["stock_code", "date"], how="inner", validate="one_to_one")
        .merge(trade, on=["stock_code", "date"], how="inner", validate="one_to_one")
        .sort_values(["stock_code", "date"])
        .reset_index(drop=True)
    )
    labels = config.labels
    panel, vwap_diagnostics = derive_forward_adjusted_vwap(
        panel,
        forward_close_col="close",
        raw_close_col="raw_close",
        raw_low_col="raw_low",
        raw_high_col="raw_high",
        volume_col="volume",
        turn_value_col="turn_value",
        output_col=labels.output_column,
        sanity_min_price_ratio=labels.sanity_min_price_ratio,
        sanity_max_price_ratio=labels.sanity_max_price_ratio,
        sanity_min_fraction=labels.sanity_min_fraction,
    )

    source_summary = pd.DataFrame(
        [
            _source_record(config.data.forward_price, forward_price),
            _source_record(config.data.raw_price, raw_price),
            _source_record(config.data.trade, trade),
            _source_record(config.data.stock_master, stock_master),
            _source_record(config.data.st_status, st_intervals),
            _source_record(config.data.suspend_status, suspend_status),
            _source_record(config.data.limit_status, limit_status),
            _source_record(config.data.trade_calendar, trade_calendar),
            _source_record("inner_aligned_panel", panel),
        ]
    )
    return M1Inputs(
        panel=panel,
        stock_master=stock_master,
        st_intervals=st_intervals,
        suspend_status=suspend_status,
        limit_status=limit_status,
        trade_calendar=trade_calendar,
        source_summary=source_summary,
        vwap_diagnostics=vwap_diagnostics,
    )


def _date_segments(config: M1Config) -> tuple[DateSegment, ...]:
    splits = config.splits
    return (
        DateSegment(splits.train_name, pd.Timestamp(splits.train_start), pd.Timestamp(splits.train_end)),
        DateSegment(
            splits.validation_name,
            pd.Timestamp(splits.validation_start),
            pd.Timestamp(splits.validation_end),
        ),
        DateSegment(
            splits.backtest_name,
            pd.Timestamp(splits.backtest_start),
            pd.Timestamp(splits.backtest_end),
        ),
    )


def prepare_m1_dataset(
    inputs: M1Inputs | None = None,
    config: M1Config = DEFAULT_CONFIG,
) -> PreparedMLData:
    """构造 m1 的六通道窗口、未来收益标签和三段样本索引。"""
    source = load_m1_inputs(config) if inputs is None else inputs
    prepared = prepare_point_in_time_ml_data(
        source.panel,
        source.stock_master,
        source.st_intervals,
        source.suspend_status,
        source.limit_status,
        source.trade_calendar,
        feature_cfg=config.features.as_mapping(),
        vwap_col=config.labels.output_column,
        entry_offset=config.labels.entry_offset,
        exit_offset=config.labels.exit_offset,
        window_length=config.features.window_length,
        minimum_listing_years=config.universe.minimum_listing_years,
        segments=_date_segments(config),
        train_split_name=config.splits.train_name,
        label_required_splits=(
            config.splits.train_name,
            config.splits.validation_name,
        ),
        allow_missing_label_splits=(config.splits.backtest_name,),
        lower_quantile=config.features.winsor_lower_quantile,
        upper_quantile=config.features.winsor_upper_quantile,
        std_epsilon=config.features.std_epsilon,
    )
    prepared.quality_summary["vwap_diagnostics"] = source.vwap_diagnostics.copy()
    prepared.quality_summary["historical_list_state_policy"] = (
        "list_date_or_first_observed; current_list_state_audit_only"
    )

    train_end = pd.Timestamp(config.splits.train_end)
    if prepared.preprocessor.fit_end > train_end:
        raise AssertionError("预处理器拟合日期进入验证/回测未来区间")
    if not (prepared.samples["entry_date"] > prepared.samples["date"]).all():
        raise AssertionError("存在不晚于信号日的买入端点")
    if any(column.startswith("entry_") for column in prepared.feature_columns):
        raise AssertionError("T+1执行状态不得进入T日特征")
    required_label_splits = {
        config.splits.train_name,
        config.splits.validation_name,
    }
    required_labels = prepared.samples.loc[
        prepared.samples["split"].isin(required_label_splits), "label"
    ]
    if required_labels.isna().any():
        raise AssertionError("训练/验证样本不得含缺失label")
    for segment in _date_segments(config):
        segment_samples = prepared.samples.loc[prepared.samples["split"] == segment.name]
        if segment_samples.empty:
            continue
        for column in ("date", "entry_date", "exit_date"):
            if not segment_samples[column].between(segment.start, segment.end).all():
                raise AssertionError(f"{segment.name} 的 {column} 跨越分段边界")
        if not (segment_samples["window_start_date"] <= segment_samples["date"]).all():
            raise AssertionError(f"{segment.name} 存在晚于信号日的特征窗口")
    return prepared


def build_m1_audit_tables(
    prepared: PreparedMLData,
    inputs: M1Inputs,
) -> dict[str, pd.DataFrame]:
    """生成后续 main/verifier 可直接导出的 m1 数据审计表，不写正式结果。"""
    samples = prepared.samples.copy()
    coverage = (
        samples.groupby("split", observed=True)
        .agg(
            sample_count=("label", "size"),
            stock_count=("stock_code", "nunique"),
            signal_start=("date", "min"),
            signal_end=("date", "max"),
            entry_start=("entry_date", "min"),
            exit_end=("exit_date", "max"),
            entry_tradable_rate=("entry_tradable", "mean"),
            label_missing_count=("label", lambda values: int(values.isna().sum())),
            label_missing_rate=("label", lambda values: float(values.isna().mean())),
            window_pre_split_count=("window_pre_split", "sum"),
        )
        .reset_index()
    )
    label_distribution = (
        samples.groupby("split", observed=True)["label"]
        .agg(
            count="size",
            mean="mean",
            std="std",
            min="min",
            q01=lambda values: values.quantile(0.01),
            q50="median",
            q99=lambda values: values.quantile(0.99),
            max="max",
        )
        .reset_index()
    )
    missing_rates = pd.DataFrame(
        [
            {"feature": feature, "raw_missing_rate": rate}
            for feature, rate in prepared.quality_summary["raw_feature_missing_rate"].items()
        ]
    )
    quality_rows = []
    for metric, value in prepared.quality_summary.items():
        if isinstance(value, (dict, list, tuple, pd.DataFrame)):
            continue
        quality_rows.append({"metric": metric, "value": value})
    vwap_audit = pd.DataFrame(
        [
            {"metric": metric, "value": value}
            for metric, value in inputs.vwap_diagnostics.items()
        ]
    )
    filter_log = pd.DataFrame(
        [
            {"stage": "完整60交易日窗口候选", "excluded": 0, "remaining": prepared.quality_summary["complete_window_candidates"]},
            {"stage": "分段边界", "excluded": prepared.quality_summary["boundary_excluded"], "remaining": np.nan},
            {"stage": "信号日上市年限/ST股票池", "excluded": prepared.quality_summary["signal_universe_excluded"], "remaining": np.nan},
            {"stage": "训练/验证标签缺失", "excluded": prepared.quality_summary["invalid_label_excluded"], "remaining": prepared.quality_summary["final_samples"]},
            {"stage": "回测预测样本label缺失（保留）", "excluded": 0, "remaining": prepared.quality_summary["missing_label_prediction_samples"]},
            {"stage": "T+1不可交易（仅标记、不用于T日筛选）", "excluded": 0, "remaining": prepared.quality_summary["entry_untradable_samples"]},
        ]
    )
    return {
        "source_coverage": inputs.source_summary.copy(),
        "sample_coverage": coverage,
        "feature_preprocessor": prepared.preprocessor.to_frame(),
        "feature_missing_rate": missing_rates,
        "label_distribution": label_distribution,
        "universe_filter_log": filter_log,
        "vwap_derivation_audit": vwap_audit,
        "quality_summary": pd.DataFrame(quality_rows),
    }


# m2 仅追加受控训练包装，不修改上方 m1 数据函数。
from common.ml_pipeline import PanelWindowDataset
from common.ml_training import (
    SequenceRegressor,
    TrainingResult,
    TrainingSettings,
    build_gru_regressor,
    predict_sequence_regressor,
    train_sequence_regressor,
)
from src.r002_liquid_neural_networks.config import M2Config, M2_DEFAULT_CONFIG


@dataclass(frozen=True)
class M2DataSplits:
    """m1 交付给统一训练器的三个互斥样本段。"""

    train: PanelWindowDataset
    validation: PanelWindowDataset
    backtest: PanelWindowDataset
    backtest_metadata: pd.DataFrame


@dataclass
class M2Artifacts:
    """供后续装配导出的 GRU 训练、预测与资源记录。"""

    training: TrainingResult
    loss_curve: pd.DataFrame
    predictions: pd.DataFrame
    model_config: dict[str, Any]
    resource_summary: pd.DataFrame


def build_m2_data_splits(
    prepared: PreparedMLData,
    config: M2Config = M2_DEFAULT_CONFIG,
) -> M2DataSplits:
    """按 m1 固定分段构造统一接口，并保留回测段预测元数据。"""
    training = config.training
    split_names = (
        training.train_split,
        training.validation_split,
        training.backtest_split,
    )
    if len(set(split_names)) != len(split_names):
        raise ValueError("训练、验证和回测 split 名称必须互不相同")
    if len(prepared.feature_columns) != config.model.input_size:
        raise ValueError(
            "m1 特征通道数与 GRU input_size 不一致: "
            f"{len(prepared.feature_columns)} != {config.model.input_size}"
        )
    datasets = {name: prepared.dataset(name) for name in split_names}
    empty = [name for name, dataset in datasets.items() if len(dataset) == 0]
    if empty:
        raise ValueError(f"m2 存在空样本分段: {empty}")
    backtest_metadata = prepared.samples.loc[
        prepared.samples["split"] == training.backtest_split
    ].reset_index(drop=True).copy()
    return M2DataSplits(
        train=datasets[training.train_split],
        validation=datasets[training.validation_split],
        backtest=datasets[training.backtest_split],
        backtest_metadata=backtest_metadata,
    )


def build_gru_baseline(config: M2Config = M2_DEFAULT_CONFIG) -> SequenceRegressor:
    """按 AS2 构造单层64维 GRU 主干和线性输出头。"""
    model = config.model
    return build_gru_regressor(
        input_size=model.input_size,
        hidden_size=model.hidden_size,
        num_layers=model.num_layers,
        dropout=model.dropout,
        output_size=model.output_size,
    )


def _m2_training_settings(config: M2Config) -> TrainingSettings:
    training = config.training
    return TrainingSettings(
        batch_size=training.batch_size,
        learning_rate=training.learning_rate,
        max_epochs=training.max_epochs,
        patience=training.early_stopping_patience,
        seed=training.seed,
        loss_name=training.loss_name,
        optimizer_name=training.optimizer_name,
        weight_decay=training.weight_decay,
        min_delta=training.early_stopping_min_delta,
        num_workers=training.num_workers,
        shuffle_training=training.shuffle_training,
        device=training.device,
        deterministic_warn_only=training.deterministic_warn_only,
    )


def _gru_model_metadata(config: M2Config) -> dict[str, Any]:
    model = config.model
    training = config.training
    return {
        "model_name": "GRU",
        "input_size": model.input_size,
        "hidden_size": model.hidden_size,
        "num_layers": model.num_layers,
        "dropout": model.dropout,
        "output_size": model.output_size,
        "loss_name": training.loss_name,
        "optimizer_name": training.optimizer_name,
        "label_scope": "AS9_T+1_to_T+21_forward_adjusted_VWAP_return",
        "feature_scope": "AS10_60_day_6_channel",
        "method_scope": "degraded_open_baseline_not_report_private_parameters",
    }


def train_gru_baseline(
    prepared: PreparedMLData,
    *,
    checkpoint_path: Path,
    config: M2Config = M2_DEFAULT_CONFIG,
) -> M2Artifacts:
    """训练 GRU 并在早停完成后生成独立回测段预测。

    ``train_sequence_regressor`` 只接收训练/验证数据；回测段直到最佳验证检查点
    恢复后才传入预测函数，因此不会参与超参数或 epoch 选择。
    """
    splits = build_m2_data_splits(prepared, config)
    model_metadata = _gru_model_metadata(config)
    training_result = train_sequence_regressor(
        lambda: build_gru_baseline(config),
        train_dataset=splits.train,
        validation_dataset=splits.validation,
        settings=_m2_training_settings(config),
        checkpoint_path=Path(checkpoint_path),
        model_metadata=model_metadata,
    )
    training = config.training
    prediction_values = predict_sequence_regressor(
        training_result.model,
        dataset=splits.backtest,
        batch_size=training.batch_size,
        seed=training.seed,
        num_workers=training.num_workers,
        device=training.device,
    )
    if len(prediction_values) != len(splits.backtest_metadata):
        raise AssertionError("样本外预测数量与回测段元数据不一致")
    metadata_columns = [
        column
        for column in (
            "stock_code",
            "date",
            "label",
            "entry_date",
            "exit_date",
            "entry_tradable",
        )
        if column in splits.backtest_metadata.columns
    ]
    predictions = splits.backtest_metadata.loc[:, metadata_columns].copy()
    predictions[training.prediction_column] = prediction_values
    predictions["model"] = model_metadata["model_name"]
    resource_summary = pd.DataFrame([training_result.resource_summary])
    resource_summary.insert(0, "model", model_metadata["model_name"])
    return M2Artifacts(
        training=training_result,
        loss_curve=training_result.history.to_frame(),
        predictions=predictions,
        model_config=model_metadata,
        resource_summary=resource_summary,
    )


# m3 仅追加液态主干及统一训练包装，不修改上方 m1/m2 函数。
from common.ml_liquid import (
    LiquidModelKind,
    build_liquid_model_manifest,
    build_liquid_regressor,
)
from src.r002_liquid_neural_networks.config import (
    GRUModelConfig,
    M3Config,
    M3_DEFAULT_CONFIG,
)


def _liquid_model_spec(
    model_name: str,
    config: M3Config,
) -> tuple[LiquidModelKind, str]:
    """按集中配置解析模型类型与安全检查点文件名。"""
    matches = [
        (model_kind, checkpoint_stem)
        for configured_name, model_kind, checkpoint_stem in config.model.model_specs
        if configured_name == model_name
    ]
    if len(matches) != 1:
        raise KeyError(f"液态模型名称未唯一登记: {model_name}")
    model_kind, checkpoint_stem = matches[0]
    return model_kind, checkpoint_stem  # type: ignore[return-value]


def build_liquid_model(
    model_name: str,
    config: M3Config = M3_DEFAULT_CONFIG,
) -> SequenceRegressor:
    """按 AS11 构造指定全连接或 AutoNCP-wired 液态回归模型。"""
    model_kind, _ = _liquid_model_spec(model_name, config)
    model = config.model
    return build_liquid_regressor(
        model_kind,
        input_size=model.input_size,
        units=model.units,
        output_size=model.output_size,
        wiring_output_size=model.wiring_output_size,
        sparsity_level=model.autoncp_sparsity_level,
        wiring_seed=model.autoncp_seed,
        batch_first=model.batch_first,
        return_sequences=model.return_sequences,
        mixed_memory=model.mixed_memory,
        ode_unfolds=model.ltc_ode_unfolds,
        cfc_mode=model.cfc_mode,
    )


def build_liquid_family(
    config: M3Config = M3_DEFAULT_CONFIG,
) -> dict[str, SequenceRegressor]:
    """一次构造四类液态模型，供冒烟、manifest 与后续训练复用。"""
    return {
        model_name: build_liquid_model(model_name, config)
        for model_name, _, _ in config.model.model_specs
    }


def build_m3_model_manifest(
    config: M3Config = M3_DEFAULT_CONFIG,
) -> pd.DataFrame:
    """记录源码、commit、许可证、版本、结构和“非私参”边界。"""
    dependency = config.dependency
    model = config.model
    records = build_liquid_model_manifest(
        build_liquid_family(config),
        expected_version=dependency.package_version,
        source_url=dependency.source_url,
        source_commit=dependency.source_commit,
        source_license=dependency.source_license,
        method_scope=dependency.method_scope,
    )
    for record in records:
        record.update(
            {
                "input_size": model.input_size,
                "units": model.units,
                "prediction_output_size": model.output_size,
                "autoncp_output_size": model.wiring_output_size,
                "autoncp_sparsity_level": model.autoncp_sparsity_level,
                "autoncp_seed": model.autoncp_seed,
                "batch_first": model.batch_first,
                "return_sequences": model.return_sequences,
                "mixed_memory": model.mixed_memory,
                "ltc_ode_unfolds": model.ltc_ode_unfolds,
                "cfc_mode": model.cfc_mode,
                "label_scope": "AS9_T+1_to_T+21_forward_adjusted_VWAP_return",
                "feature_scope": "AS10_60_day_6_channel",
            }
        )
    return pd.DataFrame(records)


def _m3_comparison_config(config: M3Config) -> M2Config:
    """仅为复用 m2 分段/训练接口提供相同 input_size 与训练参数。"""
    return M2Config(
        model=GRUModelConfig(input_size=config.model.input_size),
        training=config.training,
    )


def train_liquid_model(
    prepared: PreparedMLData,
    *,
    model_name: str,
    checkpoint_dir: Path,
    config: M3Config = M3_DEFAULT_CONFIG,
) -> M2Artifacts:
    """复用 m2 训练器拟合一个液态模型，再对独立回测段生成预测。"""
    _, checkpoint_stem = _liquid_model_spec(model_name, config)
    comparison_config = _m3_comparison_config(config)
    splits = build_m2_data_splits(prepared, comparison_config)
    manifest_row = build_liquid_model_manifest(
        {model_name: build_liquid_model(model_name, config)},
        expected_version=config.dependency.package_version,
        source_url=config.dependency.source_url,
        source_commit=config.dependency.source_commit,
        source_license=config.dependency.source_license,
        method_scope=config.dependency.method_scope,
    )[0]
    manifest_row.update(
        {
            "loss_name": config.training.loss_name,
            "optimizer_name": config.training.optimizer_name,
            "label_scope": "AS9_T+1_to_T+21_forward_adjusted_VWAP_return",
            "feature_scope": "AS10_60_day_6_channel",
        }
    )
    training_result = train_sequence_regressor(
        lambda: build_liquid_model(model_name, config),
        train_dataset=splits.train,
        validation_dataset=splits.validation,
        settings=_m2_training_settings(comparison_config),
        checkpoint_path=Path(checkpoint_dir) / f"{checkpoint_stem}.pt",
        model_metadata=manifest_row,
    )
    training = config.training
    prediction_values = predict_sequence_regressor(
        training_result.model,
        dataset=splits.backtest,
        batch_size=training.batch_size,
        seed=training.seed,
        num_workers=training.num_workers,
        device=training.device,
    )
    if len(prediction_values) != len(splits.backtest_metadata):
        raise AssertionError("液态模型样本外预测数量与回测段元数据不一致")
    metadata_columns = [
        column
        for column in (
            "stock_code",
            "date",
            "label",
            "entry_date",
            "exit_date",
            "entry_tradable",
        )
        if column in splits.backtest_metadata.columns
    ]
    predictions = splits.backtest_metadata.loc[:, metadata_columns].copy()
    predictions[training.prediction_column] = prediction_values
    predictions["model"] = model_name
    resource_summary = pd.DataFrame(
        [{"model": model_name, **training_result.resource_summary, **manifest_row}]
    )
    return M2Artifacts(
        training=training_result,
        loss_curve=training_result.history.to_frame(),
        predictions=predictions,
        model_config=manifest_row,
        resource_summary=resource_summary,
    )


def train_liquid_family(
    prepared: PreparedMLData,
    *,
    checkpoint_dir: Path,
    config: M3Config = M3_DEFAULT_CONFIG,
) -> dict[str, M2Artifacts]:
    """依次训练四类液态模型；不改变共同样本、损失或早停配置。"""
    return {
        model_name: train_liquid_model(
            prepared,
            model_name=model_name,
            checkpoint_dir=checkpoint_dir,
            config=config,
        )
        for model_name, _, _ in config.model.model_specs
    }


# m4 仅追加预测因子与组合回测包装，不修改上方 m1-m3 函数。
from collections.abc import Mapping

from common.ml_portfolio import (
    MLPortfolioResult,
    MLPortfolioSettings,
    run_multi_path_factor_backtest,
)
from src.r002_liquid_neural_networks.config import M4Config, M4_DEFAULT_CONFIG


def assemble_m4_prediction_panel(
    prediction_frames: Mapping[str, pd.DataFrame],
    config: M4Config = M4_DEFAULT_CONFIG,
) -> pd.DataFrame:
    """合并五模型样本外预测并断言模型名、键和标签完全可比。"""
    portfolio = config.portfolio
    expected = set(portfolio.model_names)
    actual = set(prediction_frames)
    if actual != expected:
        raise ValueError(
            f"五模型预测集合不符: missing={sorted(expected - actual)}, "
            f"unexpected={sorted(actual - expected)}"
        )
    required = {
        portfolio.stock_column,
        portfolio.signal_date_column,
        portfolio.prediction_column,
        portfolio.forward_return_column,
    }
    frames: list[pd.DataFrame] = []
    reference_keys: pd.DataFrame | None = None
    reference_labels: np.ndarray | None = None
    for model_name in portfolio.model_names:
        frame = prediction_frames[model_name].copy()
        missing = sorted(required - set(frame.columns))
        if missing:
            raise KeyError(f"{model_name} 样本外预测缺少字段: {missing}")
        frame[portfolio.signal_date_column] = pd.to_datetime(
            frame[portfolio.signal_date_column], errors="raise"
        ).dt.normalize()
        frame[portfolio.stock_column] = frame[portfolio.stock_column].astype(str)
        if portfolio.model_column in frame.columns:
            supplied = set(frame[portfolio.model_column].dropna().astype(str).unique())
            if supplied and supplied != {model_name}:
                raise ValueError(f"{model_name} 预测表内 model 列不一致: {sorted(supplied)}")
        frame[portfolio.model_column] = model_name
        ordered = frame.sort_values(
            [portfolio.signal_date_column, portfolio.stock_column]
        ).reset_index(drop=True)
        keys = ordered.loc[
            :, [portfolio.stock_column, portfolio.signal_date_column]
        ]
        labels = pd.to_numeric(
            ordered[portfolio.forward_return_column], errors="coerce"
        ).to_numpy(dtype=float, na_value=np.nan)
        if reference_keys is None:
            reference_keys = keys
            reference_labels = labels
        else:
            pd.testing.assert_frame_equal(
                keys,
                reference_keys,
                check_dtype=False,
                check_exact=True,
                obj=f"{model_name} 与 GRU 的样本外键",
            )
            np.testing.assert_allclose(
                labels,
                reference_labels,
                rtol=0.0,
                atol=0.0,
                equal_nan=True,
                err_msg=f"{model_name} 与 GRU 的样本外标签不一致（NaN位置必须一致）",
            )
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def build_m4_market_panel(
    inputs: M1Inputs,
    config: M4Config = M4_DEFAULT_CONFIG,
) -> pd.DataFrame:
    """由 m1 全量前复权VWAP和逐日状态构造估值/执行面板。

    可成交状态只在此执行面板中形成，不与 T 日预测或因子面板合并。
    """
    portfolio = config.portfolio
    required_market = {
        portfolio.stock_column,
        portfolio.market_date_column,
        portfolio.market_price_column,
    }
    missing_market = sorted(required_market - set(inputs.panel.columns))
    if missing_market:
        raise KeyError(f"m1 行情面板缺少 m4 字段: {missing_market}")
    market = inputs.panel.loc[:, list(required_market)].copy()
    market[portfolio.stock_column] = market[portfolio.stock_column].astype(str)
    market[portfolio.market_date_column] = pd.to_datetime(
        market[portfolio.market_date_column], errors="raise"
    ).dt.normalize()

    suspend = inputs.suspend_status.loc[:, ["stock_code", "date", "if_suspend"]].copy()
    limit_ = inputs.limit_status.loc[
        :, ["stock_code", "date", "surged_limit", "decline_limit"]
    ].copy()
    for frame in (suspend, limit_):
        frame["stock_code"] = frame["stock_code"].astype(str)
        frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    suspend = (
        suspend.groupby(["stock_code", "date"], observed=True, as_index=False)["if_suspend"]
        .max()
    )
    limit_ = (
        limit_.groupby(["stock_code", "date"], observed=True, as_index=False)[
            ["surged_limit", "decline_limit"]
        ]
        .max()
    )
    market = market.merge(
        suspend,
        left_on=[portfolio.stock_column, portfolio.market_date_column],
        right_on=["stock_code", "date"],
        how="left",
        validate="one_to_one",
    ).merge(
        limit_,
        left_on=[portfolio.stock_column, portfolio.market_date_column],
        right_on=["stock_code", "date"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_limit"),
    )
    for status_column in ("if_suspend", "surged_limit", "decline_limit"):
        market[status_column] = market[status_column].fillna(0).astype("int8")
    market[portfolio.market_tradable_column] = ~(
        market["if_suspend"].eq(1)
        | market["surged_limit"].eq(1)
        | market["decline_limit"].eq(1)
    )
    return market.loc[
        :,
        [
            portfolio.stock_column,
            portfolio.market_date_column,
            portfolio.market_price_column,
            portfolio.market_tradable_column,
        ],
    ].sort_values([portfolio.market_date_column, portfolio.stock_column]).reset_index(drop=True)


def _m4_portfolio_settings(config: M4Config) -> MLPortfolioSettings:
    """将案例集中配置完整映射到通用回测引擎，不在函数体写策略参数。"""
    portfolio = config.portfolio
    return MLPortfolioSettings(
        model_col=portfolio.model_column,
        stock_col=portfolio.stock_column,
        signal_date_col=portfolio.signal_date_column,
        prediction_col=portfolio.prediction_column,
        forward_return_col=portfolio.forward_return_column,
        market_date_col=portfolio.market_date_column,
        market_price_col=portfolio.market_price_column,
        market_tradable_col=portfolio.market_tradable_column,
        n_groups=portfolio.n_groups,
        expected_model_count=len(portfolio.model_names),
        path_offsets=portfolio.path_offsets,
        rebalance_interval=portfolio.rebalance_interval,
        entry_offset=portfolio.entry_offset,
        exit_offset=portfolio.exit_offset,
        sell_fee_rate=portfolio.sell_fee_rate,
        initial_capital=portfolio.initial_capital,
        periods_per_year=portfolio.periods_per_year,
        risk_free_rate_per_day=portfolio.risk_free_rate_per_day,
        factor_correlation_method=portfolio.factor_correlation_method,
        min_cross_section_size=portfolio.min_cross_section_size,
        share_epsilon=portfolio.share_epsilon,
    )


def run_m4_backtest(
    predictions: pd.DataFrame,
    inputs: M1Inputs,
    config: M4Config = M4_DEFAULT_CONFIG,
) -> MLPortfolioResult:
    """执行 m4；预测面板与执行状态保持物理分离以防 T+1 信息泄漏。"""
    expected_models = set(config.portfolio.model_names)
    actual_models = set(
        predictions[config.portfolio.model_column].dropna().astype(str).unique()
    ) if config.portfolio.model_column in predictions.columns else set()
    if actual_models != expected_models:
        raise ValueError(
            f"m4 输入必须正好包含五模型: missing={sorted(expected_models - actual_models)}, "
            f"unexpected={sorted(actual_models - expected_models)}"
        )
    aligned_predictions = assemble_m4_prediction_panel(
        {
            model_name: predictions.loc[
                predictions[config.portfolio.model_column].astype(str) == model_name
            ].copy()
            for model_name in config.portfolio.model_names
        },
        config,
    )
    return run_multi_path_factor_backtest(
        aligned_predictions,
        build_m4_market_panel(inputs, config),
        inputs.trade_calendar,
        _m4_portfolio_settings(config),
    )

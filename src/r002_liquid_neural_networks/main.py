"""r002_liquid_neural_networks 全链路入口与 m5 正式输出装配。

默认运行严格使用完整本地A股样本、五模型既定配置和20路径十分档回测。
``--synthetic-smoke`` 只用于临时端到端接口冒烟，绝不作为正式复现结果。
"""

from __future__ import annotations

import argparse
import os
import platform
import resource
import shlex
import sys
from dataclasses import asdict, replace
from datetime import datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
import torch

from common.ml_pipeline import PreparedMLData
from common.ml_reporting import (
    build_ml_chart_data,
    build_ml_metrics,
    build_report_reference_tables,
    calculate_gradient_feature_importance,
    calculate_model_factor_correlation,
    create_ml_charts,
    write_backtest_workbook,
    write_detail_tables,
    write_json,
)
from common.ml_training import TrainingResult
from src.r002_liquid_neural_networks.config import (
    DEFAULT_CONFIG,
    M2_DEFAULT_CONFIG,
    M3_DEFAULT_CONFIG,
    M4_DEFAULT_CONFIG,
    M5_DEFAULT_CONFIG,
    M1Config,
    M2Config,
    M3Config,
    M4Config,
    M5Config,
)
from src.r002_liquid_neural_networks.strategy import (
    M1Inputs,
    M2Artifacts,
    assemble_m4_prediction_panel,
    build_gru_baseline,
    build_liquid_model,
    build_m1_audit_tables,
    load_m1_inputs,
    prepare_m1_dataset,
    run_m4_backtest,
    train_gru_baseline,
    train_liquid_model,
)
from src.r002_liquid_neural_networks.runtime_cache import (
    CachedModelState,
    RuntimeIdentity,
    build_runtime_identity,
    derive_model_fingerprint,
    load_completed_model_cache,
    write_completed_model_cache,
)


REPORT_ID = "r002_liquid_neural_networks"
DEFAULT_OUTPUT_DIR = Path("output") / REPORT_ID / "results"
RUNTIME_CACHE_DIRNAME = "runtime_cache"
CACHE_SAMPLE_COLUMNS = (
    "stock_code",
    "date",
    "split",
    "panel_row_start",
    "panel_row_end",
    "label",
    "entry_date",
    "exit_date",
)


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _peak_rss_bytes() -> int:
    """返回进程ru_maxrss；macOS为字节，其余常见Unix为KiB。"""
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _synchronize_and_empty_device_cache() -> None:
    if torch.cuda.is_available():
        torch.cuda.synchronize()
        torch.cuda.empty_cache()
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        if hasattr(torch.mps, "synchronize"):
            torch.mps.synchronize()
        if hasattr(torch.mps, "empty_cache"):
            torch.mps.empty_cache()


def _offload_trained_models(artifacts: Mapping[str, M2Artifacts]) -> None:
    """每个模型测量前把此前模型迁回CPU，避免设备常驻量污染后续行。"""
    for artifact in artifacts.values():
        artifact.training.model.to("cpu")
    _synchronize_and_empty_device_cache()


def _device_baseline_bytes(requested_device: str) -> tuple[int | None, str]:
    if requested_device == "auto":
        device_type = "cuda" if torch.cuda.is_available() else (
            "mps"
            if hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
            else "cpu"
        )
    else:
        device_type = torch.device(requested_device).type
    if device_type == "cuda":
        torch.cuda.synchronize()
        return int(torch.cuda.memory_allocated()), "cuda_memory_allocated_before_model"
    if device_type == "mps" and hasattr(torch.mps, "current_allocated_memory"):
        if hasattr(torch.mps, "synchronize"):
            torch.mps.synchronize()
        return int(torch.mps.current_allocated_memory()), "mps_current_allocated_before_model"
    return None, "not_available_on_cpu"


def _append_run_log(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(text.rstrip() + "\n")


def _environment_default(name: str, fallback: str | None = None) -> str | None:
    value = os.environ.get(name)
    return fallback if value is None or not value.strip() else value.strip()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="神经常微分方程与液态神经网络复现")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(_environment_default("R002_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))),
        help="输出目录；环境变量 R002_OUTPUT_DIR 可覆盖",
    )
    parser.add_argument(
        "--backtest-end",
        default=_environment_default("R002_BACKTEST_END"),
        help="回测截止日 YYYY-MM-DD；用于hard扰动时提前一年",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=int(_environment_default("R002_SEED", str(M2_DEFAULT_CONFIG.training.seed))),
        help="训练随机种子；环境变量 R002_SEED 可覆盖",
    )
    parser.add_argument(
        "--synthetic-smoke",
        action="store_true",
        default=_environment_default("R002_SYNTHETIC_SMOKE", "0") == "1",
        help="仅运行小型合成端到端冒烟；不得用作正式结果",
    )
    args = parser.parse_args(argv)
    requested_output_dir = Path(args.output_dir).expanduser().resolve()
    formal_output_dir = DEFAULT_OUTPUT_DIR.expanduser().resolve()
    smoke_redirected = bool(
        args.synthetic_smoke and requested_output_dir == formal_output_dir
    )
    args.requested_output_dir = requested_output_dir
    args.synthetic_output_redirected = smoke_redirected
    args.output_dir = (
        formal_output_dir / "_smoke" if smoke_redirected else requested_output_dir
    )
    return args


def _build_configs(args: argparse.Namespace) -> tuple[M1Config, M2Config, M3Config, M4Config, M5Config]:
    m1 = DEFAULT_CONFIG
    if args.backtest_end is not None:
        end = pd.Timestamp(args.backtest_end).normalize()
        if end < pd.Timestamp(m1.splits.backtest_start):
            raise ValueError("backtest_end 不得早于回测起点")
        if end > pd.Timestamp(DEFAULT_CONFIG.splits.backtest_end):
            raise ValueError("strict 模式不得把回测截止日延长到研报区间之后")
        m1 = replace(m1, splits=replace(m1.splits, backtest_end=str(end.date())))

    training = replace(M2_DEFAULT_CONFIG.training, seed=int(args.seed))
    if args.synthetic_smoke:
        training = replace(
            training,
            batch_size=512,
            max_epochs=1,
            early_stopping_patience=1,
            device="cpu",
        )
    m2 = replace(M2_DEFAULT_CONFIG, training=training)
    m3 = replace(M3_DEFAULT_CONFIG, training=training)
    return m1, m2, m3, M4_DEFAULT_CONFIG, M5_DEFAULT_CONFIG


def _runtime_source_files(m1: M1Config, *, synthetic_smoke: bool) -> list[Path]:
    """返回正式m1实际读取的八个源Parquet；合成冒烟没有外部源文件。"""
    if synthetic_smoke:
        return []
    data = m1.data
    return [
        data.root / data.forward_price,
        data.root / data.raw_price,
        data.root / data.trade,
        data.root / data.stock_master,
        data.root / data.st_status,
        data.root / data.suspend_status,
        data.root / data.limit_status,
        data.root / data.trade_calendar,
    ]


def _runtime_code_files() -> list[Path]:
    """缓存恢复所依赖的模型、数据集和训练关键源码。"""
    project_root = Path(__file__).resolve().parents[2]
    return [
        Path(__file__).resolve(),
        project_root / "src" / REPORT_ID / "strategy.py",
        project_root / "src" / REPORT_ID / "runtime_cache.py",
        project_root / "common" / "ml_pipeline.py",
        project_root / "common" / "ml_training.py",
        project_root / "common" / "ml_liquid.py",
        project_root / "common" / "data_loader.py",
    ]


def _build_runtime_identity(
    prepared: PreparedMLData,
    *,
    m1: M1Config,
    m2: M2Config,
    m3: M3Config,
    args: argparse.Namespace,
) -> RuntimeIdentity:
    return build_runtime_identity(
        report_id=REPORT_ID,
        configs={"m1": m1, "m2": m2, "m3": m3},
        source_files=_runtime_source_files(
            m1, synthetic_smoke=bool(args.synthetic_smoke)
        ),
        code_files=_runtime_code_files(),
        samples=prepared.samples,
        sample_columns=CACHE_SAMPLE_COLUMNS,
        feature_values=prepared.standardized_feature_values,
        feature_columns=prepared.feature_columns,
        source_mode="synthetic_smoke" if args.synthetic_smoke else "formal_local_parquet",
        extra={
            "synthetic_seed": int(args.seed) if args.synthetic_smoke else None,
            "formal_result": not bool(args.synthetic_smoke),
        },
    )


def _checkpoint_stem(model_name: str, m3: M3Config) -> str:
    if model_name == "GRU":
        return "gru"
    matches = [
        checkpoint_stem
        for configured_name, _, checkpoint_stem in m3.model.model_specs
        if configured_name == model_name
    ]
    if len(matches) != 1:
        raise KeyError(f"缓存未唯一找到模型检查点名称: {model_name}")
    return matches[0]


def _cached_prediction_frame(
    prepared: PreparedMLData,
    *,
    prediction_values: np.ndarray,
    model_name: str,
    config: M2Config,
) -> pd.DataFrame:
    """按原训练函数完全相同的回测元数据顺序重建缓存预测表。"""
    training = config.training
    metadata = prepared.samples.loc[
        prepared.samples["split"] == training.backtest_split
    ].reset_index(drop=True)
    if len(prediction_values) != len(metadata):
        raise AssertionError(
            f"{model_name}缓存预测数量与当前回测元数据不一致: "
            f"{len(prediction_values)} != {len(metadata)}"
        )
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
        if column in metadata.columns
    ]
    predictions = metadata.loc[:, metadata_columns].copy()
    predictions[training.prediction_column] = prediction_values
    predictions["model"] = model_name
    return predictions


def _artifact_from_cache(
    cached: CachedModelState,
    *,
    prepared: PreparedMLData,
    model_name: str,
    checkpoint_path: Path,
    comparison_config: M2Config,
) -> M2Artifacts:
    training_result = TrainingResult(
        model=cached.model,
        history=cached.history,
        resource_summary=cached.training_resource_summary,
        checkpoint_path=checkpoint_path,
    )
    return M2Artifacts(
        training=training_result,
        loss_curve=cached.history.to_frame(),
        predictions=_cached_prediction_frame(
            prepared,
            prediction_values=cached.prediction_values,
            model_name=model_name,
            config=comparison_config,
        ),
        model_config=cached.model_config,
        resource_summary=cached.artifact_resource_summary,
    )


def _build_synthetic_inputs(m1: M1Config, *, seed: int) -> M1Inputs:
    """构造仅供显式smoke使用的点时合成面板，不进入正式输出。"""
    rng = np.random.default_rng(seed)
    stocks = [f"S{index:03d}" for index in range(10)]
    segment_starts = [
        m1.splits.train_start,
        m1.splits.validation_start,
        m1.splits.backtest_start,
    ]
    calendars = [pd.bdate_range(start, periods=115) for start in segment_starts]
    all_dates = pd.DatetimeIndex(sorted(set().union(*[set(values) for values in calendars])))
    records: list[dict[str, Any]] = []
    for stock_index, stock_code in enumerate(stocks):
        for segment_index, dates in enumerate(calendars):
            previous_close = 10.0 + stock_index * 0.4 + segment_index
            for day_index, date in enumerate(dates):
                deterministic_return = (
                    0.0003 * (stock_index - 4.5)
                    + 0.003 * np.sin((day_index + stock_index) / 9.0)
                    + float(rng.normal(0.0, 0.001))
                )
                close = previous_close * np.exp(deterministic_return)
                open_price = previous_close * np.exp(deterministic_return * 0.4)
                high = max(open_price, close) * 1.006
                low = min(open_price, close) * 0.994
                volume = 1_000_000.0 + 10_000.0 * stock_index + 1_000.0 * day_index
                vwap = (open_price + close) / 2.0
                records.append(
                    {
                        "stock_code": stock_code,
                        "date": date,
                        "prev_close": previous_close,
                        "open": open_price,
                        "high": high,
                        "low": low,
                        "close": close,
                        "raw_close": close,
                        "raw_low": low,
                        "raw_high": high,
                        "volume": volume,
                        "turn_value": volume * vwap,
                        m1.labels.output_column: vwap,
                    }
                )
                previous_close = close
    panel = pd.DataFrame(records).sort_values(["stock_code", "date"]).reset_index(drop=True)
    # smoke 专用：保留 T 日特征与预测候选，只让一个回测期未来 VWAP 端点缺失，
    # 用于验证标签缺失仅影响事后诊断，不得提前改变分组或交易。
    missing_label_endpoint = calendars[2][85]
    missing_endpoint_mask = panel["stock_code"].eq(stocks[0]) & panel["date"].eq(
        missing_label_endpoint
    )
    if int(missing_endpoint_mask.sum()) != 1:
        raise AssertionError("synthetic smoke 缺标签端点必须唯一")
    panel.loc[missing_endpoint_mask, m1.labels.output_column] = np.nan
    stock_master = pd.DataFrame(
        {"stock_code": stocks, "list_date": pd.Timestamp("2000-01-01"), "list_state": 1}
    )
    status_keys = pd.MultiIndex.from_product(
        [stocks, all_dates], names=["stock_code", "date"]
    ).to_frame(index=False)
    suspend = status_keys.assign(if_suspend=np.int8(0))
    limit_status = status_keys.assign(
        surged_limit=np.int8(0), decline_limit=np.int8(0)
    )
    calendar = pd.DataFrame({"date": all_dates, "IfTradingDay": np.int8(1)})
    source_summary = pd.DataFrame(
        [{"source": "synthetic_smoke", "rows": len(panel), "stocks": len(stocks)}]
    )
    return M1Inputs(
        panel=panel,
        stock_master=stock_master,
        st_intervals=pd.DataFrame(columns=["stock_code", "implement_date", "remove_date"]),
        suspend_status=suspend,
        limit_status=limit_status,
        trade_calendar=calendar,
        source_summary=source_summary,
        vwap_diagnostics={
            "computable_rows": float(len(panel) - 1),
            "sanity_valid_rows": float(len(panel) - 1),
            "sanity_valid_fraction": float((len(panel) - 1) / len(panel)),
            "synthetic_missing_label_endpoint_rows": 1.0,
        },
    )


def _resource_row(
    artifact: M2Artifacts,
    *,
    model_name: str,
    batch_size: int,
    cpu_peak_before_bytes: int,
    device_baseline_bytes: int | None,
    device_baseline_measurement: str,
) -> pd.DataFrame:
    frame = artifact.resource_summary.copy()
    if "model" not in frame.columns:
        frame.insert(0, "model", model_name)
    frame["model"] = model_name
    cpu_peak_after = _peak_rss_bytes()
    frame["cpu_process_peak_rss_before_bytes"] = cpu_peak_before_bytes
    frame["cpu_process_peak_rss_bytes"] = cpu_peak_after
    frame["cpu_process_peak_rss_increment_bytes"] = max(
        cpu_peak_after - cpu_peak_before_bytes, 0
    )
    frame["cpu_memory_measurement"] = (
        "process_ru_maxrss_before_after_model_fit; cumulative_process_peak_not_isolated_model_peak"
    )
    frame["device_memory_baseline_bytes"] = device_baseline_bytes
    frame["device_memory_peak_bytes"] = frame["device_memory_bytes"]
    frame["device_memory_incremental_peak_bytes"] = frame["device_memory_peak_bytes"].where(
        frame["device_memory_peak_bytes"].notna(), np.nan
    ) - (0 if device_baseline_bytes is None else device_baseline_bytes)
    frame["device_memory_incremental_peak_bytes"] = frame[
        "device_memory_incremental_peak_bytes"
    ].clip(lower=0)
    frame["device_memory_baseline_measurement"] = device_baseline_measurement
    frame["device_memory_scope"] = (
        "previous_models_offloaded_to_cpu_and_cache_cleared; "
        "cuda=max_allocated_increment_above_baseline; "
        "mps=current_allocated_after_fit_increment_above_baseline_not_true_peak; "
        "cpu=device_memory_unavailable"
    )
    frame["batch_size"] = batch_size
    frame["dtype"] = "float32"
    frame["framework"] = f"pytorch-{torch.__version__}"
    frame["ncps_version"] = version("ncps") if model_name != "GRU" else None
    frame["hardware_platform"] = platform.platform()
    frame["hardware_machine"] = platform.machine()
    frame["hardware_processor"] = platform.processor() or "not_reported"
    frame["restored_from_cache"] = False
    return frame


def _comparison_metric(
    *,
    key: str,
    name: str,
    report_value: float | None,
    reproduced_value: float | None,
    source_page: str,
    source_element: str,
    verification_level: str,
    config: M5Config,
) -> dict[str, Any]:
    numeric = report_value is not None and reproduced_value is not None and np.isfinite(
        [report_value, reproduced_value]
    ).all()
    signed_deviation = (
        float(reproduced_value - report_value) if numeric else None
    )
    absolute_deviation = abs(signed_deviation) if signed_deviation is not None else None
    rel_dev = (
        absolute_deviation / abs(float(report_value))
        if numeric and float(report_value) != 0.0
        else None
    )
    direction_match = (
        (float(report_value) == 0.0 and float(reproduced_value) == 0.0)
        or float(report_value) * float(reproduced_value) > 0.0
        if numeric
        else None
    )
    passed: bool | None
    if verification_level == "unverifiable":
        passed = None
    elif verification_level == "directional":
        passed = bool(direction_match)
    else:
        passed = bool(numeric and rel_dev is not None and rel_dev <= 0.05)
    return {
        "key": key,
        "name": name,
        "report_value": report_value,
        "reproduced_value": reproduced_value,
        "rel_dev": rel_dev,
        "direction_match": direction_match,
        "tolerance_key": "ml.layers.model.direction_only",
        "source_page": source_page,
        "source_element": source_element,
        "layer": config.reference.comparison_layer,
        "pass": passed,
        "verification_level": verification_level,
        "attribution_status": config.reference.comparison_attribution_status,
        "assumption_links": list(config.reference.comparison_assumption_links),
        "absolute_deviation": absolute_deviation,
        "signed_deviation": signed_deviation,
    }


def _comparison_payload(
    comparison: pd.DataFrame,
    *,
    metrics_payload: Mapping[str, Any],
    resource_summary: pd.DataFrame,
    correlation_pairs: pd.DataFrame,
    portfolio: Any,
    config: M5Config,
) -> dict[str, Any]:
    metric_rows: list[dict[str, Any]] = []
    for suffix, report_value in zip(
        ("min", "max"), config.reference.ltc_literature_improvement_range
    ):
        metric_rows.append(
            _comparison_metric(
                key=f"R1.ltc_literature_improvement_{suffix}",
                name=f"LTC文献性能提升范围{suffix}",
                report_value=report_value,
                reproduced_value=None,
                source_page="p7",
                source_element="R1",
                verification_level="unverifiable",
                config=config,
            )
        )
    report_memory = dict(config.reference.report_gpu_memory_gb)
    for row in resource_summary.to_dict("records"):
        reproduced_gb = row.get("device_memory_incremental_peak_bytes")
        reproduced_gb = (
            float(reproduced_gb) / 1024**3
            if reproduced_gb is not None and np.isfinite(reproduced_gb)
            else None
        )
        metric_rows.append(
            _comparison_metric(
                key=f"R2.{row['model']}.device_memory_gb",
                name=f"{row['model']}设备内存占用",
                report_value=report_memory[str(row["model"])],
                reproduced_value=reproduced_gb,
                source_page="p13,p18",
                source_element="R2",
                verification_level="unverifiable",
                config=config,
            )
        )
    reproduced_range = metrics_payload["prediction_evaluation"][
        "factor_correlation_off_diagonal_range"
    ]
    for suffix, report_value, reproduced_value in zip(
        ("min", "max"),
        config.reference.report_factor_correlation_range,
        reproduced_range,
    ):
        metric_rows.append(
            _comparison_metric(
                key=f"R3.factor_correlation_{suffix}",
                name=f"五模型因子相关系数范围{suffix}",
                report_value=report_value,
                reproduced_value=reproduced_value,
                source_page="p13,p18",
                source_element="R3",
                verification_level=config.reference.comparison_verification_level,
                config=config,
            )
        )
    for row in comparison.to_dict("records"):
        for metric_name, report_key, reproduced_key in (
            ("annualized_return", "report_annualized_return", "annualized_return"),
            ("sharpe", "report_sharpe", "sharpe"),
        ):
            metric_rows.append(
                _comparison_metric(
                    key=f"{row['element_id']}.{row['model']}.{metric_name}",
                    name=f"{row['element_id']} {row['model']} {metric_name}",
                    report_value=row[report_key],
                    reproduced_value=row[reproduced_key],
                    source_page="p14",
                    source_element=row["element_id"],
                    verification_level=config.reference.comparison_verification_level,
                    config=config,
                )
            )

    valid_pair_count = int(correlation_pairs["status"].eq("valid").sum())
    monotonic = bool((portfolio.monotonicity["directional_monotonicity"] > 0).all())
    full_groups = portfolio.path_metric_aggregate.loc[
        portfolio.path_metric_aggregate["period"].eq("all")
        & portfolio.path_metric_aggregate["portfolio"].str.startswith("group_")
    ].copy()
    full_groups["group"] = full_groups["portfolio"].str.removeprefix("group_").astype(int)
    top_best = all(
        int(frame.loc[frame["annualized_return"].idxmax(), "group"]) == 1
        for _, frame in full_groups.groupby("model")
    )
    annual = portfolio.path_metric_aggregate.loc[
        ~portfolio.path_metric_aggregate["period"].eq("all")
        & portfolio.path_metric_aggregate["portfolio"].eq("top_long")
    ]
    ncp_checks: list[bool] = []
    for _, frame in annual.groupby("period"):
        values = frame.set_index("model")["annualized_return"]
        if {"LTC", "NCP（LTC）", "CFC", "NCP（CFC）"} <= set(values.index):
            ncp_checks.extend(
                [values["NCP（LTC）"] >= values["LTC"], values["NCP（CFC）"] >= values["CFC"]]
            )
    ncp_usually_better = bool(ncp_checks and np.mean(ncp_checks) >= 0.5)
    qualitative = [
        {
            "key": "SA2.pearson_pair_coverage",
            "expect": "10_unordered_pairs_valid",
            "observed": "10_unordered_pairs_valid" if valid_pair_count == 10 else f"{valid_pair_count}_pairs_valid",
            "pass": valid_pair_count == 10,
        },
        {
            "key": "ml.group_monotonicity",
            "expect": "all_models_positive_monotonicity",
            "observed": "all_models_positive_monotonicity" if monotonic else "not_all_models_positive_monotonicity",
            "pass": monotonic,
        },
        {
            "key": "ml.top_group_rank",
            "expect": "all_models_group1_best",
            "observed": "all_models_group1_best" if top_best else "not_all_models_group1_best",
            "pass": top_best,
        },
        {
            "key": "SA3.ncp_usually_better",
            "expect": "ncp_usually_better",
            "observed": "ncp_usually_better" if ncp_usually_better else "ncp_not_usually_better",
            "pass": ncp_usually_better,
        },
    ]
    evaluated_metrics = [row for row in metric_rows if row["pass"] is not None]
    pass_count = sum(row["pass"] is True for row in evaluated_metrics) + sum(
        row["pass"] is True for row in qualitative
    )
    evaluated_total = len(evaluated_metrics) + len(qualitative)
    overall_pass = pass_count == evaluated_total
    return {
        "report_id": REPORT_ID,
        "reproduction_mode": "strict_method_level_degraded",
        "meta": {
            "report_values_are_reference_only_until_compared": True,
            "original_figures_tables": "reference_only/data_missing",
            "verdict_owner": "quant-verifier/check_gates",
            "resource_scope": "device incremental after previous models offloaded; CPU RSS cumulative",
        },
        "metrics": metric_rows,
        "qualitative": qualitative,
        "overall_pass": overall_pass,
        "pass_count": pass_count,
        "total": evaluated_total,
        "waived_count": len(metric_rows) - len(evaluated_metrics),
    }


def run_pipeline(args: argparse.Namespace) -> dict[str, Path]:
    """执行m1至m5并生成正式结构化输出；不作验证通过判定。"""
    output_dir = Path(args.output_dir).expanduser().resolve()
    formal_output_dir = DEFAULT_OUTPUT_DIR.expanduser().resolve()
    if args.synthetic_smoke and output_dir == formal_output_dir:
        args.requested_output_dir = formal_output_dir
        args.synthetic_output_redirected = True
        output_dir = formal_output_dir / "_smoke"
        args.output_dir = output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    run_log = output_dir / "run_log.md"
    started_at = _timestamp()
    command = " ".join(shlex.quote(part) for part in [sys.executable, "-m", __package__ + ".main", *sys.argv[1:]])
    _append_run_log(
        run_log,
        "\n".join(
            [
                f"## 运行 {started_at}",
                f"- command: `{command}`",
                f"- output_dir: `{output_dir}`",
                f"- requested_output_dir: `{getattr(args, 'requested_output_dir', output_dir)}`",
                f"- synthetic_output_redirected: {bool(getattr(args, 'synthetic_output_redirected', False))}",
                f"- seed: {args.seed}",
                f"- backtest_end_override: {args.backtest_end or 'none'}",
                f"- synthetic_smoke: {bool(args.synthetic_smoke)}",
                "- status: running",
            ]
        ),
    )
    m1, m2, m3, m4, m5 = _build_configs(args)
    inputs = _build_synthetic_inputs(m1, seed=args.seed) if args.synthetic_smoke else load_m1_inputs(m1)
    prepared = prepare_m1_dataset(inputs, m1)
    data_audit_tables = build_m1_audit_tables(prepared, inputs)

    runtime_identity = _build_runtime_identity(
        prepared,
        m1=m1,
        m2=m2,
        m3=m3,
        args=args,
    )
    _append_run_log(
        run_log,
        "\n".join(
            [
                f"- runtime_identity_sha256: {runtime_identity.digest}",
                "- runtime_cache_policy: exact_fingerprint_only; mismatch_refused",
                "- runtime_cache_scope: completed_training_plus_full_backtest_prediction_per_model",
            ]
        ),
    )

    checkpoints = output_dir / "checkpoints"
    checkpoints.mkdir(parents=True, exist_ok=True)
    runtime_cache_dir = output_dir / RUNTIME_CACHE_DIRNAME
    artifacts: dict[str, M2Artifacts] = {}
    resources: list[pd.DataFrame] = []
    model_prediction_values: dict[str, np.ndarray] = {}
    gru_name = "GRU"
    gru_checkpoint = checkpoints / f"{_checkpoint_stem(gru_name, m3)}.pt"
    gru_cache = runtime_cache_dir / "gru.complete.pt"
    gru_fingerprint, gru_manifest = derive_model_fingerprint(
        runtime_identity,
        model_name=gru_name,
        model_config={"family": "gru", "config": m2},
    )
    cached_gru = load_completed_model_cache(
        gru_cache,
        expected_fingerprint=gru_fingerprint,
        expected_model_name=gru_name,
        model_factory=lambda: build_gru_baseline(m2),
        checkpoint_path=gru_checkpoint,
    )
    if cached_gru is not None:
        artifacts[gru_name] = _artifact_from_cache(
            cached_gru,
            prepared=prepared,
            model_name=gru_name,
            checkpoint_path=gru_checkpoint,
            comparison_config=m2,
        )
        cached_gru_resource = cached_gru.resource_row.copy()
        cached_gru_resource["restored_from_cache"] = True
        resources.append(cached_gru_resource)
        _append_run_log(
            run_log,
            f"- model_cache: {gru_name} restored `{gru_cache}`; "
            "resource_record_source=completed_model_cache",
        )
    else:
        _offload_trained_models(artifacts)
        device_baseline, device_baseline_measurement = _device_baseline_bytes(
            m2.training.device
        )
        cpu_peak_before = _peak_rss_bytes()
        artifacts[gru_name] = train_gru_baseline(
            prepared,
            checkpoint_path=gru_checkpoint,
            config=m2,
        )
        gru_resource_row = _resource_row(
            artifacts[gru_name],
            model_name=gru_name,
            batch_size=m2.training.batch_size,
            cpu_peak_before_bytes=cpu_peak_before,
            device_baseline_bytes=device_baseline,
            device_baseline_measurement=device_baseline_measurement,
        )
        resources.append(gru_resource_row)
        write_completed_model_cache(
            gru_cache,
            fingerprint=gru_fingerprint,
            fingerprint_manifest=gru_manifest,
            model_name=gru_name,
            model=artifacts[gru_name].training.model,
            history=artifacts[gru_name].training.history,
            training_resource_summary=artifacts[gru_name].training.resource_summary,
            prediction_values=artifacts[gru_name].predictions[
                m2.training.prediction_column
            ].to_numpy(dtype=np.float64),
            model_config=artifacts[gru_name].model_config,
            artifact_resource_summary=artifacts[gru_name].resource_summary,
            resource_row=gru_resource_row,
            checkpoint_path=gru_checkpoint,
        )
        _append_run_log(
            run_log,
            f"- model_cache: {gru_name} written `{gru_cache}`; "
            "resource_record_source=fresh_training_measurement",
        )
    model_prediction_values[gru_name] = artifacts[gru_name].predictions[
        m2.training.prediction_column
    ].to_numpy(dtype=np.float64, copy=True)
    artifacts[gru_name].predictions = pd.DataFrame()

    for model_name, _, _ in m3.model.model_specs:
        checkpoint_stem = _checkpoint_stem(model_name, m3)
        checkpoint_path = checkpoints / f"{checkpoint_stem}.pt"
        cache_path = runtime_cache_dir / f"{checkpoint_stem}.complete.pt"
        fingerprint, fingerprint_manifest = derive_model_fingerprint(
            runtime_identity,
            model_name=model_name,
            model_config={"family": "liquid", "model_name": model_name, "config": m3},
        )
        cached = load_completed_model_cache(
            cache_path,
            expected_fingerprint=fingerprint,
            expected_model_name=model_name,
            model_factory=lambda name=model_name: build_liquid_model(name, m3),
            checkpoint_path=checkpoint_path,
        )
        if cached is not None:
            artifacts[model_name] = _artifact_from_cache(
                cached,
                prepared=prepared,
                model_name=model_name,
                checkpoint_path=checkpoint_path,
                comparison_config=m2,
            )
            cached_resource_row = cached.resource_row.copy()
            cached_resource_row["restored_from_cache"] = True
            resources.append(cached_resource_row)
            _append_run_log(
                run_log,
                f"- model_cache: {model_name} restored `{cache_path}`; "
                "resource_record_source=completed_model_cache",
            )
        else:
            _offload_trained_models(artifacts)
            device_baseline, device_baseline_measurement = _device_baseline_bytes(
                m3.training.device
            )
            cpu_peak_before = _peak_rss_bytes()
            artifacts[model_name] = train_liquid_model(
                prepared,
                model_name=model_name,
                checkpoint_dir=checkpoints,
                config=m3,
            )
            resource_row = _resource_row(
                artifacts[model_name],
                model_name=model_name,
                batch_size=m3.training.batch_size,
                cpu_peak_before_bytes=cpu_peak_before,
                device_baseline_bytes=device_baseline,
                device_baseline_measurement=device_baseline_measurement,
            )
            resources.append(resource_row)
            write_completed_model_cache(
                cache_path,
                fingerprint=fingerprint,
                fingerprint_manifest=fingerprint_manifest,
                model_name=model_name,
                model=artifacts[model_name].training.model,
                history=artifacts[model_name].training.history,
                training_resource_summary=artifacts[
                    model_name
                ].training.resource_summary,
                prediction_values=artifacts[model_name].predictions[
                    m3.training.prediction_column
                ].to_numpy(dtype=np.float64),
                model_config=artifacts[model_name].model_config,
                artifact_resource_summary=artifacts[model_name].resource_summary,
                resource_row=resource_row,
                checkpoint_path=checkpoint_path,
            )
            _append_run_log(
                run_log,
                f"- model_cache: {model_name} written `{cache_path}`; "
                "resource_record_source=fresh_training_measurement",
            )
        model_prediction_values[model_name] = artifacts[model_name].predictions[
            m3.training.prediction_column
        ].to_numpy(dtype=np.float64, copy=True)
        artifacts[model_name].predictions = pd.DataFrame()

    loss_curves = pd.concat(
        [artifact.loss_curve.assign(model=model_name) for model_name, artifact in artifacts.items()],
        ignore_index=True,
    )
    predictions = assemble_m4_prediction_panel(
        {
            model_name: _cached_prediction_frame(
                prepared,
                prediction_values=model_prediction_values[model_name],
                model_name=model_name,
                config=m2,
            )
            for model_name in m4.portfolio.model_names
        },
        m4,
    )
    resources_frame = pd.concat(resources, ignore_index=True, sort=False)
    portfolio = run_m4_backtest(predictions, inputs, m4)
    feature_importance = calculate_gradient_feature_importance(
        {model_name: artifact.training.model for model_name, artifact in artifacts.items()},
        prepared.dataset(m2.training.backtest_split),
        prepared.feature_columns,
        batch_size=m5.output.feature_importance_batch_size,
    )
    factor_correlation, factor_correlation_pairs, factor_correlation_by_date = (
        calculate_model_factor_correlation(
            portfolio.factor_panel,
            model_names=m4.portfolio.model_names,
            method=m5.reference.factor_correlation_method,
            min_common=m5.reference.factor_correlation_min_common,
            min_unique_values=m5.reference.factor_correlation_min_unique_values,
            sample_scope=m5.reference.factor_correlation_sample_scope,
        )
    )
    invalid_pairs = factor_correlation_pairs.loc[
        ~factor_correlation_pairs["status"].eq("valid")
    ]
    _append_run_log(
        run_log,
        "\n".join(
            [
                "- factor_correlation_method: pearson",
                f"- factor_correlation_sample_scope: {m5.reference.factor_correlation_sample_scope}",
                f"- factor_correlation_min_common: {m5.reference.factor_correlation_min_common}",
                f"- factor_correlation_invalid_pair_count: {len(invalid_pairs)}",
                f"- factor_correlation_warnings: {invalid_pairs[['model_left', 'model_right', 'status']].to_dict('records')}",
            ]
        ),
    )

    resource_reference, performance_reference = build_report_reference_tables(
        report_gpu_memory_gb=m5.reference.report_gpu_memory_gb,
        report_performance=m5.reference.report_performance,
    )
    sample_coverage = data_audit_tables["sample_coverage"]
    run_metadata = {
        "started_at": started_at,
        "finished_computation_at": _timestamp(),
        "command": command,
        "seed": args.seed,
        "backtest_end": m1.splits.backtest_end,
        "synthetic_smoke": bool(args.synthetic_smoke),
        "formal_result": not bool(args.synthetic_smoke),
        "requested_output_dir": str(getattr(args, "requested_output_dir", output_dir)),
        "actual_output_dir": str(output_dir),
        "synthetic_output_redirected": bool(
            getattr(args, "synthetic_output_redirected", False)
        ),
        "framework": f"pytorch-{torch.__version__}",
        "dtype": "float32",
        "hardware_platform": platform.platform(),
    }
    output_boundaries = {
        "metrics_use_full_samples": True,
        "parquet_details_use_full_samples": True,
        "excel_detail_row_limit": m5.output.excel_detail_row_limit,
        "plot_point_limit": m5.output.plot_point_limit,
        "display_sampling_seed": args.seed,
        "assumption": "AS17",
    }
    metrics, comparison = build_ml_metrics(
        run_metadata=run_metadata,
        sample_coverage=sample_coverage,
        resource_summary=resources_frame,
        loss_curves=loss_curves,
        portfolio=portfolio,
        factor_correlation=factor_correlation,
        factor_correlation_pairs=factor_correlation_pairs,
        factor_correlation_by_date=factor_correlation_by_date,
        feature_importance=feature_importance,
        report_ltc_improvement_range=m5.reference.ltc_literature_improvement_range,
        report_factor_correlation_range=m5.reference.report_factor_correlation_range,
        report_resource_reference=resource_reference,
        report_performance_reference=performance_reference,
        output_boundaries=output_boundaries,
    )
    label_coverage_summary = pd.DataFrame(
        metrics["prediction_evaluation"]["label_coverage_summary"]
    )
    label_coverage_by_date = pd.DataFrame(
        metrics["prediction_evaluation"]["label_coverage_by_date"]
    )
    _append_run_log(
        run_log,
        "\n".join(
            [
                "- label_missing_changes_groups_or_trades: false",
                "- rank_ic_label_policy: pairwise_complete_prediction_and_label",
                "- prediction_scatter_label_policy: pairwise_complete_before_sampling",
                f"- label_coverage_summary: {label_coverage_summary.to_dict('records')}",
            ]
        ),
    )

    chart_data = build_ml_chart_data(
        portfolio=portfolio,
        factor_correlation=factor_correlation,
        loss_curves=loss_curves,
        resource_summary=resources_frame,
        feature_importance=feature_importance,
        plot_point_limit=m5.output.plot_point_limit,
        seed=args.seed,
    )
    chart_paths = create_ml_charts(
        output_dir=output_dir,
        chart_data=chart_data,
        title_prefix=m5.output.figure_title_prefix,
        dpi=m5.output.figure_dpi,
        time_series_size=m5.output.time_series_figure_size,
        standard_size=m5.output.standard_figure_size,
        primary_blue=m5.output.primary_blue,
        primary_red=m5.output.primary_red,
        neutral_gray=m5.output.neutral_gray,
    )
    detail_paths = write_detail_tables(
        output_dir=output_dir,
        predictions=predictions,
        portfolio=portfolio,
        factor_correlation=factor_correlation,
        factor_correlation_pairs=factor_correlation_pairs,
        factor_correlation_by_date=factor_correlation_by_date,
        label_coverage_summary=label_coverage_summary,
        label_coverage_by_date=label_coverage_by_date,
        chart_data=chart_data,
    )
    comparison_payload = _comparison_payload(
        comparison,
        metrics_payload=metrics,
        resource_summary=resources_frame,
        correlation_pairs=factor_correlation_pairs,
        portfolio=portfolio,
        config=m5,
    )
    loss_curves.to_csv(output_dir / "model_training_log.csv", index=False, encoding="utf-8-sig")
    resources_frame.to_csv(output_dir / "model_resource_log.csv", index=False, encoding="utf-8-sig")
    write_json(
        output_dir / "model_config_log.json",
        {model_name: artifact.model_config for model_name, artifact in artifacts.items()},
        indent=m5.output.json_indent,
    )
    write_json(
        output_dir / "m5_method_config.json",
        asdict(m5),
        indent=m5.output.json_indent,
    )
    write_json(
        output_dir / m5.output.metrics_filename,
        metrics,
        indent=m5.output.json_indent,
    )
    write_json(
        output_dir / m5.output.comparison_filename,
        comparison_payload,
        indent=m5.output.json_indent,
    )
    workbook_path = output_dir / m5.output.workbook_filename
    write_backtest_workbook(
        path=workbook_path,
        comparison=pd.DataFrame(comparison_payload["metrics"]),
        rank_ic_summary=pd.DataFrame(metrics["prediction_evaluation"]["rank_ic"]),
        portfolio=portfolio,
        factor_correlation_pairs=factor_correlation_pairs,
        label_coverage_summary=label_coverage_summary,
        label_coverage_by_date=label_coverage_by_date,
        report_resource_reference=resource_reference,
        report_performance_reference=performance_reference,
        data_audit_tables=data_audit_tables,
        chart_data=chart_data,
        chart_paths=chart_paths,
        row_limit=m5.output.excel_detail_row_limit,
    )
    _append_run_log(
        run_log,
        "\n".join(
            [
                f"- finished_at: {_timestamp()}",
                "- exit=0",
                "- exit_code: 0",
                "- status: completed_without_verifier_judgement",
                f"- metrics: `{output_dir / m5.output.metrics_filename}`",
                f"- workbook: `{workbook_path}`",
                f"- detail_files: {len(detail_paths)}",
            ]
        ),
    )
    return {
        "metrics": output_dir / m5.output.metrics_filename,
        "comparison": output_dir / m5.output.comparison_filename,
        "workbook": workbook_path,
        "run_log": run_log,
        **chart_paths,
        **detail_paths,
    }


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    output_dir = Path(args.output_dir).expanduser().resolve()
    try:
        paths = run_pipeline(args)
    except Exception as exc:
        _append_run_log(
            output_dir / "run_log.md",
            "\n".join(
                [
                    f"- failed_at: {_timestamp()}",
                    "- exit=1",
                    "- exit_code: 1",
                    f"- error_type: {type(exc).__name__}",
                    f"- error: {exc}",
                    "- status: failed",
                ]
            ),
        )
        raise
    print(f"m5输出已生成（待verifier独立核验）：{paths['metrics'].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

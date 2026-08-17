"""r003 中国A股因子择时迁移版正式入口。

默认命令运行 2023-04 至 2025-12 的33个月严格样本外链路。任何缩短区间
都必须通过显式CLI参数给出，并在运行日志中标记为诊断运行。
"""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import shlex
import sys
from time import perf_counter
from typing import Sequence

import pandas as pd

from .config import ChinaFactorTimingConfig
from .data_pipeline import build_m1_dataset
from .factor_model import run_stage_two_factor_model
from .portfolio import run_portfolio_construction
from .regime_model import run_stage_one_regime_model
from .reporting import REPORT_ID, ReportPackage, append_run_log, write_result_package


DEFAULT_OUTPUT_ROOT = Path("output") / REPORT_ID / "results"


def _month(value: str, *, argument: str) -> pd.Period:
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError(f"{argument} 必须是有效年月或日期") from exc
    return timestamp.to_period("M")


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="运行r003中国A股两阶段因子择时严格样本外链路并生成m5结果包"
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help=f"结果目录（默认: {DEFAULT_OUTPUT_ROOT}）",
    )
    parser.add_argument(
        "--prediction-start",
        default=ChinaFactorTimingConfig().oos_start,
        help="首个目标预测月；默认固定为2023-04",
    )
    parser.add_argument(
        "--end",
        default=ChinaFactorTimingConfig().sample_end,
        help="最后目标预测月；默认固定为2025-12",
    )
    return parser.parse_args(argv)


def _validate_window(args: argparse.Namespace, config: ChinaFactorTimingConfig) -> tuple[pd.Period, pd.Period]:
    start = _month(args.prediction_start, argument="--prediction-start")
    end = _month(args.end, argument="--end")
    cutoff = pd.Timestamp(config.oos_cutoff).to_period("M")
    formal_end = pd.Timestamp(config.sample_end).to_period("M")
    if start <= cutoff:
        raise ValueError(
            f"prediction-start必须晚于冻结切点{cutoff}；正式默认从2023-04开始"
        )
    if end < start:
        raise ValueError("--end 不得早于 --prediction-start")
    if end > formal_end:
        raise ValueError(f"--end 不得晚于数据冻结终点{formal_end}")
    return start, end


def run_pipeline(args: argparse.Namespace) -> ReportPackage:
    """依次执行m1→m2→m3→m4→m5；不作独立验证判定。"""
    run_started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    run_started_monotonic = perf_counter()
    base_config = ChinaFactorTimingConfig()
    output_root = Path(args.output_root).expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_log = output_root / "run_log.md"
    command = " ".join(
        shlex.quote(part)
        for part in [
            sys.executable,
            "-m",
            "src.r003_equity_factor_timing_cn.main",
            "--output-root",
            str(output_root),
            "--prediction-start",
            str(args.prediction_start),
            "--end",
            str(args.end),
        ]
    )
    append_run_log(
        run_log,
        [
            "# r003 中国A股因子择时运行日志",
            f"- started_at: {run_started_at}",
            f"- command: `{command}`",
            f"- output_root: `{output_root}`",
            "- status: running_pending_independent_verifier",
        ],
    )
    try:
        prediction_start, end = _validate_window(args, base_config)
        formal_window = (
            prediction_start == pd.Timestamp(base_config.oos_start).to_period("M")
            and end == pd.Timestamp(base_config.sample_end).to_period("M")
        )
        append_run_log(
            run_log,
            [
                f"- freeze_cutoff: {pd.Timestamp(base_config.oos_cutoff).to_period('M')}",
                f"- prediction_window: {prediction_start}..{end}",
                f"- rolling_train_months: {base_config.turbulence_window_months}",
                f"- formal_default_window: {formal_window}",
                "- oos_tuning: forbidden",
                "- primary_return_basis: gross",
            ],
        )
        append_run_log(run_log, ["## m1", "- status: running"])
        # m1始终按冻结的完整2015-01至2025-12底座构造，不能让诊断--end
        # 截断交易日历或下一交易期。--end只裁剪传给预测层的月频特征。
        dataset = build_m1_dataset(base_config)
        model_features = dataset.monthly_features.loc[
            pd.to_datetime(dataset.monthly_features["signal_date"])
            <= end.to_timestamp("M")
        ].copy()
        append_run_log(
            run_log,
            [
                "- status: completed_for_downstream",
                f"- monthly_feature_rows: {len(dataset.monthly_features)}",
                f"- prediction_feature_rows_through_end: {len(model_features)}",
                f"- factor_return_rows: {len(dataset.factor_returns)}",
            ],
        )

        append_run_log(run_log, ["## m2", "- status: running"])
        stage_one = run_stage_one_regime_model(
            model_features,
            config=base_config,
            prediction_start=prediction_start.to_timestamp("M"),
        )
        append_run_log(
            run_log,
            [
                "- status: completed_for_downstream",
                f"- rolling_prediction_rows: {len(stage_one.rolling_predictions)}",
                f"- parameter_hash: {stage_one.parameter_hash}",
            ],
        )

        append_run_log(run_log, ["## m3", "- status: running"])
        stage_two = run_stage_two_factor_model(
            model_features,
            dataset.factor_returns,
            stage_one,
            config=base_config,
            prediction_start=prediction_start.to_timestamp("M"),
        )
        append_run_log(
            run_log,
            [
                "- status: completed_for_downstream",
                f"- probability_rows: {len(stage_two.rolling_probabilities)}",
                f"- parameter_hash: {stage_two.parameter_hash}",
            ],
        )

        append_run_log(run_log, ["## m4", "- status: running"])
        portfolio = run_portfolio_construction(
            dataset.monthly_features,
            dataset.factor_returns,
            stage_two,
            config=base_config,
        )
        append_run_log(
            run_log,
            [
                "- status: completed_for_downstream",
                f"- portfolio_return_rows: {len(portfolio.portfolio_returns)}",
                "- portfolio_count: 4",
            ],
        )

        append_run_log(run_log, ["## m5", "- status: running"])
        return write_result_package(
            output_dir=output_root,
            stage_one=stage_one,
            stage_two=stage_two,
            portfolio=portfolio,
            factor_constituents=dataset.factor_constituents,
            prediction_start=prediction_start.to_timestamp("M"),
            end=end.to_timestamp("M"),
            config=base_config,
            run_log_path=run_log,
            run_started_at=run_started_at,
            run_started_monotonic=run_started_monotonic,
            command=command,
        )
    except Exception as exc:
        failed_at = datetime.now().astimezone().isoformat(timespec="seconds")
        append_run_log(
            run_log,
            [
                "## 运行失败",
                f"- started_at: {run_started_at}",
                f"- finished_at: {failed_at}",
                f"- elapsed_seconds: {perf_counter() - run_started_monotonic:.6f}",
                f"- command: `{command}`",
                "- exit=1",
                f"- error_type: {type(exc).__name__}",
                f"- error: {exc}",
                "- status: failed_without_verifier_judgement",
            ],
        )
        raise


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    package = run_pipeline(args)
    print(f"m5结果包已生成（待quant-verifier独立核验）：{package.paths['metrics.json'].parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

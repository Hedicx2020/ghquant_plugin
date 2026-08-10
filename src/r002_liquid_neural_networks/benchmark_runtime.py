"""小规模数据加载基准；不训练模型、不读取或写入正式output。"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from typing import Sequence

import numpy as np
import pandas as pd

from common.ml_pipeline import FeaturePreprocessor, PreparedMLData
from common.ml_training import _build_loader


FEATURE_COLUMNS = tuple(f"feature_{index}" for index in range(6))
WINDOW_LENGTH = 60
DEFAULT_SAMPLE_COUNT = 120_000
DEFAULT_BATCH_SIZE = 512
DEFAULT_SEED = 42


class LegacyPanelWindowDataset:
    """修复前的逐样本pandas iloc与每split整面板复制路径。"""

    def __init__(self, feature_panel: pd.DataFrame, samples: pd.DataFrame) -> None:
        self.samples = samples.reset_index(drop=True).copy()
        self._features = feature_panel.loc[:, FEATURE_COLUMNS].to_numpy(
            dtype=np.float32
        )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[np.ndarray, np.float32]:
        row = self.samples.iloc[index]
        start = int(row["panel_row_start"])
        end = int(row["panel_row_end"]) + 1
        return self._features[start:end].copy(), np.float32(row["label"])


def _peak_rss_bytes() -> int:
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return value if sys.platform == "darwin" else value * 1024


def _fixture(sample_count: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(DEFAULT_SEED)
    panel_rows = sample_count + WINDOW_LENGTH - 1
    feature_panel = pd.DataFrame(
        rng.normal(size=(panel_rows, len(FEATURE_COLUMNS))),
        columns=FEATURE_COLUMNS,
    )
    feature_panel.insert(0, "date", pd.bdate_range("2008-01-01", periods=panel_rows))
    feature_panel.insert(0, "stock_code", "S000001")
    split = np.resize(np.array(["train", "validation", "backtest"]), sample_count)
    dates = feature_panel["date"].iloc[:sample_count].reset_index(drop=True)
    samples = pd.DataFrame(
        {
            "stock_code": [f"S{index % 5000:06d}" for index in range(sample_count)],
            "date": dates,
            "split": split,
            "panel_row_start": np.arange(sample_count, dtype=np.int64),
            "panel_row_end": np.arange(sample_count, dtype=np.int64)
            + WINDOW_LENGTH
            - 1,
            "label": rng.normal(size=sample_count).astype(np.float32),
        }
    )
    return feature_panel, samples


def _prepared(feature_panel: pd.DataFrame, samples: pd.DataFrame) -> PreparedMLData:
    zeros = pd.Series(0.0, index=FEATURE_COLUMNS)
    ones = pd.Series(1.0, index=FEATURE_COLUMNS)
    return PreparedMLData(
        feature_panel=feature_panel,
        samples=samples,
        feature_columns=FEATURE_COLUMNS,
        preprocessor=FeaturePreprocessor(
            feature_columns=FEATURE_COLUMNS,
            lower=zeros,
            upper=ones,
            mean=zeros,
            std=ones,
            fit_row_count=len(samples),
            fit_start=pd.Timestamp(feature_panel["date"].min()),
            fit_end=pd.Timestamp(feature_panel["date"].max()),
            lower_quantile=0.005,
            upper_quantile=0.995,
        ),
        quality_summary={},
    )


def run_benchmark(mode: str, *, sample_count: int, batch_size: int) -> dict[str, object]:
    feature_panel, samples = _fixture(sample_count)
    rss_before_dataset = _peak_rss_bytes()
    if mode == "legacy":
        datasets = {
            split: LegacyPanelWindowDataset(
                feature_panel,
                samples.loc[samples["split"].eq(split)].reset_index(drop=True),
            )
            for split in ("train", "validation", "backtest")
        }
    elif mode == "optimized":
        prepared = _prepared(feature_panel, samples)
        datasets = {
            split: prepared.dataset(split)
            for split in ("train", "validation", "backtest")
        }
    else:
        raise ValueError(f"未知基准模式: {mode}")
    rss_after_dataset = _peak_rss_bytes()
    started = time.perf_counter()
    observed = 0
    checksum = 0.0
    for split, dataset in datasets.items():
        loader = _build_loader(
            dataset,
            batch_size=batch_size,
            shuffle=split == "train",
            seed=DEFAULT_SEED,
            num_workers=0,
            pin_memory=False,
        )
        for features, labels in loader:
            observed += int(features.shape[0])
            checksum += float(features[:, 0, 0].sum()) + float(labels.sum())
    elapsed = time.perf_counter() - started
    rss_after_iteration = _peak_rss_bytes()
    return {
        "mode": mode,
        "sample_count": sample_count,
        "observed_count": observed,
        "batch_size": batch_size,
        "elapsed_seconds": elapsed,
        "samples_per_second": observed / elapsed,
        "peak_rss_before_dataset_bytes": rss_before_dataset,
        "peak_rss_after_dataset_bytes": rss_after_dataset,
        "peak_rss_after_iteration_bytes": rss_after_iteration,
        "dataset_peak_increment_bytes": max(
            rss_after_dataset - rss_before_dataset, 0
        ),
        "total_peak_increment_bytes": max(
            rss_after_iteration - rss_before_dataset, 0
        ),
        "checksum": checksum,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="r002窗口数据加载小规模基准")
    parser.add_argument("--mode", choices=("legacy", "optimized"), required=True)
    parser.add_argument("--samples", type=int, default=DEFAULT_SAMPLE_COUNT)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.samples <= 0 or args.batch_size <= 0:
        raise ValueError("samples与batch-size必须为正整数")
    print(
        json.dumps(
            run_benchmark(
                args.mode,
                sample_count=args.samples,
                batch_size=args.batch_size,
            ),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

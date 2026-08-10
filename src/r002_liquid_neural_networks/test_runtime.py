"""r002正式运行性能修复与模型级续跑的定向回归测试。"""

from __future__ import annotations

from inspect import signature
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import torch
from torch import nn

from common.ml_pipeline import (
    FeaturePreprocessor,
    PanelWindowDataset,
    PreparedMLData,
)
from common.ml_training import (
    TrainingHistory,
    _build_loader,
    build_gru_regressor,
    predict_sequence_regressor,
)
from src.r002_liquid_neural_networks.config import M2_DEFAULT_CONFIG
from src.r002_liquid_neural_networks.main import (
    _artifact_from_cache,
    _build_runtime_identity,
)
from src.r002_liquid_neural_networks.runtime_cache import (
    RuntimeCacheError,
    RuntimeCacheFingerprintError,
    build_runtime_identity,
    derive_model_fingerprint,
    load_completed_model_cache,
    write_completed_model_cache,
)


FEATURE_COLUMNS = tuple(f"feature_{index}" for index in range(6))
WINDOW_LENGTH = 60


class _LegacyPanelWindowDataset:
    """修复前逐样本pandas iloc路径，仅供数值/顺序对照。"""

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


class _MeanRegressor(nn.Module):
    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        return inputs.mean(dim=(1, 2))


def _prepared_fixture(*, samples_per_split: int = 41) -> PreparedMLData:
    rng = np.random.default_rng(42)
    split_names = ("train", "validation", "backtest")
    sample_count = samples_per_split * len(split_names)
    panel_rows = sample_count + WINDOW_LENGTH - 1
    dates = pd.bdate_range("2010-01-01", periods=panel_rows)
    feature_panel = pd.DataFrame(
        rng.normal(size=(panel_rows, len(FEATURE_COLUMNS))),
        columns=FEATURE_COLUMNS,
    )
    feature_panel.insert(0, "date", dates)
    feature_panel.insert(0, "stock_code", "S000001")
    samples = pd.DataFrame(
        {
            "stock_code": [f"S{index:06d}" for index in range(sample_count)],
            "date": dates[:sample_count],
            "split": np.repeat(split_names, samples_per_split),
            "panel_row_start": np.arange(sample_count, dtype=np.int64),
            "panel_row_end": np.arange(sample_count, dtype=np.int64)
            + WINDOW_LENGTH
            - 1,
            "label": rng.normal(size=sample_count).astype(np.float32),
            "entry_date": dates[1 : sample_count + 1],
            "exit_date": dates[21 : sample_count + 21],
            "entry_tradable": True,
        }
    )
    backtest_first = samples.index[samples["split"].eq("backtest")][0]
    samples.loc[backtest_first, "label"] = np.nan
    zeros = pd.Series(0.0, index=FEATURE_COLUMNS)
    ones = pd.Series(1.0, index=FEATURE_COLUMNS)
    preprocessor = FeaturePreprocessor(
        feature_columns=FEATURE_COLUMNS,
        lower=zeros,
        upper=ones,
        mean=zeros,
        std=ones,
        fit_row_count=samples_per_split,
        fit_start=dates.min(),
        fit_end=dates.max(),
        lower_quantile=0.005,
        upper_quantile=0.995,
    )
    return PreparedMLData(
        feature_panel=feature_panel,
        samples=samples,
        feature_columns=FEATURE_COLUMNS,
        preprocessor=preprocessor,
        quality_summary={},
    )


def test_vectorized_dataset_matches_legacy_values_and_sampler_order() -> None:
    prepared = _prepared_fixture(samples_per_split=257)
    selected = prepared.samples.loc[prepared.samples["split"].eq("train")].reset_index(
        drop=True
    )
    legacy = _LegacyPanelWindowDataset(prepared.feature_panel, selected)
    optimized = prepared.dataset("train")
    explicit_indices = np.array([256, 0, 91, 17, 200, 3], dtype=np.int64)
    optimized_features, optimized_labels = optimized.__getitems__(explicit_indices)
    legacy_features = np.stack(
        [legacy[int(index)][0] for index in explicit_indices]
    )
    legacy_labels = np.array(
        [legacy[int(index)][1] for index in explicit_indices], dtype=np.float32
    )
    np.testing.assert_array_equal(optimized_features, legacy_features)
    np.testing.assert_array_equal(optimized_labels, legacy_labels)
    for index in explicit_indices:
        pd.testing.assert_series_equal(
            optimized.metadata(int(index)),
            selected.iloc[int(index)],
            check_names=True,
        )

    legacy_loader = _build_loader(
        legacy,
        batch_size=32,
        shuffle=True,
        seed=42,
        num_workers=0,
        pin_memory=False,
    )
    optimized_loader = _build_loader(
        optimized,
        batch_size=32,
        shuffle=True,
        seed=42,
        num_workers=0,
        pin_memory=False,
    )
    for legacy_batch, optimized_batch in zip(legacy_loader, optimized_loader):
        torch.testing.assert_close(optimized_batch[0], legacy_batch[0], rtol=0, atol=0)
        torch.testing.assert_close(optimized_batch[1], legacy_batch[1], rtol=0, atol=0)
    legacy_predictions = predict_sequence_regressor(
        _MeanRegressor(),
        dataset=legacy,
        batch_size=32,
        seed=42,
        num_workers=0,
        device="cpu",
    )
    optimized_predictions = predict_sequence_regressor(
        _MeanRegressor(),
        dataset=optimized,
        batch_size=32,
        seed=42,
        num_workers=0,
        device="cpu",
    )
    np.testing.assert_array_equal(optimized_predictions, legacy_predictions)


def test_split_counts_and_missing_backtest_label_prediction_contract() -> None:
    prepared = _prepared_fixture(samples_per_split=43)
    train = prepared.dataset("train")
    validation = prepared.dataset("validation")
    backtest = prepared.dataset("backtest")
    assert (len(train), len(validation), len(backtest)) == (43, 43, 43)
    assert np.isfinite(train.__getitems__(range(len(train)))[1]).all()
    assert np.isfinite(validation.__getitems__(range(len(validation)))[1]).all()
    assert np.isnan(backtest.__getitems__(range(len(backtest)))[1]).sum() == 1
    predictions = predict_sequence_regressor(
        _MeanRegressor(),
        dataset=backtest,
        batch_size=17,
        seed=42,
        num_workers=0,
        device="cpu",
    )
    assert len(predictions) == len(backtest)
    assert np.isfinite(predictions).all()


def test_completed_model_cache_first_write_restore_and_mismatch(
    tmp_path: Path,
) -> None:
    prepared = _prepared_fixture(samples_per_split=11)
    source_file = tmp_path / "source.parquet"
    code_file = tmp_path / "model.py"
    source_file.write_bytes(b"formal-source-content")
    code_file.write_text("MODEL_VERSION = 1\n", encoding="utf-8")
    identity = build_runtime_identity(
        report_id="r002_liquid_neural_networks",
        configs={"training": M2_DEFAULT_CONFIG},
        source_files=[source_file],
        code_files=[code_file],
        samples=prepared.samples,
        sample_columns=(
            "stock_code",
            "date",
            "split",
            "panel_row_start",
            "panel_row_end",
            "label",
        ),
        feature_values=prepared.standardized_feature_values,
        feature_columns=prepared.feature_columns,
        source_mode="test_fixture",
    )
    fingerprint, manifest = derive_model_fingerprint(
        identity,
        model_name="GRU",
        model_config={"hidden_size": 4, "seed": 42},
    )
    model_factory = lambda: build_gru_regressor(
        input_size=6,
        hidden_size=4,
        num_layers=1,
        dropout=0.0,
        output_size=1,
    )
    model = model_factory()
    checkpoint = tmp_path / "gru.pt"
    torch.save({"model_state_dict": model.state_dict()}, checkpoint)
    history = TrainingHistory(
        train_loss=(0.5, 0.4),
        validation_loss=(0.6, 0.45),
        best_epoch=2,
        best_validation_loss=0.45,
        stopped_early=False,
        epochs_completed=2,
    )
    prediction_values = np.linspace(-0.2, 0.2, 11, dtype=np.float64)
    artifact_resource = pd.DataFrame(
        [{"model": "GRU", "parameter_count": 149, "device": "cpu"}]
    )
    resource_row = artifact_resource.assign(
        batch_size=512, dtype="float32", framework="pytorch-test"
    )
    cache_path = tmp_path / "gru.complete.pt"
    assert load_completed_model_cache(
        cache_path,
        expected_fingerprint=fingerprint,
        expected_model_name="GRU",
        model_factory=model_factory,
        checkpoint_path=checkpoint,
    ) is None
    write_completed_model_cache(
        cache_path,
        fingerprint=fingerprint,
        fingerprint_manifest=manifest,
        model_name="GRU",
        model=model,
        history=history,
        training_resource_summary={"parameter_count": 149, "device": "cpu"},
        prediction_values=prediction_values,
        model_config={"model_name": "GRU", "seed": 42},
        artifact_resource_summary=artifact_resource,
        resource_row=resource_row,
        checkpoint_path=checkpoint,
    )
    restored = load_completed_model_cache(
        cache_path,
        expected_fingerprint=fingerprint,
        expected_model_name="GRU",
        model_factory=model_factory,
        checkpoint_path=checkpoint,
    )
    assert restored is not None
    np.testing.assert_array_equal(restored.prediction_values, prediction_values)
    assert restored.history == history
    pd.testing.assert_frame_equal(
        restored.artifact_resource_summary, artifact_resource, check_dtype=False
    )
    pd.testing.assert_frame_equal(restored.resource_row, resource_row, check_dtype=False)
    for name, expected in model.state_dict().items():
        torch.testing.assert_close(restored.model.state_dict()[name], expected)

    artifact = _artifact_from_cache(
        restored,
        prepared=prepared,
        model_name="GRU",
        checkpoint_path=checkpoint,
        comparison_config=M2_DEFAULT_CONFIG,
    )
    expected_metadata = prepared.samples.loc[
        prepared.samples["split"].eq("backtest"),
        ["stock_code", "date", "label", "entry_date", "exit_date", "entry_tradable"],
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        artifact.predictions.loc[:, expected_metadata.columns],
        expected_metadata,
        check_dtype=False,
        check_exact=True,
    )
    np.testing.assert_array_equal(
        artifact.predictions["prediction"].to_numpy(), prediction_values
    )
    assert artifact.loss_curve.to_dict("list") == history.to_frame().to_dict("list")

    with pytest.raises(RuntimeCacheFingerprintError, match="名称不一致"):
        load_completed_model_cache(
            cache_path,
            expected_fingerprint=fingerprint,
            expected_model_name="LTC",
            model_factory=model_factory,
            checkpoint_path=checkpoint,
        )

    checkpoint_bytes = checkpoint.read_bytes()
    checkpoint.write_bytes(checkpoint_bytes + b"tampered")
    with pytest.raises(RuntimeCacheError, match="检查点内容不一致"):
        load_completed_model_cache(
            cache_path,
            expected_fingerprint=fingerprint,
            expected_model_name="GRU",
            model_factory=model_factory,
            checkpoint_path=checkpoint,
        )
    checkpoint.write_bytes(checkpoint_bytes)

    truncated_cache = tmp_path / "gru.truncated.pt"
    cache_bytes = cache_path.read_bytes()
    truncated_cache.write_bytes(cache_bytes[: len(cache_bytes) // 2])
    with pytest.raises(RuntimeCacheError, match="无法安全读取"):
        load_completed_model_cache(
            truncated_cache,
            expected_fingerprint=fingerprint,
            expected_model_name="GRU",
            model_factory=model_factory,
            checkpoint_path=checkpoint,
        )

    changed_fingerprint, _ = derive_model_fingerprint(
        identity,
        model_name="GRU",
        model_config={"hidden_size": 4, "seed": 43},
    )
    with pytest.raises(RuntimeCacheFingerprintError, match="指纹不一致"):
        load_completed_model_cache(
            cache_path,
            expected_fingerprint=changed_fingerprint,
            expected_model_name="GRU",
            model_factory=model_factory,
            checkpoint_path=checkpoint,
        )


def test_runtime_identity_changes_with_source_config_code_or_sample(tmp_path: Path) -> None:
    prepared = _prepared_fixture(samples_per_split=3)
    source_file = tmp_path / "source.parquet"
    code_file = tmp_path / "model.py"
    data_loader_file = tmp_path / "data_loader.py"
    source_file.write_bytes(b"source-v1")
    code_file.write_text("VERSION = 1\n", encoding="utf-8")
    data_loader_file.write_text("LOADER_VERSION = 1\n", encoding="utf-8")

    def identity_digest(
        config_seed: int,
        *,
        feature_values: np.ndarray | None = None,
        source_mode: str = "formal_local_parquet",
    ) -> str:
        return build_runtime_identity(
            report_id="r002_liquid_neural_networks",
            configs={"m1": {"seed": config_seed}, "m2": {}, "m3": {}},
            source_files=[source_file],
            code_files=[code_file, data_loader_file],
            samples=prepared.samples,
            sample_columns=("stock_code", "date", "split", "label"),
            feature_values=(
                prepared.standardized_feature_values
                if feature_values is None
                else feature_values
            ),
            feature_columns=prepared.feature_columns,
            source_mode=source_mode,
        ).digest

    baseline = identity_digest(42)
    assert identity_digest(43) != baseline
    assert identity_digest(42, source_mode="synthetic_smoke") != baseline
    source_file.write_bytes(b"source-v2")
    source_changed = identity_digest(42)
    assert source_changed != baseline
    source_file.write_bytes(b"source-v1")
    code_file.write_text("VERSION = 2\n", encoding="utf-8")
    assert identity_digest(42) != baseline
    code_file.write_text("VERSION = 1\n", encoding="utf-8")
    data_loader_file.write_text("LOADER_VERSION = 2\n", encoding="utf-8")
    assert identity_digest(42) != baseline
    data_loader_file.write_text("LOADER_VERSION = 1\n", encoding="utf-8")

    changed_features = prepared.standardized_feature_values.copy()
    changed_features[0, 0] = np.nextafter(
        changed_features[0, 0], np.float32(np.inf), dtype=np.float32
    )
    assert identity_digest(42, feature_values=changed_features) != baseline

    features_with_nan = prepared.standardized_feature_values.copy()
    features_with_nan[0, 0] = np.nan
    big_endian_features = features_with_nan.astype(">f4")
    assert identity_digest(42, feature_values=features_with_nan) == identity_digest(
        42, feature_values=big_endian_features
    )

    prepared.samples.loc[0, "label"] += 1.0
    assert identity_digest(42) != baseline
    identity_parameters = signature(_build_runtime_identity).parameters
    assert "m4" not in identity_parameters
    assert "m5" not in identity_parameters

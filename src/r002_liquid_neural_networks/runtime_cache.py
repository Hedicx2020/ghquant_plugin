"""r002正式运行的严格指纹与模型完成态缓存。

缓存只保存已经完成训练、最佳检查点恢复及完整回测段预测的单模型中间态。
它不是最终复现产物；后续五模型合并、组合回测、指标和图表仍由main完整重算。
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sys
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import pandas as pd
import torch
from torch import nn

from common.ml_training import TrainingHistory


CACHE_SCHEMA_VERSION = 1
FILE_HASH_CHUNK_BYTES = 4 * 1024 * 1024
SAMPLE_HASH_CHUNK_ROWS = 100_000
FEATURE_HASH_CHUNK_ROWS = 100_000
CANONICAL_FLOAT32_NAN_BITS = np.uint32(0x7FC00000)


class RuntimeCacheError(RuntimeError):
    """模型完成态缓存损坏或不完整。"""


class RuntimeCacheFingerprintError(RuntimeCacheError):
    """现存缓存与本次源码、配置或数据指纹不一致，必须拒绝恢复。"""


@dataclass(frozen=True)
class RuntimeIdentity:
    """全链路共享身份；每个模型在此基础上追加模型名与配置。"""

    digest: str
    manifest: dict[str, Any]


@dataclass
class CachedModelState:
    """通过严格校验后恢复出的单模型运行态。"""

    model: nn.Module
    history: TrainingHistory
    training_resource_summary: dict[str, Any]
    prediction_values: np.ndarray
    model_config: dict[str, Any]
    artifact_resource_summary: pd.DataFrame
    resource_row: pd.DataFrame


def _package_version(package_name: str) -> str:
    try:
        return version(package_name)
    except PackageNotFoundError:
        return "not_installed"


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, Path):
        return str(value.expanduser().resolve())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if pd.isna(value):
        return None
    return str(value)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def sha256_file(path: Path) -> str:
    """流式计算文件内容SHA256，避免用mtime/size冒充内容指纹。"""
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"指纹源文件不存在: {resolved}")
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        while chunk := stream.read(FILE_HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def _file_manifest(paths: Sequence[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted({Path(item).expanduser().resolve() for item in paths}):
        stat = path.stat()
        records.append(
            {
                "path": str(path),
                "size_bytes": int(stat.st_size),
                "sha256": sha256_file(path),
            }
        )
    return records


def _sample_manifest(
    samples: pd.DataFrame,
    *,
    columns: Sequence[str],
) -> dict[str, Any]:
    missing = [column for column in columns if column not in samples.columns]
    if missing:
        raise KeyError(f"样本指纹缺少字段: {missing}")
    digest = hashlib.sha256()
    selected_columns = list(columns)
    for start in range(0, len(samples), SAMPLE_HASH_CHUNK_ROWS):
        chunk = samples.iloc[start : start + SAMPLE_HASH_CHUNK_ROWS].loc[
            :, selected_columns
        ]
        row_hashes = pd.util.hash_pandas_object(
            chunk, index=False, categorize=True
        ).to_numpy(dtype=np.uint64, copy=False)
        digest.update(row_hashes.tobytes(order="C"))
    return {
        "row_count": int(len(samples)),
        "columns": selected_columns,
        "dtypes": {column: str(samples[column].dtype) for column in selected_columns},
        "row_hash_method": "pandas_hash_pandas_object_uint64_chunks",
        "sha256": digest.hexdigest(),
    }


def _feature_manifest(
    feature_values: np.ndarray,
    *,
    feature_columns: Sequence[str],
) -> dict[str, Any]:
    """分块哈希模型实际消费的float32底板，规范字节序与NaN位型。

    正式底板是C连续的本机float32，因此常规路径只创建行分块view并直接把
    memoryview交给hashlib；不会复制整张特征表。只有非小端或含NaN时才复制
    当前最多 ``FEATURE_HASH_CHUNK_ROWS`` 行，分别转为little-endian float32
    或把所有NaN payload统一为quiet-NaN ``0x7fc00000``。
    """
    values = np.asarray(feature_values)
    if values.ndim != 2:
        raise ValueError("特征底板必须为[rows, features]二维数组")
    if values.dtype.kind != "f" or values.dtype.itemsize != np.dtype(np.float32).itemsize:
        raise TypeError("特征底板必须为float32数值数组")
    columns = [str(column) for column in feature_columns]
    if values.shape[1] != len(columns):
        raise ValueError("特征底板列数与feature_columns不一致")

    digest = hashlib.sha256()
    nan_count = 0
    canonical_dtype = np.dtype("<f4")
    for start in range(0, len(values), FEATURE_HASH_CHUNK_ROWS):
        source_chunk = values[start : start + FEATURE_HASH_CHUNK_ROWS]
        canonical = np.asarray(source_chunk, dtype=canonical_dtype, order="C")
        nan_mask = np.isnan(canonical)
        chunk_nan_count = int(nan_mask.sum())
        if chunk_nan_count:
            canonical = canonical.copy()
            canonical.view("<u4")[nan_mask] = CANONICAL_FLOAT32_NAN_BITS
            nan_count += chunk_nan_count
        if not canonical.flags.c_contiguous:
            canonical = np.ascontiguousarray(canonical)
        digest.update(memoryview(canonical).cast("B"))
    return {
        "shape": [int(size) for size in values.shape],
        "source_dtype": values.dtype.name,
        "canonical_dtype": canonical_dtype.str,
        "feature_columns": columns,
        "nan_count": nan_count,
        "hash_method": "row_chunks_little_endian_float32_c_order_canonical_nan",
        "sha256": digest.hexdigest(),
    }


def build_runtime_identity(
    *,
    report_id: str,
    configs: Mapping[str, Any],
    source_files: Sequence[Path],
    code_files: Sequence[Path],
    samples: pd.DataFrame,
    sample_columns: Sequence[str],
    feature_values: np.ndarray,
    feature_columns: Sequence[str],
    source_mode: str,
    extra: Mapping[str, Any] | None = None,
) -> RuntimeIdentity:
    """构造覆盖配置、源Parquet内容、关键源码和样本键的严格身份。"""
    manifest = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "report_id": report_id,
        "source_mode": source_mode,
        "configs": _jsonable(configs),
        "source_files": _file_manifest(source_files),
        "code_files": _file_manifest(code_files),
        "samples": _sample_manifest(samples, columns=sample_columns),
        "standardized_features": _feature_manifest(
            feature_values, feature_columns=feature_columns
        ),
        "environment": {
            "python": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": sys.platform,
            "machine": platform.machine(),
            "torch": torch.__version__,
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "ncps": _package_version("ncps"),
        },
        "extra": _jsonable({} if extra is None else extra),
    }
    digest = hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()
    return RuntimeIdentity(digest=digest, manifest=manifest)


def derive_model_fingerprint(
    identity: RuntimeIdentity,
    *,
    model_name: str,
    model_config: Mapping[str, Any],
) -> tuple[str, dict[str, Any]]:
    """在全链路身份上追加当前模型配置，生成模型完成态指纹。"""
    manifest = {
        "runtime_identity_sha256": identity.digest,
        "runtime_identity_manifest": identity.manifest,
        "model_name": model_name,
        "model_config": _jsonable(model_config),
    }
    digest = hashlib.sha256(_canonical_json(manifest).encode("utf-8")).hexdigest()
    return digest, manifest


def _frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return _jsonable(frame.to_dict(orient="records"))


def write_completed_model_cache(
    path: Path,
    *,
    fingerprint: str,
    fingerprint_manifest: Mapping[str, Any],
    model_name: str,
    model: nn.Module,
    history: TrainingHistory,
    training_resource_summary: Mapping[str, Any],
    prediction_values: np.ndarray,
    model_config: Mapping[str, Any],
    artifact_resource_summary: pd.DataFrame,
    resource_row: pd.DataFrame,
    checkpoint_path: Path,
) -> None:
    """原子写入单模型完成态；调用方必须在完整预测结束后才调用。"""
    cache_path = Path(path)
    checkpoint = Path(checkpoint_path)
    if not checkpoint.is_file():
        raise RuntimeCacheError(f"完成态缓存要求最佳检查点已存在: {checkpoint}")
    values = np.asarray(prediction_values, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise RuntimeCacheError("完成态缓存只接受一维有限完整预测")
    state_dict = {
        name: tensor.detach().cpu().clone()
        for name, tensor in model.state_dict().items()
    }
    metadata = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "complete": True,
        "fingerprint": fingerprint,
        "fingerprint_manifest": _jsonable(fingerprint_manifest),
        "model_name": model_name,
        "history": _jsonable(asdict(history)),
        "training_resource_summary": _jsonable(training_resource_summary),
        "prediction_count": int(len(values)),
        "model_config": _jsonable(model_config),
        "artifact_resource_summary": _frame_records(artifact_resource_summary),
        "artifact_resource_columns": list(artifact_resource_summary.columns),
        "resource_row": _frame_records(resource_row),
        "resource_row_columns": list(resource_row.columns),
        "checkpoint_sha256": sha256_file(checkpoint),
    }
    payload = {
        "metadata_json": _canonical_json(metadata),
        "model_state_dict": state_dict,
        "prediction_values": torch.from_numpy(values.copy()),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_name(f".{cache_path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            torch.save(payload, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(cache_path)
    finally:
        temporary.unlink(missing_ok=True)


def load_completed_model_cache(
    path: Path,
    *,
    expected_fingerprint: str,
    expected_model_name: str,
    model_factory: Callable[[], nn.Module],
    checkpoint_path: Path,
) -> CachedModelState | None:
    """恢复完全匹配的模型完成态；不存在返回None，不匹配则明确拒绝。"""
    cache_path = Path(path)
    if not cache_path.exists():
        return None
    if not cache_path.is_file():
        raise RuntimeCacheError(f"模型缓存路径不是普通文件: {cache_path}")
    try:
        payload = torch.load(cache_path, map_location="cpu", weights_only=True)
        metadata = json.loads(payload["metadata_json"])
    except Exception as exc:
        raise RuntimeCacheError(f"模型完成态缓存无法安全读取: {cache_path}") from exc
    if metadata.get("schema_version") != CACHE_SCHEMA_VERSION or not metadata.get(
        "complete"
    ):
        raise RuntimeCacheError(f"模型完成态缓存schema或complete标记无效: {cache_path}")
    actual_fingerprint = str(metadata.get("fingerprint", ""))
    if actual_fingerprint != expected_fingerprint:
        raise RuntimeCacheFingerprintError(
            "模型完成态缓存指纹不一致，拒绝恢复: "
            f"model={expected_model_name}, expected={expected_fingerprint}, "
            f"actual={actual_fingerprint}, cache={cache_path}"
        )
    if metadata.get("model_name") != expected_model_name:
        raise RuntimeCacheFingerprintError(
            f"模型完成态缓存名称不一致，拒绝恢复: {cache_path}"
        )
    checkpoint = Path(checkpoint_path)
    if not checkpoint.is_file():
        raise RuntimeCacheError(f"缓存对应最佳检查点缺失: {checkpoint}")
    if sha256_file(checkpoint) != metadata.get("checkpoint_sha256"):
        raise RuntimeCacheError(f"缓存对应最佳检查点内容不一致: {checkpoint}")

    model = model_factory()
    if not isinstance(model, nn.Module):
        raise TypeError("model_factory 必须返回torch.nn.Module")
    model.load_state_dict(payload["model_state_dict"], strict=True)
    prediction_values = payload["prediction_values"].detach().cpu().numpy().astype(
        np.float64, copy=False
    )
    if prediction_values.ndim != 1 or not np.isfinite(prediction_values).all():
        raise RuntimeCacheError(f"缓存预测不是一维有限数组: {cache_path}")
    if len(prediction_values) != int(metadata["prediction_count"]):
        raise RuntimeCacheError(f"缓存预测长度与元数据不一致: {cache_path}")
    history_payload = metadata["history"]
    history = TrainingHistory(
        train_loss=tuple(float(value) for value in history_payload["train_loss"]),
        validation_loss=tuple(
            float(value) for value in history_payload["validation_loss"]
        ),
        best_epoch=int(history_payload["best_epoch"]),
        best_validation_loss=float(history_payload["best_validation_loss"]),
        stopped_early=bool(history_payload["stopped_early"]),
        epochs_completed=int(history_payload["epochs_completed"]),
    )
    return CachedModelState(
        model=model,
        history=history,
        training_resource_summary=dict(metadata["training_resource_summary"]),
        prediction_values=prediction_values,
        model_config=dict(metadata["model_config"]),
        artifact_resource_summary=pd.DataFrame(
            metadata["artifact_resource_summary"],
            columns=metadata["artifact_resource_columns"],
        ),
        resource_row=pd.DataFrame(
            metadata["resource_row"], columns=metadata["resource_row_columns"]
        ),
    )

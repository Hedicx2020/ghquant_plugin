"""机器学习研报共用的序列回归训练与预测接口。

本模块把数据加载、损失、优化、早停、检查点和样本外预测固定在同一条
训练路径中；具体模型只需替换 ``SequenceRegressor`` 接收的 backbone。
训练函数只接收训练集与验证集，回测集只能在模型选择结束后单独预测，
从接口上避免把回测段用于调参。
"""

from __future__ import annotations

import copy
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

import numpy as np
import pandas as pd

try:
    import torch
    from torch import nn
    from torch.utils.data import DataLoader
except ImportError as exc:  # pragma: no cover - 仅在缺少可选运行环境时触发
    raise ImportError(
        "common.ml_training 需要 PyTorch；请按项目 pyproject 安装依赖后再运行模型训练"
    ) from exc


@runtime_checkable
class SequenceRegressionDataset(Protocol):
    """惰性序列回归数据集协议，兼容 ``PanelWindowDataset``。

    训练/验证调用要求标签有限；独立预测调用允许标签为NaN，因为预测路径
    只消费特征窗口。
    """

    def __len__(self) -> int:
        """返回样本数量。"""

    def __getitem__(self, index: int) -> tuple[np.ndarray, np.float32]:
        """返回特征窗口与标签占位；预测段标签允许为NaN。"""


@dataclass(frozen=True)
class TrainingSettings:
    """一次受控比较实验的完整训练设置。"""

    batch_size: int
    learning_rate: float
    max_epochs: int
    patience: int
    seed: int
    loss_name: str
    optimizer_name: str
    weight_decay: float
    min_delta: float
    num_workers: int
    shuffle_training: bool
    device: str
    deterministic_warn_only: bool

    def __post_init__(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size 必须为正整数")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate 必须为正数")
        if self.max_epochs <= 0 or self.patience <= 0:
            raise ValueError("max_epochs 与 patience 必须为正整数")
        if self.weight_decay < 0 or self.min_delta < 0:
            raise ValueError("weight_decay 与 min_delta 不得为负")
        if self.num_workers < 0:
            raise ValueError("num_workers 不得为负")
        if self.loss_name.lower() != "mse":
            raise ValueError("受控比较框架当前只允许 MSE 损失")
        if self.optimizer_name.lower() != "adam":
            raise ValueError("受控比较框架当前只允许 Adam 优化器")


@dataclass(frozen=True)
class TrainingHistory:
    """训练/验证损失及早停审计记录。"""

    train_loss: tuple[float, ...]
    validation_loss: tuple[float, ...]
    best_epoch: int
    best_validation_loss: float
    stopped_early: bool
    epochs_completed: int

    def to_frame(self) -> pd.DataFrame:
        """返回一行一个 epoch 的训练曲线。"""
        epochs = np.arange(1, self.epochs_completed + 1, dtype=np.int64)
        return pd.DataFrame(
            {
                "epoch": epochs,
                "train_loss": self.train_loss,
                "validation_loss": self.validation_loss,
                "is_best_epoch": epochs == self.best_epoch,
            }
        )


@dataclass
class TrainingResult:
    """最佳模型、损失曲线、资源记录与检查点位置。"""

    model: nn.Module
    history: TrainingHistory
    resource_summary: dict[str, Any]
    checkpoint_path: Path


class GRUBackbone(nn.Module):
    """返回最后一层最后时点隐藏状态的单向 GRU 主干。"""

    def __init__(
        self,
        *,
        input_size: int,
        hidden_size: int,
        num_layers: int,
        dropout: float,
    ) -> None:
        super().__init__()
        if input_size <= 0 or hidden_size <= 0 or num_layers <= 0:
            raise ValueError("GRU 的 input_size/hidden_size/num_layers 必须为正整数")
        if not 0.0 <= dropout < 1.0:
            raise ValueError("GRU dropout 必须位于 [0, 1)")
        self.output_size = hidden_size
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            dropout=dropout,
            batch_first=True,
            bidirectional=False,
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        """输入 ``[batch,time,features]``，输出 ``[batch,hidden]``。"""
        if inputs.ndim != 3:
            raise ValueError("GRU 输入必须为 [batch,time,features] 三维张量")
        _, hidden = self.gru(inputs)
        return hidden[-1]


class SequenceRegressor(nn.Module):
    """主干加线性输出头；后续模型只需替换主干。"""

    def __init__(self, backbone: nn.Module, *, backbone_output_size: int, output_size: int) -> None:
        super().__init__()
        if backbone_output_size <= 0 or output_size <= 0:
            raise ValueError("backbone_output_size 与 output_size 必须为正整数")
        self.backbone = backbone
        self.output_head = nn.Linear(backbone_output_size, output_size)
        self.output_size = output_size

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        """提取主干隐藏状态并映射为连续收益预测。"""
        hidden = self.backbone(inputs)
        if not isinstance(hidden, torch.Tensor) or hidden.ndim != 2:
            raise ValueError("backbone 必须返回 [batch,hidden] 二维张量")
        predictions = self.output_head(hidden)
        return predictions.squeeze(-1) if self.output_size == 1 else predictions


def build_gru_regressor(
    *,
    input_size: int,
    hidden_size: int,
    num_layers: int,
    dropout: float,
    output_size: int,
) -> SequenceRegressor:
    """构造单向 GRU 主干与线性回归输出头。"""
    backbone = GRUBackbone(
        input_size=input_size,
        hidden_size=hidden_size,
        num_layers=num_layers,
        dropout=dropout,
    )
    return SequenceRegressor(
        backbone,
        backbone_output_size=backbone.output_size,
        output_size=output_size,
    )


def set_reproducible_seed(seed: int, *, deterministic_warn_only: bool) -> None:
    """固定 Python、NumPy 与 PyTorch 随机性。"""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if hasattr(torch.backends, "cudnn"):
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True, warn_only=deterministic_warn_only)


def resolve_device(requested: str) -> torch.device:
    """解析明确设备或按 CUDA→MPS→CPU 顺序选择可用设备。"""
    normalized = requested.lower()
    if normalized == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    device = torch.device(normalized)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("配置要求 CUDA，但当前 PyTorch 未检测到 CUDA")
    if device.type == "mps" and not (
        hasattr(torch.backends, "mps") and torch.backends.mps.is_available()
    ):
        raise RuntimeError("配置要求 MPS，但当前 PyTorch 未检测到 MPS")
    return device


def _build_loader(
    dataset: SequenceRegressionDataset,
    *,
    batch_size: int,
    shuffle: bool,
    seed: int,
    num_workers: int,
    pin_memory: bool,
) -> DataLoader:
    if len(dataset) == 0:
        raise ValueError("训练或预测数据集不得为空")
    generator = torch.Generator()
    generator.manual_seed(seed)
    loader_kwargs: dict[str, Any] = {}
    if getattr(dataset, "supports_prebatched_fetch", False):
        loader_kwargs["collate_fn"] = _collate_prebatched_arrays
    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        num_workers=num_workers,
        pin_memory=pin_memory,
        generator=generator,
        drop_last=False,
        **loader_kwargs,
    )


def _collate_prebatched_arrays(
    batch: tuple[np.ndarray, np.ndarray],
) -> tuple[torch.Tensor, torch.Tensor]:
    """把Dataset整批生成的连续数组各转换一次，保持Sampler给定顺序。"""
    if not isinstance(batch, tuple) or len(batch) != 2:
        raise TypeError("预批量数据必须是(features, labels)二元组")
    features, labels = batch
    if not isinstance(features, np.ndarray) or not isinstance(labels, np.ndarray):
        raise TypeError("预批量features/labels必须是NumPy数组")
    if features.ndim != 3 or labels.ndim != 1:
        raise ValueError("预批量形状必须为[batch,time,features]和[batch]")
    if features.shape[0] != labels.shape[0]:
        raise ValueError("预批量features/labels样本数不一致")
    return torch.from_numpy(features), torch.from_numpy(labels)


def _unpack_features(
    batch: Sequence[torch.Tensor] | torch.Tensor,
    device: torch.device,
) -> torch.Tensor:
    """纯预测只解包并校验特征，绝不读取或筛选标签。"""
    if isinstance(batch, torch.Tensor):
        feature_values = batch
    else:
        if len(batch) < 1:
            raise ValueError("预测 batch 至少必须包含特征")
        feature_values = batch[0]
    features = torch.as_tensor(feature_values, dtype=torch.float32, device=device)
    if features.ndim != 3:
        raise ValueError("batch 特征必须为 [batch,time,features] 三维张量")
    if not torch.isfinite(features).all():
        raise ValueError("batch 特征含 NaN 或无穷值")
    return features


def _unpack_batch(
    batch: Sequence[torch.Tensor],
    device: torch.device,
) -> tuple[torch.Tensor, torch.Tensor]:
    """训练/验证严格解包特征与有限标签。"""
    if len(batch) != 2:
        raise ValueError("序列回归 batch 必须仅包含特征和标签")
    features = _unpack_features(batch, device)
    labels = torch.as_tensor(batch[1], dtype=torch.float32, device=device).reshape(-1)
    if features.shape[0] != labels.shape[0]:
        raise ValueError("batch 特征与标签样本数须一致")
    if not torch.isfinite(labels).all():
        raise ValueError("训练或验证 batch 标签含 NaN 或无穷值")
    return features, labels


def _mean_epoch_loss(
    model: nn.Module,
    loader: DataLoader,
    loss_function: nn.Module,
    device: torch.device,
    optimizer: torch.optim.Optimizer | None,
) -> float:
    training = optimizer is not None
    model.train(training)
    weighted_loss = 0.0
    sample_count = 0
    context = torch.enable_grad() if training else torch.inference_mode()
    with context:
        for batch in loader:
            features, labels = _unpack_batch(batch, device)
            if training:
                optimizer.zero_grad(set_to_none=True)
            predictions = model(features).reshape(-1)
            if predictions.shape != labels.shape:
                raise ValueError("模型预测形状与标签不一致")
            loss = loss_function(predictions, labels)
            if not torch.isfinite(loss):
                raise FloatingPointError("训练或验证损失出现 NaN/无穷值")
            if training:
                loss.backward()
                optimizer.step()
            count = labels.shape[0]
            weighted_loss += float(loss.detach().cpu()) * count
            sample_count += count
    if sample_count == 0:
        raise ValueError("训练或验证 loader 未产生样本")
    return weighted_loss / sample_count


def _portable_state_dict(model: nn.Module) -> dict[str, torch.Tensor]:
    return {
        name: tensor.detach().cpu().clone()
        for name, tensor in model.state_dict().items()
    }


def _write_checkpoint(
    path: Path,
    *,
    model_state: dict[str, torch.Tensor],
    optimizer_state: dict[str, Any],
    epoch: int,
    validation_loss: float,
    settings: TrainingSettings,
    model_metadata: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    torch.save(
        {
            "model_state_dict": model_state,
            "optimizer_state_dict": optimizer_state,
            "epoch": epoch,
            "validation_loss": validation_loss,
            "training_settings": asdict(settings),
            "model_metadata": copy.deepcopy(model_metadata),
        },
        temporary,
    )
    temporary.replace(path)


def _reset_device_memory(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    elif device.type == "mps" and hasattr(torch.mps, "empty_cache"):
        torch.mps.empty_cache()


def _device_memory_summary(device: torch.device) -> tuple[int | None, str]:
    if device.type == "cuda":
        return int(torch.cuda.max_memory_allocated(device)), "cuda_max_memory_allocated"
    if device.type == "mps" and hasattr(torch.mps, "current_allocated_memory"):
        return int(torch.mps.current_allocated_memory()), "mps_current_allocated_after_fit"
    return None, "not_available_on_cpu"


def summarize_model_resources(
    model: nn.Module,
    *,
    device: torch.device,
) -> dict[str, Any]:
    """记录参数量及设备可提供的内存观测值，不伪造 CPU 显存。"""
    allocated_bytes, measurement = _device_memory_summary(device)
    return {
        "parameter_count": int(sum(parameter.numel() for parameter in model.parameters())),
        "trainable_parameter_count": int(
            sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
        ),
        "device": str(device),
        "device_memory_bytes": allocated_bytes,
        "device_memory_measurement": measurement,
    }


def train_sequence_regressor(
    model_factory: Callable[[], nn.Module],
    *,
    train_dataset: SequenceRegressionDataset,
    validation_dataset: SequenceRegressionDataset,
    settings: TrainingSettings,
    checkpoint_path: Path,
    model_metadata: dict[str, Any] | None = None,
) -> TrainingResult:
    """用训练集拟合、只用验证集早停并恢复最佳模型。

    函数签名刻意不接收回测集，确保回测段无法参与损失监控或模型选择。
    """
    set_reproducible_seed(
        settings.seed,
        deterministic_warn_only=settings.deterministic_warn_only,
    )
    device = resolve_device(settings.device)
    model = model_factory()
    if not isinstance(model, nn.Module):
        raise TypeError("model_factory 必须返回 torch.nn.Module")
    model = model.to(device)
    _reset_device_memory(device)
    pin_memory = device.type == "cuda"
    train_loader = _build_loader(
        train_dataset,
        batch_size=settings.batch_size,
        shuffle=settings.shuffle_training,
        seed=settings.seed,
        num_workers=settings.num_workers,
        pin_memory=pin_memory,
    )
    validation_loader = _build_loader(
        validation_dataset,
        batch_size=settings.batch_size,
        shuffle=False,
        seed=settings.seed,
        num_workers=settings.num_workers,
        pin_memory=pin_memory,
    )
    loss_function = nn.MSELoss(reduction="mean")
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=settings.learning_rate,
        weight_decay=settings.weight_decay,
    )

    train_losses: list[float] = []
    validation_losses: list[float] = []
    best_validation_loss = float("inf")
    best_epoch = 0
    stale_epochs = 0
    best_state: dict[str, torch.Tensor] | None = None
    metadata = {} if model_metadata is None else model_metadata

    for epoch in range(1, settings.max_epochs + 1):
        train_loss = _mean_epoch_loss(model, train_loader, loss_function, device, optimizer)
        validation_loss = _mean_epoch_loss(
            model,
            validation_loader,
            loss_function,
            device,
            optimizer=None,
        )
        train_losses.append(train_loss)
        validation_losses.append(validation_loss)
        improved = validation_loss < best_validation_loss - settings.min_delta
        if improved:
            best_validation_loss = validation_loss
            best_epoch = epoch
            stale_epochs = 0
            best_state = _portable_state_dict(model)
            _write_checkpoint(
                Path(checkpoint_path),
                model_state=best_state,
                optimizer_state=optimizer.state_dict(),
                epoch=epoch,
                validation_loss=validation_loss,
                settings=settings,
                model_metadata=metadata,
            )
        else:
            stale_epochs += 1
        if stale_epochs >= settings.patience:
            break

    if best_state is None or best_epoch == 0:
        raise RuntimeError("训练结束但未产生有效最佳检查点")
    model.load_state_dict(best_state)
    epochs_completed = len(train_losses)
    history = TrainingHistory(
        train_loss=tuple(train_losses),
        validation_loss=tuple(validation_losses),
        best_epoch=best_epoch,
        best_validation_loss=best_validation_loss,
        stopped_early=epochs_completed < settings.max_epochs,
        epochs_completed=epochs_completed,
    )
    return TrainingResult(
        model=model,
        history=history,
        resource_summary=summarize_model_resources(model, device=device),
        checkpoint_path=Path(checkpoint_path),
    )


def predict_sequence_regressor(
    model: nn.Module,
    *,
    dataset: SequenceRegressionDataset,
    batch_size: int,
    seed: int,
    num_workers: int,
    device: str,
) -> np.ndarray:
    """对模型选择完成后的独立数据集生成顺序稳定的预测。"""
    set_reproducible_seed(seed, deterministic_warn_only=True)
    resolved_device = resolve_device(device)
    model = model.to(resolved_device)
    loader = _build_loader(
        dataset,
        batch_size=batch_size,
        shuffle=False,
        seed=seed,
        num_workers=num_workers,
        pin_memory=resolved_device.type == "cuda",
    )
    predictions: list[np.ndarray] = []
    model.eval()
    with torch.inference_mode():
        for batch in loader:
            features = _unpack_features(batch, resolved_device)
            output = model(features).reshape(-1)
            if not torch.isfinite(output).all():
                raise FloatingPointError("样本外预测含 NaN 或无穷值")
            predictions.append(output.detach().cpu().numpy())
    return np.concatenate(predictions).astype(np.float64, copy=False)


def load_model_checkpoint(
    model: nn.Module,
    checkpoint_path: Path,
    *,
    map_location: str = "cpu",
) -> dict[str, Any]:
    """加载最佳模型检查点，并返回其审计元数据。"""
    path = Path(checkpoint_path)
    if not path.is_file():
        raise FileNotFoundError(f"模型检查点不存在: {path}")
    try:
        payload = torch.load(path, map_location=map_location, weights_only=True)
    except TypeError:  # 兼容较早 PyTorch
        payload = torch.load(path, map_location=map_location)
    model.load_state_dict(payload["model_state_dict"])
    return {
        "epoch": int(payload["epoch"]),
        "validation_loss": float(payload["validation_loss"]),
        "training_settings": payload["training_settings"],
        "model_metadata": payload["model_metadata"],
    }

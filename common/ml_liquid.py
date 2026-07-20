"""液态神经网络共用主干、连续时间辅助与可审计模型清单。

四类主干均直接调用固定依赖 ``ncps`` 的 PyTorch 实现；本模块不复刻或
猜测任何研报私有公式、参数或训练代码。输出统一适配
``common.ml_training.SequenceRegressor``，因此可与 GRU 共用损失、优化、
早停和样本外预测路径。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import metadata
from typing import Any, Literal

import numpy as np
import torch
from torch import nn

try:
    from ncps.torch import CfC, LTC
    from ncps.wirings import AutoNCP, Wiring
except ImportError as exc:  # pragma: no cover - 仅在依赖环境缺失时触发
    raise ImportError(
        "common.ml_liquid 需要固定commit的 ncps；请先同步项目依赖"
    ) from exc

from common.ml_training import SequenceRegressor


LiquidModelKind = Literal["ltc", "ncp_ltc", "cfc", "ncp_cfc"]
VectorField = Callable[[torch.Tensor, torch.Tensor], torch.Tensor]


def neural_ode_derivative(
    hidden: torch.Tensor,
    time: torch.Tensor,
    vector_field: VectorField,
) -> torch.Tensor:
    """计算 ``dh/dt=f(h,t,theta)``，并校验形状和数值有限性。"""
    if not isinstance(hidden, torch.Tensor) or not isinstance(time, torch.Tensor):
        raise TypeError("hidden 与 time 必须为 torch.Tensor")
    if hidden.numel() == 0 or time.numel() != 1:
        raise ValueError("hidden 不得为空，time 必须为单元素张量")
    if not torch.isfinite(hidden).all() or not torch.isfinite(time).all():
        raise ValueError("Neural ODE 输入含 NaN 或无穷值")
    derivative = vector_field(hidden, time)
    if not isinstance(derivative, torch.Tensor) or derivative.shape != hidden.shape:
        raise ValueError("向量场输出必须与 hidden 同形")
    if not torch.isfinite(derivative).all():
        raise FloatingPointError("Neural ODE 导数含 NaN 或无穷值")
    return derivative


def euler_residual_step(
    hidden: torch.Tensor,
    time: torch.Tensor,
    step_size: torch.Tensor,
    vector_field: VectorField,
) -> torch.Tensor:
    """用显式欧拉将连续导数离散为 ``h_next=h+dt*f(h,t)``。"""
    if not isinstance(step_size, torch.Tensor) or step_size.numel() != 1:
        raise ValueError("step_size 必须为单元素 torch.Tensor")
    if not torch.isfinite(step_size).all() or bool((step_size <= 0).item()):
        raise ValueError("step_size 必须为有限正数")
    next_hidden = hidden + step_size * neural_ode_derivative(hidden, time, vector_field)
    if not torch.isfinite(next_hidden).all():
        raise FloatingPointError("欧拉离散后的隐藏状态含 NaN 或无穷值")
    return next_hidden


def integrate_neural_ode_euler(
    initial_hidden: torch.Tensor,
    time_points: torch.Tensor,
    vector_field: VectorField,
) -> torch.Tensor:
    """在严格递增时间网格上积分，并返回 ``[time,...hidden_shape]`` 轨迹。"""
    if not isinstance(time_points, torch.Tensor) or time_points.ndim != 1:
        raise ValueError("time_points 必须为一维 torch.Tensor")
    if len(time_points) < 2 or not torch.isfinite(time_points).all():
        raise ValueError("time_points 至少含两个有限时点")
    if not bool(torch.all(time_points[1:] > time_points[:-1]).item()):
        raise ValueError("time_points 必须严格递增")
    state = initial_hidden
    trajectory = [state]
    for current_time, next_time in zip(time_points[:-1], time_points[1:]):
        state = euler_residual_step(
            state,
            current_time.reshape(1),
            (next_time - current_time).reshape(1),
            vector_field,
        )
        trajectory.append(state)
    return torch.stack(trajectory, dim=0)


class NcpsSequenceBackbone(nn.Module):
    """把 ``ncps`` 的 ``(readout,state)`` 接口转成统一二维主干输出。"""

    def __init__(
        self,
        *,
        model_kind: LiquidModelKind,
        recurrent_layer: nn.Module,
        output_size: int,
        wiring: Wiring | None,
        batch_first: bool,
        return_sequences: bool,
        mixed_memory: bool,
    ) -> None:
        super().__init__()
        if output_size <= 0:
            raise ValueError("液态主干 output_size 必须为正整数")
        if not batch_first or return_sequences or mixed_memory:
            raise ValueError(
                "统一训练接口要求 batch_first=True、return_sequences=False、mixed_memory=False"
            )
        self.model_kind = model_kind
        self.recurrent_layer = recurrent_layer
        self.output_size = output_size
        self.wiring = wiring
        self.batch_first = batch_first
        self.return_sequences = return_sequences
        self.mixed_memory = mixed_memory

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        """输入 ``[batch,time,features]``，返回最后读出 ``[batch,hidden]``。"""
        if inputs.ndim != 3:
            raise ValueError("液态网络输入必须为 [batch,time,features] 三维张量")
        if not torch.isfinite(inputs).all():
            raise ValueError("液态网络输入含 NaN 或无穷值")
        readout, _ = self.recurrent_layer(inputs)
        if not isinstance(readout, torch.Tensor) or readout.ndim != 2:
            raise ValueError("ncps 主干在 return_sequences=False 时必须返回二维读出")
        if readout.shape[1] != self.output_size:
            raise ValueError(
                f"ncps 主干读出维度不符: {readout.shape[1]} != {self.output_size}"
            )
        if not torch.isfinite(readout).all():
            raise FloatingPointError("液态网络主干输出含 NaN 或无穷值")
        return readout


def _validate_model_arguments(
    *,
    input_size: int,
    units: int,
    output_size: int,
    wiring_output_size: int,
    sparsity_level: float,
    ode_unfolds: int,
    cfc_mode: str,
) -> None:
    if min(input_size, units, output_size, wiring_output_size, ode_unfolds) <= 0:
        raise ValueError("模型维度与 ode_unfolds 必须为正整数")
    if not 0.0 < sparsity_level < 1.0:
        raise ValueError("AutoNCP sparsity_level 必须位于 (0,1)")
    if cfc_mode not in {"default", "pure", "no_gate"}:
        raise ValueError("CfC mode 仅允许 default/pure/no_gate")


def build_liquid_regressor(
    model_kind: LiquidModelKind,
    *,
    input_size: int,
    units: int,
    output_size: int,
    wiring_output_size: int,
    sparsity_level: float,
    wiring_seed: int,
    batch_first: bool,
    return_sequences: bool,
    mixed_memory: bool,
    ode_unfolds: int,
    cfc_mode: str,
) -> SequenceRegressor:
    """按 AS11 构造四类 ``ncps`` 主干及统一线性回归头。"""
    _validate_model_arguments(
        input_size=input_size,
        units=units,
        output_size=output_size,
        wiring_output_size=wiring_output_size,
        sparsity_level=sparsity_level,
        ode_unfolds=ode_unfolds,
        cfc_mode=cfc_mode,
    )
    if model_kind not in {"ltc", "ncp_ltc", "cfc", "ncp_cfc"}:
        raise ValueError(f"未知液态模型类型: {model_kind}")

    wiring: Wiring | None = None
    units_or_wiring: int | Wiring = units
    if model_kind in {"ncp_ltc", "ncp_cfc"}:
        wiring = AutoNCP(
            units,
            wiring_output_size,
            sparsity_level=sparsity_level,
            seed=wiring_seed,
        )
        units_or_wiring = wiring

    if model_kind in {"ltc", "ncp_ltc"}:
        recurrent = LTC(
            input_size=input_size,
            units=units_or_wiring,
            batch_first=batch_first,
            return_sequences=return_sequences,
            mixed_memory=mixed_memory,
            ode_unfolds=ode_unfolds,
        )
        if wiring is None:
            wiring = recurrent._wiring
    else:
        recurrent = CfC(
            input_size=input_size,
            units=units_or_wiring,
            batch_first=batch_first,
            return_sequences=return_sequences,
            mixed_memory=mixed_memory,
            mode=cfc_mode,
        )

    backbone_output_size = (
        wiring_output_size if model_kind in {"ncp_ltc", "ncp_cfc"} else units
    )
    backbone = NcpsSequenceBackbone(
        model_kind=model_kind,
        recurrent_layer=recurrent,
        output_size=backbone_output_size,
        wiring=wiring,
        batch_first=batch_first,
        return_sequences=return_sequences,
        mixed_memory=mixed_memory,
    )
    return SequenceRegressor(
        backbone,
        backbone_output_size=backbone.output_size,
        output_size=output_size,
    )


def summarize_liquid_wiring(model: nn.Module) -> dict[str, Any]:
    """汇总连接数量和密度；全连接 CfC 无显式 wiring 矩阵。"""
    if not isinstance(model, SequenceRegressor) or not isinstance(
        model.backbone, NcpsSequenceBackbone
    ):
        raise TypeError("model 必须是由 build_liquid_regressor 构造的模型")
    backbone = model.backbone
    wiring = backbone.wiring
    if wiring is None:
        return {
            "wiring_type": "fully_connected_cfc_cell",
            "wiring_units": backbone.output_size,
            "wiring_output_size": backbone.output_size,
            "wiring_layers": 1,
            "internal_synapse_count": None,
            "sensory_synapse_count": None,
            "overall_density": 1.0,
            "is_sparse_wiring": False,
        }
    internal_count = int(np.abs(wiring.adjacency_matrix).sum())
    sensory_count = int(np.abs(wiring.sensory_adjacency_matrix).sum())
    possible = wiring.units * wiring.units + wiring.input_dim * wiring.units
    density = float((internal_count + sensory_count) / possible)
    return {
        "wiring_type": type(wiring).__name__,
        "wiring_units": int(wiring.units),
        "wiring_output_size": int(wiring.output_dim),
        "wiring_layers": int(wiring.num_layers),
        "internal_synapse_count": internal_count,
        "sensory_synapse_count": sensory_count,
        "overall_density": density,
        "is_sparse_wiring": bool(density < 1.0),
    }


def assert_ncps_version(expected_version: str) -> str:
    """断言运行环境中的 ``ncps`` 包版本与固定依赖声明一致。"""
    actual_version = metadata.version("ncps")
    if actual_version != expected_version:
        raise RuntimeError(
            f"ncps 版本不符: actual={actual_version}, expected={expected_version}"
        )
    return actual_version


def build_liquid_model_manifest(
    models: Mapping[str, SequenceRegressor],
    *,
    expected_version: str,
    source_url: str,
    source_commit: str,
    source_license: str,
    method_scope: str,
) -> list[dict[str, Any]]:
    """生成包含依赖来源、参数量与 wiring 证据的模型 manifest。"""
    actual_version = assert_ncps_version(expected_version)
    records: list[dict[str, Any]] = []
    for model_name, model in models.items():
        if not isinstance(model.backbone, NcpsSequenceBackbone):
            raise TypeError(f"{model_name} 不是 ncps 液态主干")
        wiring_summary = summarize_liquid_wiring(model)
        records.append(
            {
                "model": model_name,
                "model_kind": model.backbone.model_kind,
                "parameter_count": int(sum(p.numel() for p in model.parameters())),
                "trainable_parameter_count": int(
                    sum(p.numel() for p in model.parameters() if p.requires_grad)
                ),
                "source_url": source_url,
                "source_commit": source_commit,
                "source_license": source_license,
                "package_version_expected": expected_version,
                "package_version_actual": actual_version,
                "method_scope": method_scope,
                **wiring_summary,
            }
        )
    return records

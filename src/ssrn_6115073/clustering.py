"""m3: 资产聚类分组（SU + 层次聚类 + Silhouette）· ssrn_6115073（市场迁移复现）

对齐要素：
  - F3（原文式9-14）：候选资产两两算互信息 MI[X,Y]=H[X]+H[Y]−H[X,Y]（式9）与对称不确定性
    SU=2·MI/(H[X]+H[Y])∈[0,1]（式14）；连续收益分箱离散化估熵（AS20）；**只用训练期收益**
    （spec F3「in-sample」/ 未来函数红线）。
  - F4（原文 p12-14, p46-47）：以 (1−SU) 为距离做凝聚层次聚类（scipy），Silhouette 定簇数 nc
    （AS2，nc 每期自动、搜索 2..10）；每簇取「离中心最近资产」（medoid）为代表（spec F4
    line146「asset nearest to the cluster's center」）。四聚类模型 hierarchical/K-means/GMM/DBSCAN
    × 两关系度量 SU/correlation 对比（R2/表1）。
  - R2（表1）：每配置用代表组合迷你评估（每簇选 medoid、等权、**训练期**算）打分
    SR/MDD/VaR/Frobenius——SR/MDD 复用 common.utils（import），VaR=历史模拟最低 5%（spec B7），
    Frobenius=‖CM−IM‖_F 分散化（越小越分散，spec B7/附录C，理想矩阵 IM=单位阵=资产无关联）。
    原文选 hierarchical+SU，本模块**忠实报告迁移下实际哪个占优**，但供 m5 的 canonical 簇标签
    仍用原文选定的 hierarchical+SU（复现原文方法，R2 仅作对比/验证展）。

依赖退化（环境实测：scipy 可用、sklearn 不可用，见落地假设）：
  - hierarchical：scipy.cluster.hierarchy（rock solid，PRIMARY，保证跑通；连接法 ward，见常量注释）；
  - Silhouette / K-means / GMM / DBSCAN：sklearn 缺 → 全部用 numpy 自实现（K-means=Lloyd+k-means++，
    GMM=全协方差 EM on MDS 低维嵌入，DBSCAN=precomputed 距离邻域扩张、eps 分位网格 silhouette 择优）；
    某配置数值失败或分不出 ≥2 簇时该行记 limited（不中断全表）。

未来函数红线（code_audit/codex 逐点核查）：
  SU/相关/nc/模型选择/代表组合评估**全部只用 [train_start, train_end] 训练期数据**，测试期不进入。
  候选集来自 m2（训练期一次性估、固定候选集，AS42），本模块不引入测试期泄漏。

数据对接（m1 prepare_all + m2 run_selection，接口以现状为准，不改上游）：
  prep.markets[m].stock_returns（月末×股票 月收益）/ prep.train_start / prep.train_end ；
  selection[m].candidates（候选股票 list[str]）/ selection[m].regime_tier。

只许冒烟运行：uv run python -m src.ssrn_6115073.clustering
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Optional

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform

from common.utils import calculate_max_drawdown, calculate_sharpe

# ---------------------------------------------------------------------------
# m3 聚类参数（集中常量，杜绝魔法数字，均可反查 spec/assumptions；严守文件所有权，
# 不写入 m1 建的 config.py，参数集中于本模块顶部，与 m2 selection.py 同构）
# ---------------------------------------------------------------------------

# --- SU/MI 熵估计（F3 / AS20：分箱离散化，分箱数用 sqrt(N)，落在 [MIN,MAX]）---
ENTROPY_BINS_RULE: Final[str] = "sqrt"     # AS20：sqrt(N)（另一备选为固定 10 箱，见 AS20）
ENTROPY_BINS_MIN: Final[int] = 3
ENTROPY_BINS_MAX: Final[int] = 12          # 训练期约 144 月 → sqrt≈12，取此上界
MIN_PAIR_OVERLAP: Final[int] = 24          # SU/相关 pairwise 最小重叠月（与 m2 MIN_REGIME_OBS 量级一致）

# --- 簇数搜索（F4 / AS2：Silhouette 在 2..10 自动定 nc）---
NC_MIN: Final[int] = 2
NC_MAX: Final[int] = 10                     # 表7 nc±2 敏感性佐证无固定绝对值（AS2）

# --- 层次聚类（凝聚）：连接法 spec 未指定 → 取 ward（sklearn AgglomerativeClustering 默认；
#     弱结构下产平衡簇，避免 average-linkage 把离群点逐个剥成单点簇的退化，登记 coder 假设）---
HIERARCHICAL_LINKAGE: Final[str] = "ward"

# --- K-means / GMM 的 MDS 低维嵌入（把 SU/相关距离阵嵌到欧氏空间，避免高维 GMM 协方差奇异）---
MDS_DIM: Final[int] = 5
KMEANS_N_INIT: Final[int] = 5
KMEANS_MAX_ITER: Final[int] = 100
GMM_MAX_ITER: Final[int] = 100
GMM_REG_COVAR: Final[float] = 1e-6         # 协方差对角正则，防奇异

# --- DBSCAN（precomputed 距离；eps 从距离低分位网格按 silhouette 选、min_samples=2）---
DBSCAN_MIN_SAMPLES: Final[int] = 2
# eps 候选=非对角距离的低分位网格（弱结构下距离几乎等长，仅极紧邻能成簇 → 网格取低端，
# 由 silhouette 在能分出 ≥2 簇的档中择优；全网格都分不出 ≥2 簇则该配置记 limited）
DBSCAN_EPS_PCTL_GRID: Final[tuple[float, ...]] = (2.0, 4.0, 6.0, 8.0, 10.0, 15.0)

# --- 迷你评估（R2 / spec B7）---
PERIODS_PER_YEAR: Final[int] = 12          # 月频（AS4）
VAR_QUANTILE: Final[float] = 0.05          # 历史模拟 VaR 最低 5%（spec B7）
MINI_EVAL_RF: Final[float] = 0.0           # R2 迷你评估 SR 的 rf=0（各配置统一、保序，非最终回测口径）
MIN_CANDIDATES: Final[int] = 4             # 候选 < 此值聚类无意义 → 该市场 degraded

RANDOM_SEED: Final[int] = 42               # 可复现随机种子（与 config.RANDOM_SEED 一致）

# --- 供 m5 的 canonical（原文选定）模型（spec F4：hierarchical+SU）---
FINAL_MODEL: Final[str] = "hierarchical"
FINAL_MEASURE: Final[str] = "su"

CLUSTER_MODELS: Final[tuple[str, ...]] = ("hierarchical", "kmeans", "gmm", "dbscan")
RELATION_MEASURES: Final[tuple[str, ...]] = ("su", "correlation")


# ---------------------------------------------------------------------------
# 返回结构（供 m5 每簇选一直接对接）
# ---------------------------------------------------------------------------

@dataclass
class MarketClustering:
    """单市场聚类产出（供 m5「每簇选一」与 R2 对比表）。"""
    market: str                          # 内部市场名（hs300/sz50/zz500）
    index_code: str                      # 指数代码
    regime_tier: str                     # 透传 m2：Tier1 / Tier2_degraded / excluded_narrow_pool
    n_candidates: int                    # 参与聚类的候选股票数
    status: str                          # 'ok' | 'degraded_small_pool' | 'excluded'
    # --- canonical（hierarchical+SU）：供 m5 每簇选一 ---
    final_model: str                     # 'hierarchical'
    final_measure: str                   # 'su'
    nc: int                              # canonical 簇数（Silhouette 定）
    silhouette: float                    # canonical 轮廓系数
    cluster_labels: dict[str, int]       # {股票 → 簇 id}（canonical，供 m5 分组）
    representatives: dict[int, str]      # {簇 id → medoid 股票}（canonical，离中心最近资产）
    # --- 关系矩阵与对比表 ---
    su_matrix: pd.DataFrame              # 候选×候选 对称不确定性（训练期）
    corr_matrix: pd.DataFrame            # 候选×候选 Pearson 相关（训练期）
    comparison: pd.DataFrame             # R2 表：8 行 model×measure，列 nc/silhouette/SR/MDD/VaR/frobenius/status
    notes: str = ""


# ---------------------------------------------------------------------------
# F3：MI / SU（分箱离散化估熵，AS20）
# ---------------------------------------------------------------------------

def _n_bins(n: int) -> int:
    """AS20 分箱数：sqrt(N) 落在 [MIN, MAX]。"""
    if ENTROPY_BINS_RULE == "sqrt":
        return int(np.clip(round(np.sqrt(max(n, 1))), ENTROPY_BINS_MIN, ENTROPY_BINS_MAX))
    return ENTROPY_BINS_MAX


def _entropy_from_counts(counts: np.ndarray) -> float:
    """离散分布香农熵 H=−Σ p·ln p（自然对数；SU 为比值故底数无关）。"""
    total = counts.sum()
    if total <= 0:
        return 0.0
    p = counts[counts > 0] / total
    return float(-(p * np.log(p)).sum())


def _su_pair(x: np.ndarray, y: np.ndarray) -> float:
    """一对资产的对称不确定性 SU（F3 式9/14；分箱估 MI，AS20）。

    x, y 为已对齐、无 NaN 的两资产收益序列（等长）。等宽分箱离散化后由频率估
    H[X]/H[Y]/H[X,Y]，MI=H[X]+H[Y]−H[X,Y]，SU=2·MI/(H[X]+H[Y])，裁剪到 [0,1]。
    退化（denom≤0，如某序列近常数）时 SU=0（信息无关）。
    """
    n = x.size
    if n < MIN_PAIR_OVERLAP:
        return 0.0
    nb = _n_bins(n)
    joint, _, _ = np.histogram2d(x, y, bins=nb)
    hx = _entropy_from_counts(joint.sum(axis=1))
    hy = _entropy_from_counts(joint.sum(axis=0))
    hxy = _entropy_from_counts(joint.ravel())
    denom = hx + hy
    if denom <= 0.0:
        return 0.0
    mi = hx + hy - hxy
    su = 2.0 * mi / denom
    return float(np.clip(su, 0.0, 1.0))


def pairwise_su(returns: pd.DataFrame) -> pd.DataFrame:
    """候选资产两两 SU 矩阵（F3；对称、对角=1；仅用输入的训练期收益）。

    Args:
        returns: [训练月末 × 候选股票] 月收益（可含 NaN，按 pairwise 重叠估计）。

    Returns:
        DataFrame（候选×候选），SU∈[0,1]，对角=1，index/columns=候选代码。
    """
    cols = list(returns.columns)
    n = len(cols)
    arr = returns.to_numpy()
    su = np.eye(n)
    for i in range(n):
        xi = arr[:, i]
        for j in range(i + 1, n):
            xj = arr[:, j]
            m = ~(np.isnan(xi) | np.isnan(xj))
            val = _su_pair(xi[m], xj[m]) if m.sum() >= MIN_PAIR_OVERLAP else 0.0
            su[i, j] = su[j, i] = val
    return pd.DataFrame(su, index=cols, columns=cols)


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """候选资产 Pearson 相关矩阵（pairwise complete；对角=1，NaN 相关补 0）。"""
    corr = returns.corr(min_periods=MIN_PAIR_OVERLAP).fillna(0.0)
    arr = corr.to_numpy(copy=True)
    np.fill_diagonal(arr, 1.0)
    return pd.DataFrame(arr, index=corr.index, columns=corr.columns)


# ---------------------------------------------------------------------------
# 关系度量 → 距离矩阵
# ---------------------------------------------------------------------------

def relation_to_distance(rel: pd.DataFrame, measure: str) -> np.ndarray:
    """关系矩阵 → 距离阵（对称、对角 0、非负）。

    - su          ：d = 1 − SU（SU∈[0,1] → d∈[0,1]，任务指定）。
    - correlation ：d = sqrt(0.5·(1−corr))（Mantegna 相关距离，corr=1→0/0→0.707/−1→1，
                    proper metric；spec 未定相关→距离形式，此为标准选择，登记 coder 假设）。
    """
    R = rel.to_numpy()
    if measure == "su":
        D = 1.0 - R
    elif measure == "correlation":
        D = np.sqrt(np.clip(0.5 * (1.0 - R), 0.0, None))
    else:
        raise ValueError(f"unknown measure: {measure!r}")
    D = (D + D.T) / 2.0
    np.fill_diagonal(D, 0.0)
    return np.clip(D, 0.0, None)


# ---------------------------------------------------------------------------
# Silhouette（自实现，precomputed 距离；sklearn 不可用，AS2）
# ---------------------------------------------------------------------------

def silhouette_precomputed(D: np.ndarray, labels: np.ndarray) -> float:
    """轮廓系数（precomputed 距离阵）。噪声点（label<0）排除；需 ≥2 有效簇。

    对每点 a(i)=同簇平均距离、b(i)=最近异簇平均距离，s(i)=(b−a)/max(a,b)；单点簇 s=0。
    返回全体（非噪声点）s 均值；不足 2 簇/2 点时 NaN。
    """
    labels = np.asarray(labels)
    keep = np.where(labels >= 0)[0]
    if keep.size < 2:
        return float("nan")
    lab = labels[keep]
    uniq = np.unique(lab)
    if uniq.size < 2:
        return float("nan")
    Ds = D[np.ix_(keep, keep)]
    sil = np.zeros(keep.size)
    for i in range(keep.size):
        same = lab == lab[i]
        n_same = int(same.sum()) - 1
        if n_same <= 0:
            sil[i] = 0.0
            continue
        a = Ds[i, same].sum() / n_same          # 排除自身（对角 0，不影响和）
        b = np.inf
        for c in uniq:
            if c == lab[i]:
                continue
            other = lab == c
            b = min(b, Ds[i, other].mean())
        denom = max(a, b)
        sil[i] = (b - a) / denom if denom > 0 else 0.0
    return float(sil.mean())


# ---------------------------------------------------------------------------
# 四聚类模型（hierarchical=scipy；kmeans/gmm/dbscan=numpy 自实现）
# ---------------------------------------------------------------------------

def _hierarchical(D: np.ndarray, nc: int) -> np.ndarray:
    """凝聚层次聚类（scipy，ward 连接，HIERARCHICAL_LINKAGE），切成 nc 簇；返回 0 基 labels。"""
    condensed = squareform(D, checks=False)
    Z = linkage(condensed, method=HIERARCHICAL_LINKAGE)
    return fcluster(Z, t=nc, criterion="maxclust").astype(int) - 1


def _classical_mds(D: np.ndarray, dim: int) -> np.ndarray:
    """经典 MDS：距离阵 → 低维欧氏坐标（供 kmeans/gmm）。"""
    n = D.shape[0]
    D2 = D ** 2
    J = np.eye(n) - np.ones((n, n)) / n
    B = -0.5 * J @ D2 @ J
    B = (B + B.T) / 2.0
    vals, vecs = np.linalg.eigh(B)
    order = np.argsort(vals)[::-1]
    vals, vecs = vals[order], vecs[:, order]
    k = max(1, min(dim, int((vals > 1e-9).sum()), n - 1))
    L = np.sqrt(np.clip(vals[:k], 0.0, None))
    return vecs[:, :k] * L


def _kpp_init(X: np.ndarray, k: int, rng: np.random.Generator) -> np.ndarray:
    """k-means++ 初始中心。"""
    n = X.shape[0]
    centers = [X[rng.integers(n)]]
    for _ in range(1, k):
        d2 = np.min(np.stack([((X - c) ** 2).sum(axis=1) for c in centers]), axis=0)
        s = d2.sum()
        probs = d2 / s if s > 0 else np.ones(n) / n
        centers.append(X[rng.choice(n, p=probs)])
    return np.stack(centers)


def _kmeans(X: np.ndarray, k: int, seed: int = RANDOM_SEED) -> np.ndarray:
    """K-means（Lloyd + k-means++，n_init 取最优；numpy 自实现，sklearn 不可用）。"""
    rng = np.random.default_rng(seed)
    n = X.shape[0]
    best_labels, best_inertia = None, np.inf
    for _ in range(KMEANS_N_INIT):
        centers = _kpp_init(X, k, rng)
        labels = np.zeros(n, dtype=int)
        for _ in range(KMEANS_MAX_ITER):
            d = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
            new_labels = d.argmin(axis=1)
            new_centers = np.stack([
                X[new_labels == c].mean(axis=0) if (new_labels == c).any() else centers[c]
                for c in range(k)
            ])
            if np.array_equal(new_labels, labels) and np.allclose(new_centers, centers):
                centers, labels = new_centers, new_labels
                break
            centers, labels = new_centers, new_labels
        d = ((X[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        inertia = float(d[np.arange(n), labels].sum())
        if inertia < best_inertia:
            best_inertia, best_labels = inertia, labels.copy()
    return best_labels


def _log_gaussian(X: np.ndarray, mean: np.ndarray, cov: np.ndarray, reg: float) -> np.ndarray:
    """多元高斯对数密度（数值稳健：slogdet + solve；奇异时加大正则）。"""
    d = X.shape[1]
    cov = cov + reg * np.eye(d)
    sign, logdet = np.linalg.slogdet(cov)
    if sign <= 0:
        cov = cov + (reg * 100 + 1e-4) * np.eye(d)
        sign, logdet = np.linalg.slogdet(cov)
    diff = X - mean
    sol = np.linalg.solve(cov, diff.T).T
    maha = np.einsum("ij,ij->i", diff, sol)
    return -0.5 * (d * np.log(2.0 * np.pi) + logdet + maha)


def _gmm(X: np.ndarray, k: int, seed: int = RANDOM_SEED) -> np.ndarray:
    """高斯混合（全协方差 EM，k-means 初始；numpy 自实现，sklearn 不可用）。

    在 MDS 低维空间上跑（维度小 → 全协方差非奇异）；数值失败由调用方 try/except 捕获记 limited。
    """
    n, d = X.shape
    labels0 = _kmeans(X, k, seed)
    rng = np.random.default_rng(seed)
    means = np.stack([
        X[labels0 == c].mean(axis=0) if (labels0 == c).any() else X[rng.integers(n)]
        for c in range(k)
    ])
    covs = np.stack([
        np.cov(X[labels0 == c].T) + GMM_REG_COVAR * np.eye(d)
        if (labels0 == c).sum() > 1 else np.eye(d)
        for c in range(k)
    ])
    weights = np.array([max((labels0 == c).mean(), 1e-3) for c in range(k)])
    weights /= weights.sum()
    prev_ll = -np.inf
    resp = np.full((n, k), 1.0 / k)
    for _ in range(GMM_MAX_ITER):
        logp = np.stack(
            [np.log(weights[c]) + _log_gaussian(X, means[c], covs[c], GMM_REG_COVAR) for c in range(k)],
            axis=1,
        )
        m = logp.max(axis=1, keepdims=True)
        logsum = m + np.log(np.exp(logp - m).sum(axis=1, keepdims=True))
        resp = np.exp(logp - logsum)
        ll = float(logsum.sum())
        Nk = resp.sum(axis=0) + 1e-8
        weights = Nk / Nk.sum()
        means = (resp.T @ X) / Nk[:, None]
        covs = np.stack([
            ((resp[:, c: c + 1] * (X - means[c])).T @ (X - means[c])) / Nk[c] + GMM_REG_COVAR * np.eye(d)
            for c in range(k)
        ])
        if abs(ll - prev_ll) < 1e-4 * (abs(prev_ll) if prev_ll != 0 else 1.0):
            break
        prev_ll = ll
    return resp.argmax(axis=1)


def _dbscan_offdiag(D: np.ndarray) -> np.ndarray:
    """非对角距离（用于 eps 分位网格）。"""
    n = D.shape[0]
    return D[~np.eye(n, dtype=bool)]


def _dbscan_precomputed(D: np.ndarray, eps: float, min_samples: int = DBSCAN_MIN_SAMPLES) -> np.ndarray:
    """DBSCAN（precomputed 距离；numpy 自实现）。噪声点 label=−1。"""
    n = D.shape[0]
    labels = np.full(n, -1, dtype=int)
    visited = np.zeros(n, dtype=bool)
    neighbors = [np.where(D[i] <= eps)[0].tolist() for i in range(n)]  # 含自身
    cluster = 0
    for i in range(n):
        if visited[i]:
            continue
        visited[i] = True
        if len(neighbors[i]) < min_samples:
            continue                                        # 暂记噪声
        labels[i] = cluster
        seeds = list(neighbors[i])
        s = 0
        while s < len(seeds):
            q = seeds[s]
            s += 1
            if not visited[q]:
                visited[q] = True
                if len(neighbors[q]) >= min_samples:
                    seeds.extend(x for x in neighbors[q] if x not in seeds)
            if labels[q] < 0:
                labels[q] = cluster
        cluster += 1
    return labels


# ---------------------------------------------------------------------------
# 每配置：定 nc（Silhouette）+ 聚类
# ---------------------------------------------------------------------------

def cluster_config(
    D: np.ndarray,
    model: str,
    measure: str,
    *,
    seed: int = RANDOM_SEED,
) -> tuple[np.ndarray, float, int]:
    """单（模型, 度量）配置聚类：nc-可调模型用 Silhouette 在 2..nc_max 选 nc；dbscan nc 涌现。

    Returns:
        (labels 0基/噪声−1, silhouette, nc 有效簇数)。GMM 数值失败抛异常，调用方记 limited。
    """
    n = D.shape[0]
    nc_max = min(NC_MAX, n - 1)

    if model == "dbscan":
        off = _dbscan_offdiag(D)
        best_db: Optional[tuple[np.ndarray, float, int]] = None
        for p in DBSCAN_EPS_PCTL_GRID:                     # eps 网格，silhouette 择优（同 nc 选法精神）
            eps = float(np.percentile(off, p)) if off.size else 0.0
            labels = _dbscan_precomputed(D, eps)
            n_eff = int(np.unique(labels[labels >= 0]).size)
            if n_eff < 2:
                continue
            sil = silhouette_precomputed(D, labels)
            if best_db is None or (not np.isnan(sil) and (np.isnan(best_db[1]) or sil > best_db[1])):
                best_db = (labels, sil, n_eff)
        if best_db is not None:
            return best_db
        eps = float(np.percentile(off, DBSCAN_EPS_PCTL_GRID[-1])) if off.size else 0.0
        labels = _dbscan_precomputed(D, eps)               # 无档能分 ≥2 簇 → 单簇，下游记 limited
        return labels, float("nan"), int(np.unique(labels[labels >= 0]).size)

    X = _classical_mds(D, MDS_DIM) if model in ("kmeans", "gmm") else None
    best: Optional[tuple[np.ndarray, float, int]] = None
    for nc in range(NC_MIN, nc_max + 1):
        if model == "hierarchical":
            labels = _hierarchical(D, nc)
        elif model == "kmeans":
            labels = _kmeans(X, nc, seed)
        elif model == "gmm":
            labels = _gmm(X, nc, seed)
        else:
            raise ValueError(f"unknown model: {model!r}")
        sil = silhouette_precomputed(D, labels)
        n_eff = int(np.unique(labels[labels >= 0]).size)
        if n_eff < 2:
            continue
        if best is None or (not np.isnan(sil) and (np.isnan(best[1]) or sil > best[1])):
            best = (labels, sil, n_eff)
    if best is None:                                       # 全 nc 退化 → 兜底单一切分
        labels = _hierarchical(D, 2) if model == "hierarchical" else (
            _kmeans(X, 2, seed) if model == "kmeans" else _gmm(X, 2, seed))
        return labels, silhouette_precomputed(D, labels), int(np.unique(labels[labels >= 0]).size)
    return best


# ---------------------------------------------------------------------------
# 代表资产（medoid）+ R2 迷你评估（SR/MDD/VaR/Frobenius）
# ---------------------------------------------------------------------------

def cluster_medoids(D: np.ndarray, labels: np.ndarray) -> dict[int, int]:
    """每簇 medoid（离中心最近资产 = 簇内平均距离最小者，spec F4）。噪声簇跳过。

    Returns: {簇 id → 候选列索引}。
    """
    labels = np.asarray(labels)
    reps: dict[int, int] = {}
    for c in np.unique(labels):
        if c < 0:
            continue
        members = np.where(labels == c)[0]
        if members.size == 1:
            reps[int(c)] = int(members[0])
            continue
        sub = D[np.ix_(members, members)]
        reps[int(c)] = int(members[sub.mean(axis=1).argmin()])
    return reps


def _historical_var(returns: pd.Series, q: float = VAR_QUANTILE) -> float:
    """历史模拟 VaR（最低 q 分位收益的损失幅度，正数；spec B7）。"""
    r = returns.dropna().to_numpy()
    if r.size == 0:
        return float("nan")
    return float(-np.quantile(r, q))


def _frobenius_diversification(rep_returns: pd.DataFrame) -> float:
    """分散化指数=‖CM−IM‖_F（IM=单位阵=资产无关联的理想；越小越分散，spec B7/附录C）。"""
    r = rep_returns.dropna(how="all")
    if r.shape[1] < 2:
        return float("nan")
    cm = r.corr(min_periods=MIN_PAIR_OVERLAP).to_numpy()
    cm = np.nan_to_num(cm, nan=0.0)
    np.fill_diagonal(cm, 1.0)
    return float(np.linalg.norm(cm - np.eye(cm.shape[0]), ord="fro"))


def evaluate_representatives(returns_train: pd.DataFrame, D: np.ndarray, labels: np.ndarray) -> dict:
    """R2 迷你评估：每簇 medoid → 等权组合（训练期）→ SR/MDD/VaR/Frobenius。

    SR/MDD 复用 common.utils（import）；VaR=历史模拟最低5%（spec B7）；Frobenius 见上。
    """
    reps = cluster_medoids(D, labels)
    if len(reps) < 2:
        return dict(nc=len(reps), SR=np.nan, MDD=np.nan, VaR=np.nan, frobenius=np.nan, status="limited")
    rep_cols = [returns_train.columns[i] for i in reps.values()]
    rep_ret = returns_train[rep_cols]
    port = rep_ret.mean(axis=1, skipna=True).dropna()      # 等权组合月收益
    if port.shape[0] < 3:
        return dict(nc=len(reps), SR=np.nan, MDD=np.nan, VaR=np.nan, frobenius=np.nan, status="limited")
    nav = (1.0 + port).cumprod()
    return dict(
        nc=len(reps),
        SR=calculate_sharpe(port, rf=MINI_EVAL_RF, periods_per_year=PERIODS_PER_YEAR),
        MDD=calculate_max_drawdown(nav),
        VaR=_historical_var(port),
        frobenius=_frobenius_diversification(rep_ret),
        status="ok",
    )


# ---------------------------------------------------------------------------
# 单市场：8 配置对比表 + canonical（hierarchical+SU）簇标签
# ---------------------------------------------------------------------------

_COMPARISON_COLS: Final[list[str]] = ["model", "measure", "nc", "silhouette",
                                      "SR", "MDD", "VaR", "frobenius", "status"]


def run_market_clustering(
    name: str,
    index_code: str,
    regime_tier: str,
    returns_train: pd.DataFrame,
) -> MarketClustering:
    """单市场聚类：SU/相关矩阵 → 8 配置对比表（R2）+ canonical hierarchical+SU 簇标签（供 m5）。

    Args:
        returns_train: [训练月末 × 候选股票] 训练期月收益（只用训练期，防未来函数）。
    """
    candidates = list(returns_train.columns)
    n = len(candidates)

    # 退化/排除市场：不聚类，返回空标签（下游据 status/regime_tier 处理）
    if regime_tier == "excluded_narrow_pool" or n < MIN_CANDIDATES:
        status = "excluded" if regime_tier == "excluded_narrow_pool" else "degraded_small_pool"
        empty = pd.DataFrame(columns=candidates, index=candidates, dtype=float)
        return MarketClustering(
            market=name, index_code=index_code, regime_tier=regime_tier, n_candidates=n,
            status=status, final_model=FINAL_MODEL, final_measure=FINAL_MEASURE,
            nc=0, silhouette=float("nan"), cluster_labels={}, representatives={},
            su_matrix=empty, corr_matrix=empty,
            comparison=pd.DataFrame(columns=_COMPARISON_COLS),
            notes=f"候选数 {n} < {MIN_CANDIDATES} 或 tier=excluded，跳过聚类",
        )

    su_df = pairwise_su(returns_train)
    corr_df = correlation_matrix(returns_train)
    dist = {m: relation_to_distance(su_df if m == "su" else corr_df, m) for m in RELATION_MEASURES}

    rows: list[dict] = []
    canonical: dict[str, object] = {}
    for model in CLUSTER_MODELS:
        for measure in RELATION_MEASURES:
            D = dist[measure]
            try:
                labels, sil, nc = cluster_config(D, model, measure)
                metrics = evaluate_representatives(returns_train, D, labels)
                status = metrics["status"]
            except Exception as exc:                       # GMM 等数值失败 → limited（不中断全表）
                labels, sil, nc = np.full(n, -1), float("nan"), 0
                metrics = dict(nc=0, SR=np.nan, MDD=np.nan, VaR=np.nan, frobenius=np.nan)
                status = f"limited:{type(exc).__name__}"
            rows.append({
                "model": model, "measure": measure, "nc": nc, "silhouette": sil,
                "SR": metrics["SR"], "MDD": metrics["MDD"], "VaR": metrics["VaR"],
                "frobenius": metrics["frobenius"], "status": status,
            })
            if model == FINAL_MODEL and measure == FINAL_MEASURE:
                canonical = dict(labels=labels, sil=sil, nc=nc, D=D)

    comparison = pd.DataFrame(rows, columns=_COMPARISON_COLS)

    # canonical（原文选定 hierarchical+SU）：供 m5 的每簇选一
    c_labels = np.asarray(canonical["labels"])
    c_D = canonical["D"]
    cluster_labels = {candidates[i]: int(c_labels[i]) for i in range(n)}
    reps_idx = cluster_medoids(c_D, c_labels)
    representatives = {cid: candidates[col] for cid, col in reps_idx.items()}

    return MarketClustering(
        market=name, index_code=index_code, regime_tier=regime_tier, n_candidates=n,
        status="ok", final_model=FINAL_MODEL, final_measure=FINAL_MEASURE,
        nc=int(canonical["nc"]), silhouette=float(canonical["sil"]),
        cluster_labels=cluster_labels, representatives=representatives,
        su_matrix=su_df, corr_matrix=corr_df, comparison=comparison,
        notes=("Tier2_degraded 市场：候选过滤放宽一档（AS44），聚类结果可信度低于 Tier1"
               if regime_tier == "Tier2_degraded" else ""),
    )


def run_clustering(prep, selection: Optional[dict] = None) -> dict[str, MarketClustering]:
    """m3 主入口：三宽基各自 SU+层次聚类分组，返回 {市场名: MarketClustering}。

    Args:
        prep: m1 prepare_all() 产出的 PreparedData。
        selection: m2 run_selection(prep) 产出（None 时内部调用）。

    Returns:
        dict[市场名 → MarketClustering]；下游 m5 按市场取 .cluster_labels（每簇选一分组基）与
        .representatives；R2 对比表在 .comparison。
    """
    if selection is None:
        from src.ssrn_6115073.selection import run_selection
        selection = run_selection(prep)

    out: dict[str, MarketClustering] = {}
    for name, md in prep.markets.items():
        sel = selection[name]
        idx = md.stock_returns.index
        train_sel = (idx >= prep.train_start) & (idx <= prep.train_end)
        cands = [c for c in sel.candidates if c in md.stock_returns.columns]
        returns_train = md.stock_returns.loc[train_sel, cands]
        out[name] = run_market_clustering(name, md.code, sel.regime_tier, returns_train)
    return out


# ---------------------------------------------------------------------------
# 冒烟运行（仅确认可执行 + 打印 nc/簇大小/对比表；验证结论归 verifier）
# ---------------------------------------------------------------------------

def _cluster_sizes(labels: dict[str, int]) -> dict[int, int]:
    s = pd.Series(list(labels.values()))
    return {int(k): int(v) for k, v in s.value_counts().sort_index().items()}


def _dominance(comparison: pd.DataFrame) -> dict[str, str]:
    """R2 对比表各指标占优配置（SR 高优 / MDD·VaR·Frobenius 低优）。"""
    ok = comparison[comparison["status"] == "ok"].copy()
    if ok.empty:
        return {}
    tag = ok["model"] + "+" + ok["measure"]
    return {
        "SR(高)": tag[ok["SR"].idxmax()],
        "MDD(低)": tag[ok["MDD"].idxmin()],
        "VaR(低)": tag[ok["VaR"].idxmin()],
        "Frobenius(低=最分散)": tag[ok["frobenius"].idxmin()],
    }


def _smoke() -> None:
    from src.ssrn_6115073.data_prep import prepare_all
    from src.ssrn_6115073.selection import run_selection

    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 20)
    print("=" * 88)
    print("m3 资产聚类分组冒烟 · ssrn_6115073（SU + 层次聚类 + Silhouette；scipy 可用/sklearn 不可用）")
    print("=" * 88)

    prep = prepare_all()
    selection = run_selection(prep)
    print(f"\n[口径] SU 分箱={ENTROPY_BINS_RULE}(N)∈[{ENTROPY_BINS_MIN},{ENTROPY_BINS_MAX}] "
          f"最小重叠={MIN_PAIR_OVERLAP} | nc 搜索 [{NC_MIN},{NC_MAX}] Silhouette 定")
    print(f"[canonical 供 m5] {FINAL_MODEL}+{FINAL_MEASURE}（原文选定，spec F4）| MDS 维={MDS_DIM} 种子={RANDOM_SEED}")
    print(f"[训练期] {prep.train_start.date()}~{prep.train_end.date()}（测试期不进入聚类，防未来函数）")

    results = run_clustering(prep, selection)

    for name, r in results.items():
        print("\n" + "-" * 88)
        print(f"[{name} / {r.index_code}]  regime_tier={r.regime_tier}  status={r.status}  候选数={r.n_candidates}")
        if r.status != "ok":
            print(f"   {r.notes}")
            continue
        sizes = _cluster_sizes(r.cluster_labels)
        print(f"   canonical({r.final_model}+{r.final_measure})  nc={r.nc}  silhouette={r.silhouette:.4f}")
        print(f"   簇大小分布 {sizes}  代表(medoid)={list(r.representatives.values())}")
        print(f"   R2 聚类对比表（4 模型 × 2 度量；SR 高优 / MDD·VaR·Frobenius 低优）：")
        disp = r.comparison.copy()
        for col in ("silhouette", "SR", "MDD", "VaR", "frobenius"):
            disp[col] = disp[col].astype(float).round(4)
        print(disp.to_string(index=False))
        dom = _dominance(r.comparison)
        print("   各指标占优配置：" + " | ".join(f"{k}={v}" for k, v in dom.items()))
        hs = r.comparison[(r.comparison["model"] == "hierarchical") & (r.comparison["measure"] == "su")]
        hc = r.comparison[(r.comparison["model"] == "hierarchical") & (r.comparison["measure"] == "correlation")]
        if not hs.empty:
            best_sr = _dominance(r.comparison).get("SR(高)", "")
            print(f"   → hierarchical+SU 迁移下是否 SR 占优：{'是' if best_sr == 'hierarchical+su' else '否，占优=' + best_sr}"
                  f"（原文选 hierarchical+SU；hier+corr SR={float(hc['SR'].iloc[0]):.3f} vs hier+su SR={float(hs['SR'].iloc[0]):.3f}）")

    print("\n" + "-" * 88)
    print("[下游接口 m5] run_clustering(prep, selection) → dict[市场名 → MarketClustering]；"
          "每市场 .cluster_labels(股票→簇id) 供每簇选一、.representatives(簇id→medoid)、.comparison(R2 表)。")
    print("冒烟完成：SU+层次聚类可端到端构造（可执行性确认；聚类质量/占优结论由 verifier 判定）。")


if __name__ == "__main__":
    _smoke()

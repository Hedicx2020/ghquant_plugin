# r001 SIT · m3「SIT 模型」实现忠实性审计（impl_audit_m3）

- mode=code / milestone=m3 / 生成日期 2026-07-13（前轮因环境回显损坏未落盘，本轮补产）
- 审计对象：`src/r001_signature_transformer_allocation/{model.py, test_model.py, config.py(m3段)}`
- 对照基准：`spec/spec.md` F3/F4/F5/F6 原文 + Eq.4/8-16 + Theorem 2.2；`assumptions.md` AS2/AS6/AS7/AS14/AS23；`coverage_matrix.md` milestone=m3 四条 done 行
- 方法：只拿文件不拿 coder 汇报；F5 逐 einsum 索引独立展开核对 Eq.8-16，不采信自述结论

## 一、coverage_matrix m3 done 行清单与空壳核查

| 要素 | 类别 | 声明实现位置 | 源码核实 | 空壳核查 |
|---|---|---|---|---|
| F3 | core | model.py:SignatureEmbedding / SIT.embedding | model.py:45-74 真实 nn.Module，forward 有体 | 非空壳 |
| F4 | support | model.py:TemporalCausalAttention / SITBlock.forward(时间子层) | model.py:81-116 + 260-262 真实 | 非空壳 |
| F5 | core | model.py:SignatureAssetAttention(mlp_beta/mlp_q/gamma/logit_parts/attn_from_parts) | model.py:128-227 五方法齐备有体 | 非空壳 |
| F6 | core | model.py:AllocationHead / SIT.forward(last-slice) | model.py:278-300 + 376-377 真实 | 非空壳 |

空壳判定：四实现位置均为真实、非 pass/TODO 的类与方法，`logit_parts`/`attn_from_parts`/`forward` 均含完整张量运算，无一为占位。故本 milestone 无空壳、无需回退。

## 二、逐要素五维度核对（公式一致 / 参数一致 / 实现位置真实 / 代码反查 / 简化声明）

### F3 签名嵌入输入 token（Eq.4，三嵌入融合，core）
- 公式一致：spec Eq.4 `x=Wproj[e_sig⊕e_date⊕e_asset]`。model.py:69 `e_sig=sig_proj(asset_sig)`（签名线性投影）、70 `e_date=date_proj(calendar).unsqueeze(2).expand(...)`（日历嵌入切片共享、跨资产广播）、72 `e_asset=asset_emb(idx)...expand(...)`（可学习资产嵌入）、73 `cat([e_sig,e_date,e_asset],dim=-1)`（⊕）、74 `w_proj(fused)`（Wproj）。三源融合 + 拼接 + 线性投影三步逐一对应，吻合。
- 参数一致：d_sig=config.asset_signature_dim=7（config.py:132-140 派生 1+2+4，AS21 时间增广+level0）、calendar_dim=8（config.py:49，AS4）、d_model 来自 config.sit_d_model（model.py:319/324-329）。无硬编码。
- 实现位置真实：SignatureEmbedding 为完整 forward（含资产数一致性校验 line 67-68）。
- 代码反查：无与 F3 无关的私货；三 nn.Linear/Embedding 均映射 Eq.4 三源。
- 简化声明：各源先投影至 d_model 再拼接（3·d_model→d_model）属 AS23(1) 登记（原文未指定子维，取对称最简）；无独立位置编码属 AS23(3) 登记（位置信息由 e_date + 时间增广签名提供）。声明合理。

### F4 时间维因果自注意力（support）
- 公式一致：spec「standard causal self-attention along temporal dimension」。model.py:107 `logits=matmul(q,k^T)/d_k**0.5`；109-111 `causal=triu(ones(L,L),diagonal=1)`（严格上三角=未来位）；112 `masked_fill(causal,-inf)` → softmax 后未来位权重为 0。因果掩码真实掩未来切片，吻合。
- 参数一致：n_heads=config.sit_n_heads=4（AS14 缩减）、d_k=d_model//n_heads，整除校验（model.py:91-92）。
- 实现位置真实：TemporalCausalAttention.forward 完整；SITBlock.forward:260-262 将资产维 reshape 为 batch（`x.permute(0,2,1,3).reshape(b*d,h,m)`）后沿 H 做时间注意力，忠于「asset-wise attention treats time as batch」。
- 代码反查：无私货。
- 简化声明：注意力权重 dropout（line 113）为标准 Transformer 组件，B1 dropout=0.1；无越界。
- 因果验证充分性：test_model.py:113-130（扰动 t>5 未来位→历史位输出逐元素不变 atol1e-6，且未来位确实改变=反平凡）、133-149（全编码器扰动未来 asset_sig 切片→历史切片表征不变 + 未来变）。两测均含「扰动确实生效」反向断言，非平凡通过，真实验证 F4 因果。

### F5 签名增强资产维自注意力（核心创新，逐式独立核）
- 公式一致（逐式展开核对，全部精确吻合）：
  - `Logits=QK^T/√d_k+γ·B`：model.py:196 `qk=einsum("bsjnf,bslnf->bsnjl",q,k)/(d_k**0.5)`（qk[b,s,n,j,l]=Σ_f Q_j·K_l，缩放 √d_k）；208 `attn_from_parts` 返回 `softmax(qk+gamma*bias,dim=-1)`（over key l）。精确对 Eq.11。
  - `b=⟨q_dyn,β⟩`（Eq.10）：model.py:200 `bias=einsum("bsjne,bjlne->bsnjl",q_dyn,beta)`——沿 e=d_β 逐头 n 做内积，共享 query 资产 j，β 另带 key 资产 l。逐位展开 bias[k,h,j,l]=Σ_e q_dyn[k,j,h,e]·β[j,l,h,e]=⟨(q_dyn_{k,j})_h,(β_{j,l})_h⟩，与 Eq.10 逐符号一致。
  - `β=MLP_β(交叉签名)`（Eq.8）：model.py:199 `beta=mlp_beta(cross).view(b,d,d,nh,db)`，输入即 cross_sig（B,d,d,d_cross）→ R^{N_H×d_β}逐头分离。B 确由交叉签名驱动——bias 非自由可学习参数矩阵，而是 ⟨q_dyn, MLPβ(cross_signature)⟩，签名诱导性真实（非「假偏置」捷径）。
  - `q_dyn=MLP_q(x')`（Eq.9）：model.py:198 `q_dyn=mlp_q(x).view(b,h,d,nh,db)`，x 为 SITBlock 内时间注意力之后的 token x'（SITBlock.forward:262 先时间子层→267 才调 asset_attn），忠于 Eq.9「x'_{k,j}」。
  - `γ=softplus(γ̂)>0`（p4）：model.py:159 `gamma_hat=nn.Parameter(torch.zeros(()))` 可学习标量；175 `return F.softplus(self.gamma_hat)`，softplus 恒正。γ 为逐层单一标量、广播乘全 bias（line 208），对 Eq「learnable strictly positive scalar gate」。
  - `WO+残差+LayerNorm`（Eq.15-16）：model.py:222 `einsum("bsnjl,bslnf->bsjnf",attn,v).reshape(b,h,d,-1)`（逐头加权求和 Σ_l α·V 后拼头→d_model）→ 223 `w_o(out)`（Eq.15 WO）；残差/LN 在外层 SITBlock:268 `ln_asset(x+drop(xa))`（post-LN，Eq.16）。
- 参数一致：d_β=config.sit_d_beta=4（AS7/AS23(6) 原文未明取小值）、hidden_c=config.sit_hidden_c=16（AS7）、n_heads=4、d_model=32。MLP 结构 `_mlp2`=Linear→GELU→Linear（line 123-125）对 AS7「2 层 MLP+GELU」。均映射 config/AS。
- 实现位置真实：logit_parts/attn_from_parts/forward 三方法完整；gamma property 完整。
- 代码反查：见 Finding CA-A01（mlp_beta 输入维取自模块级 DEFAULT_CONFIG 而非线程化 config，minor）。除此无未登记私货；无魔法数字（√d_k 为数学缩放、γ̂ 初值 0 见 AS23(5)）。
- 简化声明：MLP 结构/d_β/hidden 属 AS7 + AS23(5)(6) 登记；β 全窗口共享（不随切片变、仅 q_dyn 引切片依赖）是 Eq.8「c_{i,j,l} 无切片下标」的必然，非简化。声明合理。
- Theorem 2.2 测试有效性：test_model.py:156-184 固定 qk/bias、γ 由 0→5 线性扫描，断言每 query 对其 max-bias key l* 的注意力份额相邻差分≥−1e-6（单调不降）且整体严格上升（shares[-1]−shares[0]>0）。用真实 logit_parts 输出（非人造），验证 softmax dp/dγ=p·(B−E[B])>0，为 Theorem 2.2 的真实数值方向验证，非空测。

### F6 输出头 + softmax 分配层（core）
- 公式一致：spec F6 `w=softmax(µ̂/τ)∈R^d, long-only+fully-invested`；`µ̂^{1:K}∈R^{K×d}`。model.py:289 `proj=Linear(d_model,n_steps_k)`；298 `mu=proj(last_slice).transpose(1,2)`→(B,K,d)=µ̂^{1:K}；299 `w=softmax(mu/temp,dim=-1)`（dim=-1=资产维 d）→ 非负 + 逐步资产和=1。吻合。
- 参数一致：K=config.decision_steps_k=12（AS2）；τ=config.sit_tau=1.0 默认、可覆盖，τ≤0 抛错（line 296-297）。
- 实现位置真实：AllocationHead.forward 完整；SIT.forward:376 `last_slice=repr_seq[:,-1,:,:]` 取末切片。
- 代码反查：无私货。
- 简化声明：last-slice（非 pooling）属 AS6 登记（spec 原文「optionally ... using the last slice」为二选一，取 last-slice）；Linear(d_model→K) 属 AS23(4)。声明合理。
- 单纯形有效性测试：test_model.py:57-70 断言 shape==(B,12,d)、`all(w>=0)`、逐步和 allclose(1,atol1e-5)；真实验证 long-only + fully-invested。line 73-85 另验 τ↑→HHI↓（温度语义）。

## 三、专项核查

- 向后兼容（m5 消融开关注入 m3 文件 model.py）：`ablation_disable_bias=False`(160)、`ablation_gamma_fixed=None`(162)、`ablation_disable_asset_attn=False`(252) 默认值均不改现行为——gamma property(171-175) 默认走 softplus、forward(216-219) 默认走 attn_from_parts(含 γ·B)、SITBlock(264-268) 默认执行 F5 子层；`SIT.set_ablation`(382-397) 不调用即等价 full。默认路径与 m3 纯净前向逐分支一致，向后兼容成立。开关以 `# ---- SA1 ... (m5) ----` 明确分区（160/251/382），且 coverage_matrix SA1(m5) 行显式登记该实现位置，跨 milestone 共有 model.py 属声明范围内，非私自越界。
- 文件所有权：model.py=m3(F3-F6)+m5(SA1 开关，已登记)；test_model.py=m3 单测；config.py 为单一参数源、m1-m5 字段各带 milestone 出处注释（「本 milestone 追加，只增不改」），m3 段(83-91) 分区清晰。无所有权违规。
- AS23/AS7 简化合理性：AS23 六项（嵌入子维/factorized+post-LN/无位置编码/输出头 Linear/γ̂初值/d_β=4）逐项与 model.py 结构对应，均属 spec/Table4 未钉死的实现自由度，取 Transformer 通行最简忠实实现且可由 config 调，合理。AS7（MLP 2层+GELU、d_cross=2、d_β 小值）与 `_mlp2`/config 一致，合理。

## 四、Findings

- **CA-A01 · minor · model.py:157**（代码反查/config 线程化）：`self.mlp_beta = _mlp2(DEFAULT_CONFIG.cross_signature_dim, hidden_c, n_heads*d_beta)` 取模块级 `DEFAULT_CONFIG.cross_signature_dim`，而 `SignatureAssetAttention.__init__`(141-143) 未把 cross_signature_dim 作构造参数线程化（其余 d_model/n_heads/d_beta/hidden_c 均来自入参）。依据：违背 config.py「单一参数源」原则，属潜在耦合脆性——若 m4 用非默认 SITConfig（cross_signature_dim≠2）构造 SIT，mlp_beta 输入维仍按 DEFAULT_CONFIG=2 建，forward 收到 config 维的 cross 张量将触发 shape 报错。当日功能正确（cross_signature_dim=2 为 M=2 数据派生常量、不在 B2 网格、AS7 固定，从不改动），故仅 minor；建议将 cross_signature_dim 经 config 线程化入构造。不影响 F5 公式忠实性与 m3 结论。

## 五、已检查维度清单（五维度 × 4 要素 + 专项，无遗漏）

- 公式一致：F3(Eq.4)✓ / F4(causal)✓ / F5(Eq.8-16 逐式独立展开)✓ / F6(softmax 单纯形)✓
- 参数一致：F3(d_sig=7/cal=8)✓ / F4(heads=4)✓ / F5(d_β=4/hidden=16)✓ / F6(K=12/τ=1.0)✓ —— 全映射 config/AS，无魔法数字
- 实现位置真实：四要素实现位置均真实非空壳（第一节表），无 pass/TODO 占位
- 代码反查：仅 CA-A01(minor)；无未登记私货、无魔法数字
- 简化声明：AS2(H/K)/AS6(last-slice,τ)/AS7(MLP,d_β)/AS14(缩减档)/AS23(结构六项) 全登记且合理，无 deviation_undeclared
- 专项：向后兼容(m5 开关默认不改现行为)✓ / 文件所有权✓ / Theorem 2.2 测试有效✓ / F4 因果与 F6 单纯形单测非平凡✓ / B 由交叉签名驱动(真签名诱导非假偏置)✓

verdict: pass_with_issues

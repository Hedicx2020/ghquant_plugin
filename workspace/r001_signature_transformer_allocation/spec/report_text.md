===== PAGE 1 =====

                                                              Signature-Informed Transformer for Asset Allocation


                                                                                      Yoontae Hwang 1 Stefan Zohren 2


                                         Modern deep learning for asset allocation typically sepa-                           (1) Lacks Financial                  (2) Objective
                                                                                                                                Inductive Bias                      Mismatch
                                         rates forecasting from optimization. We argue this creates a
                                                                                                                      TSLA
                                         fundamental mismatch where minimizing prediction errors                      NVDA                                       ±𝒏% Error
                                         fails to yield robust portfolios. We propose the Signature                   AAPL                                                            MSE
                                                                                                                       …                           Forecasting




arXiv:2510.03129v3 [cs.LG] 22 Jan 2026
                                         Informed Transformer to address this by unifying feature ex-                                                Models      (3) Error         Portfolio
                                         traction and decision making into a single policy. Our model                                                            Amplification
                                                                                                                                                                                  Optimization
                                         employs path signatures to encode complex path dependen-                                              Asset Allocation
                                         cies and introduces a specialized attention mechanism that
                                         targets geometric asset relationships. By directly minimiz-             Figure 1. A depiction of flawed strategies for asset allocation
                                         ing the Conditional Value at Risk we ensure the training
                                         objective aligns with financial goals. We prove that our atten-       the idiosyncratic structures of financial markets, such as the
                                         tion module rigorously amplifies signature derived signals.           intricate lead-lag relationships between assets. Without a
                                         Experiments across diverse equity universes show our ap-              model architecture that explicitly reflects market dynamics,
                                         proach significantly outperforms both traditional strategies          such models struggle to distinguish genuine signals from
                                         and advanced forecasting baselines. The code is available             noise. Second, and more critically, this pipeline creates an
                                         at: https://anonymous.4open.science/r/Signature-Informed-             objective mismatch that leads to error amplification. The
                                         Transformer-For-Asset-Allocation-DB88                                 forecaster is trained to minimize a statistical metric like the
                                                                                                               Mean Squared Error (MSE), i.e. the average squared differ-
                                         1. Introduction                                                       ence between estimated and actual values. This objective is
                                                                                                               agnostic to the downstream task of portfolio construction,
                                         A central challenge in modern quantitative finance is strate-         where even minuscule prediction errors can be magnified by
                                         gic asset allocation: the dynamic construction of portfolios          the optimizer into volatile and impractical portfolio weights.
                                         that are robust to the complex, non-linear behavior of fi-            Furthermore, an MSE objective implicitly incentivizes the
                                         nancial markets (Markowitz, 1952). While foundational                 model to favor assets that are easier to predict, potentially
                                         theories provided a basis for optimization, their assump-             not considering harder-to-predict assets with larger estima-
                                         tions of static correlations and normally distributed returns         tion errors and distorting the final allocation. We argue
                                         are often not adequate for navigating the non-stationary              that a robust solution requires moving beyond this fragile
                                         and path-dependent nature of today’s markets (Cont, 2001;             pipeline. The challenge is to develop a unified policy that
                                         Fama, 1970). Deep learning offers a powerful toolkit to ad-           learns an end-to-end mapping from market data directly
                                         dress these complexities, yet developing policies that yield          to portfolio weights while being architecturally designed
                                         stable, real-world performance remains a formidable task.             to model the known geometric properties of financial time
                                         The predominant deep learning paradigm for this problem,              series (Buehler et al., 2019; Hwang et al., 2025a).
                                         illustrated in Figure 1, is a decoupled, two-stage pipeline: a        To this end, we introduce the Signature-informed Trans-
                                         forecasting model first predicts asset returns, and these pre-        former (SIT), a deep learning framework designed to learn
                                         dictions are then fed into a downstream portfolio optimizer           robust, multi-asset allocation policies by directly addressing
                                         (Moody & Saffell, 2001). This approach has drawbacks and              these challenges. SIT’s contributions are unified within a
                                         suffers from two critical issues. First, the forecasting mod-         synergistic architecture built on three pillars:
                                         els typically employed are general-purpose architectures.
                                         They lack the financial inductive biases necessary to model             1. Path-wise Feature Representation: To better capture
                                                                                                                    the complex dynamics of assets, the model generates
                                              1
                                                Pusan National University, Busan, Republic of Korea                 features from each asset’s price history using Rough
                                         2
                                          University of Oxford, Oxford, United Kingdom. Correspondence
                                                                                                                    Path Signatures. This technique offers a principled
                                         to: Stefan Zohren <stefan.zohren@eng.ox.ac.uk>.
                                                                                                                    summary of a path’s shape, encoding its trends and os-
                                         Preprint. January 23, 2026.                                                cillations to provide a richer basis for decision-making
                                                                                                                    (Lyons, 1998; Lyons & McLeod, 2022).

                                                                                                           1

===== PAGE 2 =====

                                      Signature-Informed Transformer for Asset Allocation

  2. Signature-Augmented Attention: For modeling de-                   M , it becomes a finite-dimensional
                                                                                              Rt       RtRu      vector denoted as
     pendencies between assets, the model introduces a                 SigM (X[s,t] ) = (1, s dXu , s s dXr ⊗ dXu , . . .). In
     novel attention mechanism. It enhances attention                  our financial context, X corresponds to the price process
     scores with a term derived from the signature of as-              St . First-order signature terms capture net increments for
     set pairs, which represents a robust measure of their             each asset, while second-order terms encode signed areas,
     lead-lag relationships (Bonnier et al., 2019). This al-           revealing non-trivial correlations and lead-lag effects. For
     lows the model to allocate attention based on geometric           clarity, the key notations are provided in Appendix B.
     interactions, a crucial inductive bias for this problem.          Proposition 2.1 (Strict Lead-Lag Implies Positive Sec-
                                                                       ond-Order Signature (cf. (Chevyrev & Kormilitzin, 2016))).
  3. Decision Alignment: To align the training process
                                                                       Let Xt = (Xt1 , Xt2 ) for t ∈ [0, T ] satisfy a strict lead-lag
     with the goal, the model is optimized directly for the
                                                                       structure of Definition C.1. Then the second-level signature
     quality of the portfolio allocation. Instead of aim-
                                                                       cross-term
     ing for statistical forecasting accuracy, its parameters
                                                                                            Z T              Z T
     are trained to minimize the Conditional Value-at-Risk
     (CVaR) of the portfolio’s loss distribution, bridging the                    A(X) =         Xt1 dXt2 −       Xt2 dXt1          (1)
                                                                                               0                  0
     gap often found in two-stage pipelines.
                                                                       is strictly positive. In particular, A(X) > 0.
2. Methodology                                                         Proof. See Appendix C.2.
This section introduces the Signature-Informed Transformer
(SIT), a novel approach to risk-aware portfolio allocation             Problem Formulation. We frame the task as a se-
(Figure 2). All relevant literature can be found in the Ap-            quential decision-making problem under uncertainty. At
pendix A. After a brief overview of the problem and path               each decision point ti , the objective is to construct
signatures, we detail the model’s core components.                     portfolios of d assets for each of the next K periods
                                                                       [ti , ti+1 ], . . . , [ti+K−1 , ti+K ]. The information set avail-
2.1. Preliminaries                                                     able at time ti , denoted Fti , comprises three components:
Notations. Let 0 = t0 < t1 < · · · < tn = T denote                     (i) for each asset j, a sequence of truncated path sig-
a sequence of discrete times over the horizon [0, T ]. We              natures {SigM (S[tj i−H+k−1 ,ti−H+k ] )}H    k=1 over a lookback
consider d assets traded in a financial market, with price             window of H time steps (ii) pairwise cross-signatures
Stji (ω) referring to the value of asset j ∈ {1, . . . , d} at         SigM ((S j , S l )[ti−H ,ti ] ) for all asset pairs (j, l), captur-
time ti under a particular market scenario ω ∈ Ω. The                  ing lead-lag relationships over the entire window and
set Ω encapsulates all possible market paths. For con-                 (iii) a sequence of deterministic calendar feature vectors
venience, we define the continuous-time vector process                 {vti−H+k }H                            F
                                                                                       k=1 , where vt ∈ R . Our model, parameterized
Su (ω) = (Su1 (ω), . . . , Sud (ω)) ∈ Rd , understanding that          by θ ∈ Θ, learns a mapping
its values at discrete times {ti } coincide with the observed
data {Sti }. In practice, Su on each interval [ti , ti+1 ] can               gθ : Fti 7−→ µ̂1:K
                                                                                            ti (θ),          µ̂1:K
                                                                                                               ti (θ) ∈ R
                                                                                                                          K×d
                                                                                                                              ,       (2)
be reconstructed by an appropriate interpolation. A para-
                                                                       which yields k-step-ahead expected returns for k =
metric asset allocation strategy is denoted by θ ∈ Θ,
                                                                       1, . . . , K. Portfolio weights for step k are then obtained
where Θ is the set of all feasible parameter configura-                         (k)                  (k)
                                                                       via wti (θ) = softmax(µ̂ti (θ)/τ ) ∈ Rd , ensuring a long-
tions. At each decision time ti , the policy outputs a se-
                                                                       only, fully invested allocation at each future step. Note that
quence of long-only, fully invested portfolio weight vec-
                                     (k)                               µ̂1:K
                                                                         ti     is not trained with a prediction loss. It acts as the log-
tors for the next K periods, {wti (θ)}K               d
                                            k=1 ⊂ R+ , with
Pd        (k),j
                                                                       its of the allocation layer, and gradients flow only from the
    j=1 wti     (θ) = 1 for each k. We parameterize each               portfolio objective below. Let rti+k be the vector of realized
  (k)
wti via a softmax over the k-step-ahead predicted returns,             asset returns over [ti+k−1 , ti+k ], and define the correspond-
                                                                                               (k)              (k)
  (k)                   (k)
wti (θ) = softmax(µ̂ti (θ)/τ ), where µ̂1:K               K×d          ing portfolio loss Lti+k (θω ) = −(wti (θ))⊤ rti+k (ω). The
                                              ti (θ) ∈ R
stacks the predictions for k = 1, . . . , K. Our objective is to       parameters θ are optimized by minimizing the expected Con-
learn θ so as to maximize cumulative trading gains, subject            ditional Value-at-Risk (CVaR) of the K-step loss sequence
to uncertainty in market behavior.                                     within a scenario as
                                                                                                            (k)
A key ingredient in our framework is the use of path sig-                         min Eω∼D [CVaRα ({Lti+k (θω )}K
                                                                                                                k=1 )].               (3)
                                                                                  θ∈Θ
natures to capture high-order variations and cross-asset
interactions in price trajectories. For a continuous path              A core assumption of this framework is that the complex,
X : [s, t] → Rd , the signature Sig(X[s,t] ) lies in the               path-dependent market dynamics relevant for forecasting
tensor algebra ⊕∞        d ⊗k
                  k=0 (R )    . When truncated at level                returns are effectively encoded within the signature features.

                                                                   2

===== PAGE 3 =====

                                       Signature-Informed Transformer for Asset Allocation



                            Pairwise Cross-Signatures
                                   Extraction                        SIT Block
                                                                                                                  Query
                                                                 Temporal Attn
                                                                                                              +𝜸𝜷


                                                                                             Key, Value
                                           𝐒𝐢𝐠 𝑴 (𝑺)
                                                                   Signature-                                 +𝜸𝜷
                                         Signature               Informed Attn
               Price Data                Extraction                                                                       +𝜸𝜷
                                                                 Feed-Forward
                                                                   Network                                Financial Inductive Bias

                 𝒆𝐬𝐢𝐠         𝒆𝐝𝐚𝐭𝐞          𝒆𝐚𝐬𝐬𝐞𝐭
              Signature       Time           Asset                                                            min CVaR 𝛼 (Loss)
                                                               Portfolio Allocation
                          Fusion & Projection Block                   Head                                 Optimization Objective

                            Figure 2. Overview of the Signature-Informed Transformer (SIT) architecture.

2.2. Signature-Informed Transformer (SIT)                                vectors {x′k,1 , . . . , x′k,d }, where each x′k,j ∈ Rdmodel . The
                                                                         asset-wise attention treats the time dimension as a batch di-
Signature Embeddings. At a given decision time ti ,
                                                                         mension, processing H independent attention calculations.
the initial representation for each asset j and lookback
slice k ∈ {1, . . . , H} is constructed by fusing three dis-             The mechanism is built upon a standard multi-head self-
tinct information sources. First, the truncated path signa-              attention framework with NH heads. For a given time slice
ture of the asset’s price history over the slice’s interval,             k, the collection of asset vectors X′k = (x′k,1 , . . . , x′k,d )⊤ ∈
sk,j = SigM (S[tj i−H+k−1 ,ti−H+k ] ) ∈ Rdsig , is projected into        Rd×dmodel is linearly projected to generate queries, keys, and
the model’s hidden space Rdmodel using a linear layer to form            values:
a path embedding esig,k,j . Second, the vector of calendar
features for that slice, vti−H+k ∈ RF , is projected to create                             Qk = X′k WQ ∈ Rd×dmodel                       (5)
a time embedding edate,k ∈ Rdmodel , which is shared across                                Kk = X′k WK ∈ Rd×dmodel                       (6)
all assets for slice k. Third, to encode unique, time-invariant                            Vk = X′k WV ∈ Rd×dmodel                       (7)
characteristics, each asset j ∈ {1, . . . , d} is assigned a
learnable embedding vector ejasset ∈ Rdmodel . These three               where WQ , WK , WV ∈ Rdmodel ×dmodel are learnable weight
embeddings are concatenated and passed through a final                   matrices. These are then reshaped for multi-head computa-
linear projection to produce the input token xk,j for the first          tion, yielding per-head tensors Qk,h , Kk,h , Vk,h ∈ Rd×dk
Transformer layer:                                                       for each head h ∈ {1, . . . , NH }, where dk = dNmodel . The
                                                                                                                            H

      xk,j = Wproj [esig,k,j ⊕ edate,k ⊕ ejasset ] ∈ Rdmodel   (4)       innovation lies in the computation of an additive bias term.
                                                                         This bias is a function of both pairwise relational charac-
where ⊕ denotes concatenation. The resulting input tensor
                                                                         teristics and current asset states. The first component uses
for time ti , of shape H × d × dmodel , encapsulates path-
                                                                         the cross-signature feature over the entire lookback window
wise, temporal, and asset-specific information. Note that
                                                                         [ti−H , ti ]. For each pair of assets (j, l), we denote the vector
the signature update uses Chen relation (Lyons et al., 2007;
                                                                         representation of this feature as ci,j,l ∈ Rdcross-sig . These fea-
Moreno-Pino et al., 2024) and therefore avoids recomputa-
                                                                         tures, encoding relational information for the pair (j, l), are
tion over the full history.
                                                                         projected into a specialized embedding space using a dedi-
                                                                         cated MLP, denoted MLPβ , to produce a tensor of relational
Signature-Informed Self-Attention. The core of the
                                                                         embeddings, β i,j,l :
model’s cross-asset reasoning lies in a novel attention mech-
anism that operates along the asset dimension, following a
                                                                                       β i,j,l = MLPβ (ci,j,l ) ∈ RNH ×dβ                (8)
standard causal self-attention pass along the temporal dimen-
sion within each factorized layer. This Signature-Informed               Here, dβ is the bias embedding dimensionality, and a sep-
Self-Attention dynamically modifies the attention scores                 arate embedding is learned for each attention head. The
between pairs of assets based on their explicit relational               second component introduces dynamism. The query as-
features encoded by path signatures. Let the output of the               set’s representation from the temporal stage, x′k,j , is used to
temporal attention and its subsequent feed-forward network               generate a dynamic query vector via another MLP,
for a given layer be denoted by the tensor X′ ∈ RH×d×dmodel .
For each time slice k ∈ {1, . . . , H}, we have a set of d asset                        qdyn          ′
                                                                                         k,j = MLPq (xk,j ) ∈ R
                                                                                                                NH ×dβ
                                                                                                                                         (9)

                                                                     3

===== PAGE 4 =====

                                         Signature-Informed Transformer for Asset Allocation

This vector qdyn
              k,j represents the informational need of asset j                 with above-average alignment increases as γ grows, while
at slice k. The dynamic attention bias, bk,h,j,l , for each head               attention to below-average alignment decreases.
h, query asset j, and key asset l at time slice k, is computed
                                                                               Finally, the outputs from all heads are concatenated and
via an inner product as
                                                                               passed through a final linear projection WO , followed by a
                bk,h,j,l = ⟨(qdyn                                              residual connection and layer normalization:
                              k,j )h , (β i,j,l )h ⟩               (10)

where (·)h denotes the vector for head h. This forms a                                                 Qk,h K⊤
                                                                                  Headk,h = softmax(     √ k,h + γBk,h )Vk,h                (14)
complete bias matrix Bk ∈ RNH ×d×d for each time slice                                                     dk
k. This allows the model to selectively amplify or suppress                               Ok = Concat(Headk,1 , . . . , Headk,NH )WO        (15)
attention based on whether a signature-encoded relationship                               X′′k = LayerNorm(X′k + Dropout(Ok ))              (16)
is pertinent to the query asset’s current state.
This dynamic bias matrix is scaled by a learnable, strictly                    The resulting collection {X′′k }H
                                                                                                               k=1 is the output of the
positive scalar gate, γ > 0 (parameterized as γ =                              Signature-Informed Self-Attention block.
softplus(γ̂)), which controls the overall magnitude of the
signature-based influence. The final attention logits are:                     Training Strategy The model is trained end-to-end to
                                                                               optimize portfolio performance under a risk-aware objec-
                        Qk,h K⊤                                                tive. The final output tensor from the Transformer stack,
         Logitsk,h =      √ k,h + γBk,h ∈ Rd×d                     (11)        X′′ ∈ RH×d×dmodel , summarizes pathwise and cross-asset in-
                            dk
                                                                               formation over the lookback window. An output head maps
The attention weights, αk,h ∈ Rd×d , are obtained by ap-                       this representation at decision time ti to K-step-ahead re-
plying the softmax function row-wise. The output for each                      turn predictions: a linear projection (optionally preceded by
head is computed by multiplying the attention weights with                     pooling over the H slices or using the last slice) produces
the value matrix.                                                              µ̂1:K
                                                                                 ti   ∈ RK×d . For each forecast step k ∈ {1, . . . , K},
                                                                                                         (k)
Theorem 2.2 (Positive directional derivative of attention                      the predicted returns µ̂ti ∈ Rd are converted into long-
                                                                                                             (k)               (k)
weight). Assume d ≥ 2, γ > 0, and fix (k, h, j, l). Let the                    only portfolio weights via wti = softmax(µ̂ti /τ ), where
query vector (qdyn
               k,j )h ∈ R
                         dβ
                            satisfy ∥(qdyn
                                       k,j )h ∥2 > 0. For                      τ > 0 controls allocation concentration.
                                                                               Let rti+k denote the realized asset-return vector over
         (Qk,h K⊤     )j,m
  zj,m =      √ k,h        + γ⟨(qdyn
                                 k,j )h , (β i,j,m )h ⟩ (12)
                                                                                                                               (k)
                                                                               [ti+k−1 , ti+k ]. The step-k portfolio loss is Lti+k (θω ) =
                dk                                                                  (k)
           ezj,m                                                               −(wti (θ))⊤ rti+k (ω). The overall objective is formally
  αj,m = Pd           ,                                 (13)                   stated as
                 zj,r
           r=1 e
                                                                                            min Eω∼D [CVaRα ({L(k) (θω )}K
                                                                                                                         k=1 )],            (17)
assume 0 < αj,l < 1. Then the directional deriva-                                            θ
tive of αj,l with respect to β i,j,l in the direction (qdyn
                                                        k,j )h                 No auxiliary prediction losses are used. Eq. (17) is the sole
          (β)
equalsD            αj,l = γ αj,l (1 − αj,l ) ∥(qdyn     2
                                                k,j )h ∥2 > 0.                 training signal, avoiding the objective-mismatch issues dis-
          (qdyn
            k,j )h
                                                                               cussed in Section A. For each scenario ω, the inner CVaRα
Proof. See Appendix C.3.                                                       is taken over the intra-scenario empirical distribution. The
                                                                               following derivation shows the dual form and its empirical
Intuitively, when a relational signature is aligned with a                     counterpart used for optimization:
query asset’s current informational need, strengthening that                   L(θ) = Eω∼D [CVaRα ({L(k) (θω )}K
                                                                                                               k=1 )]                       (18)
signature should raise the model’s attention to the counter-
                                                                                                                       K
part. Formally, Theorem 2.2 shows that, for fixed γ > 0,                                                        1      X
                                                                                    = Eω∼D [ min (νω +                       (L(k) (θω ) − νω )+ )]
the directional derivative of αj,l with respect to (β i,j,l )h                                   νω ∈R      (1 − α)K
                                                                                                                       k=1
                                                       (β)
along (qdyn
        k,j )h is strictly positive, i.e., D                    αj,l   =                                                                    (19)
                                                       (qdyn
                                                         k,j )h

γ αj,l (1 − αj,l )∥(qdyn       2
                     k,j )h ∥2 > 0. By contrast, the effect of                            1
                                                                                             N
                                                                                             X                1
                                                                                                                       K
                                                                                                                       X
increasing the gate γ itself on αj,l depends on alignment rel-                      ≈           min (νi +                    (L(k) (θωi ) − νi )+ ).
                                                                                          N i=1 νi ∈R     (1 − α)K
                                                 d
                                                             !                                                         k=1
                       ∂αj,l                    X
                                                                                                                                            (20)
ative to other keys:            = αj,l bj,l −       αj,m bj,m ,
                        ∂γ                      m=1
where bj,m = ⟨(qdyn  k,j )h , (β i,j,m )h ⟩. Thus, γ > 0 scales                To incorporate risk aversion, we made the choice in Eq. (18)
the influence of signature alignment, i.e. attention to pairs                  to minimizing the expected CVaR of the intra-scenario loss

                                                                           4

===== PAGE 5 =====

                                          Signature-Informed Transformer for Asset Allocation

                       Panel A. Asset 40 Universe (S&P100)
                          Models        Sharpe Ratio (↑)   Sortino Ratio (↑)       Maximum Drawdown (↓)   Final Wealth Factor (↑)
                           CVaR              0.1531             0.2001                     0.3516                 1.0569
                            EW               0.5759             0.7153                     0.3688                 1.6439
                           GMV               0.4148             0.5337                     0.2743                 1.3258
                           HRP               0.4958             0.6171                     0.3185                 1.4561
                        Autoformer      0.2499 ± 0.1405    0.3423 ± 0.1980            0.3812 ± 0.0480        1.1809 ± 0.2403
                          DLinear       0.3167 ± 0.1326    0.4513 ± 0.2005            0.3621 ± 0.0407        1.2915 ± 0.2133
                        FEDformer       0.4006 ± 0.2317    0.5540 ± 0.3192            0.3647 ± 0.0167        1.5198 ± 0.5703
                       iTransformer     0.3157 ± 0.0749    0.4233 ± 0.0943            0.4136 ± 0.0326        1.2860 ± 0.0147
                         NSformer       0.4074 ± 0.1151    0.5820 ± 0.1655            0.4475 ± 0.0672        1.5129 ± 0.3010
                         PatchTST       0.3286 ± 0.2021    0.4540 ± 0.2818            0.4523 ± 0.0838        1.3409 ± 0.3886
                         TimesNet       0.3568 ± 0.0782    0.4959 ± 0.1019            0.4704 ± 0.0701        1.3765 ± 0.1729
                         RFormer        0.4901 ± 0.1437    0.6308 ± 0.1828            0.3415 ± 0.0482        1.5387 ± 0.2353
                        SIT (Ours)      0.6717 ± 0.0628    0.8232 ± 0.0792            0.3611 ± 0.0037        1.7903 ± 0.1023

                       Panel B. Asset 50 Universe (S&P100)
                          Models        Sharpe Ratio (↑)   Sortino Ratio (↑)       Maximum Drawdown (↓)   Final Wealth Factor (↑)
                           CVaR              0.2165             0.2858                     0.3086                 1.1170
                            EW               0.6008             0.7399                     0.3604                 1.6683
                           GMV               0.3947             0.4992                     0.2678                 1.2845
                           HRP               0.4637             0.5620                     0.3258                 1.4021
                        Autoformer      0.3899 ± 0.1985    0.5321 ± 0.2870            0.4356 ± 0.1256        1.4697 ± 0.4573
                          DLinear       0.2540 ± 0.1215    0.3557 ± 0.1828            0.3716 ± 0.0193        1.1883 ± 0.1979
                        FEDformer       0.4318 ± 0.0692    0.6039 ± 0.1097            0.4039 ± 0.1143        1.5286 ± 0.1508
                       iTransformer     0.5162 ± 0.1367    0.6761 ± 0.1770            0.4542 ± 0.0239        1.7910 ± 0.3722
                         NSformer       0.5238 ± 0.0694    0.7105 ± 0.1033            0.4992 ± 0.0975        1.8138 ± 0.1922
                         PatchTST       0.3821 ± 0.1871    0.5134 ± 0.2635            0.4255 ± 0.1533        1.4411 ± 0.3814
                         TimesNet       0.3050 ± 0.3439    0.4296 ± 0.4864            0.5181 ± 0.1404        1.3737 ± 0.8857
                         RFormer        0.5315 ± 0.2519    0.6671 ± 0.3255            0.5202 ± 0.0555        1.8014 ± 0.6303
                        SIT (Ours)      0.7715 ± 0.0627    0.9743 ± 0.0998            0.3271 ± 0.0094        1.9215 ± 0.1792
Table 1. Portfolio performance of SIT versus baselines across 40- and 50-asset universes. The best, second-best, and third-best results for
each metric are highlighted in red, blue, and bold, respectively.

distribution, which is the objective in (17). Eq. (19) lever-                      multiple market regimes, including the recent volatility.
ages the dual representation of CVaR (Rockafellar et al.,
2000) under the confidence–level convention: CVaRα (Z) =                           Baseline Models The performance of our proposed model,
                 1
minν∈R (ν + 1−α    E[(Z − ν)+ ]) with tail mass 1 − α. Thus                        SIT, is compared against a comprehensive suite of bench-
νω equals the α–quantile (VaRα ) of the intra–scenario loss                        marks spanning traditional and deep learning approaches.
distribution. Finally, Eq. (20) presents the empirical objec-                      Traditional baselines include Equally Weighted Portfolio
tive function used in training, where the expectation Eω∼D                         (EWP) (DeMiguel et al., 2009), Global Minimum Vari-
is approximated by an average over a batch of N scenar-                            ance (GMV) (Clarke et al., 2011; Markowitz, 1952), Con-
ios {ωi }Ni=1 . For each scenario ωi , the optimal ν̂i is the                      ditional Value-at-Risk (CVaR) (Rockafellar et al., 2000)
empirical α–quantile of its losses {L(k) (θωi )}K
                                                k=1 .                              and Hierarchical Risk Parity (HRP) (Lopez de Prado,
                                                                                   2016). The portfolio optimization strategy forms the second
3. Experiment                                                                      stage of our deep learning-based comparisons, which use
                                                                                   predictions from various state-of-the-art time-series fore-
3.1. Implementation details                                                        casting models as input. These forecasters include deep
Dataset Experiments used three portfolios of 30, 40, and                           learning models such as Autoformer (Wu et al., 2021),
50 S&P 100 companies. We also selected two additional                              DLinear (Zeng et al., 2023) FEDformer (Zhou et al., 2022),
portfolios of 10 and 20 assets from the DOW30 to validate                          PatchTST (Nie et al., 2022), iTransformer (Liu et al.,
performance against a different index composition, which                           2023), Non-stationary Transformers (NSformer) (Liu
is often characterized as more concentrated. Furthermore,                          et al., 2022), TimesNet (Wu et al., 2022) and RFormer
to evaluate robustness across different market dynamics, we                        (Moreno-Pino et al., 2024). Details of the parameter search
included two portfolios consisting of 50 and 100 assets from                       space are provided in Appendix D.
the CSI 300 index. The daily price data was sourced from
Wharton Research Data Services (WRDS). The data was                                Evaluation Metrics The strategies were evaluated us-
partitioned chronologically into distinct training, validation,                    ing four standard financial metrics, assuming a zero risk-
and test periods. The training set spans from January 1,                           free rate. Risk-adjusted performance was measured by the
2000, to December 31, 2016. The validation set from Jan-                           Sharpe Ratio, which accounts for total volatility, and the
uary 1, 2017, to December 31, 2019 and the test set from                           Sortino Ratio, a refinement that isolates downside risk by
January 1, 2020, to December 27, 2024. This split covers                           considering only downside deviation; higher values are su-
                                                                                   perior for both. Overall growth was tracked by the Final

                                                                               5

===== PAGE 6 =====

                                     Signature-Informed Transformer for Asset Allocation

Wealth Factor, while the Maximum Drawdown quantified                  dently removing a single key component from the full SIT
the largest peak-to-trough percentage decline, with a lower           model, while all other hyperparameters are held constant.
value being preferable.                                               This module-drop protocol allows for a precise evaluation
                                                                      of each component’s marginal contribution. The variants
3.2. Can SIT deliver superior risk-adjusted                           evaluated are: (i) w/o CVaR, which replaces the Condi-
     performance?                                                     tional Value-at-Risk objective with a risk-neutral objective
                                                                      of maximizing mean returns (ii) w/o Asset Attn, which
We evaluate the out-of-sample asset allocations efficacy of           disables the entire Signature-Informed Self-Attention mech-
our proposed model: SIT. The comprehensive performance                anism across assets (iii) w/o Financial Bias, which removes
metrics, including risk-adjusted returns and downside risk,           the signature-derived bias term from the attention scores,
are presented for the 40- and 50-asset universes (see Ap-             reverting to a standard self-attention mechanism and (iv)
pendix G for the 30-asset universe experiment). Our analysis          w/o Gate γ, which removes the learnable gate γ that scales
underscores that the quality of asset allocation, rather than         the financial bias.
raw predictive accuracy, is the decisive factor for success, a
central tenet of our work. The empirical results, summarized
in Table 1, demonstrate that SIT consistently and signifi-               Panel A. Asset 40 Universe
cantly outperforms all baseline models across the primary                     Models           Sharpe    Sortino    MDD      Wealth
                                                                            SIT (Ours)         0.6717    0.8232    0.3611    1.7903
metrics of risk-adjusted return and wealth generation. In                    w/o CVaR          0.5691c   0.7057b   0.3695    1.6409b
the 40-asset universe, for instance, SIT achieves a Sharpe                w/o Asset Attn       0.5284c   0.6576c   0.3342b   1.5381c
Ratio of 0.6717 and a Sortino Ratio of 0.8232, decisively                w/o Financial Bias    0.6045b   0.7590b   0.3431c   1.6801c
                                                                            w/o Gate γ         0.5251    0.6489c   0.3470b   1.5470c
surpassing the next-best traditional baseline EWP and all
deep learning counterparts. This translates into superior                Panel B. Asset 50 Universe
capital growth, with SIT yielding a Final Wealth Factor of                    Models           Sharpe    Sortino    MDD      Wealth
1.7903, the highest among all tested strategies.                            SIT (Ours)         0.7715    0.9743    0.3271    1.9215
                                                                             w/o CVaR          0.5923c   0.7294c   0.3606b   1.6622c
The primary contribution of SIT becomes evident when                      w/o Asset Attn       0.6268c   0.7650b   0.3298    1.6562b
                                                                         w/o Financial Bias    0.6047c   0.7545b   0.3224    1.6260b
contrasted with the predict-then-optimize models. These                     w/o Gate γ         0.5831c   0.7138c   0.3305    1.5945c
models, which rely on minimizing statistical forecasting er-          Table 2. Ablation study of SIT’s core components.Superscripts b
ror, exhibit poor and highly unstable portfolio performance.          and c indicate statistical significance at p < 0.05 and p < 0.001
Many fail to outperform even simple heuristics. Their high            in paired tests against SIT (Ours).
standard deviations across runs underscore the problem of
error amplification, where small prediction inaccuracies are          The results, summarized in Table 2, underscore the impor-
magnified by the downstream optimizer into fragile, im-               tance of each design choice. The most critical element is the
practical allocations. This finding empirically validates our         decision-focused approach. When the Conditional Value-
core hypothesis. Optimizing for prediction is not a valid             at-Risk (CVaR) loss is replaced with a standard risk-neutral
proxy for optimizing for allocation quality. In addition to its       objective (w/o CVaR), the Sharpe Ratio on the 40-asset uni-
inductive biases designed for financial assets, SIT’s decision-       verse falls from 0.6717 to 0.5691. This demonstrates that di-
focused approach directly minimizes the portfolio’s CVaR,             rect optimization for risk-adjusted outcomes is essential for
fundamentally aligning the model’s objective with the fi-             producing stable allocations that are resilient to tail events.
nancial goal and thereby avoiding this critical pitfall. Fur-         The components of the Signature-Informed Self-Attention
thermore, SIT demonstrates a superior risk-return profile             mechanism prove equally vital. Removing the asset-wise
compared to traditional quantitative strategies. While risk-          attention layer entirely (w/o Asset Attn) severely reduces the
minimizing models like Global Minimum Variance (GMV)                  model’s ability to reason about portfolio structure, causing
achieve low Maximum Drawdown (MDD) (e.g., 0.2743 in                   a steep performance drop (Sharpe of 0.5284). Furthermore,
the 40-asset case), they do so at the cost of substantially           removing just the signature-based inductive bias (w/o Finan-
lower returns (Sharpe Ratio of 0.4148). SIT, conversely,              cial Bias), i.e. reverting to a standard attention mechanism,
maintains a competitive MDD (0.3611) while delivering                 still leads to significant degradation (Sharpe of 0.6045). This
significantly higher returns. For the results on the DOW30            confirms that injecting principled geometric knowledge of
and SCI300, please refer to Appendix G.                               lead-lag structures (Proposition 2.1) is more effective than
                                                                      forcing the model to learn these relationships from scratch.
3.3. Module-Level Contribution Experiments                            Finally, removing the learnable gate γ (w/o Gate γ) is highly
                                                                      detrimental (Sharpe of 0.5251), highlighting that the model
To dissect the contribution of each architectural pillar of
                                                                      must learn to dynamically modulate the influence of these
the SIT, we conduct a comprehensive ablation study. For
                                                                      financial priors (Theorem 2.2) to adapt to changing market
this analysis, each ablated variant is created by indepen-
                                                                      regimes.

                                                                  6

===== PAGE 7 =====

                                                                                               Signature-Informed Transformer for Asset Allocation

     3.4. Are signatures effective at driving attention?                                                                              amplify risk-relevant dependencies. In Appendix , Figure
                                                                                                                                      7 overlays the learned gate γ on portfolio drawdowns. We
     SIT perturbs asset-axis attention logits by an additive,
                                                                                                 Qk,h K⊤
                                                                                                                                      observe that higher values of γ tend to cluster during volatile
    signature-induced bias, Logitsk,h = √d k,h + γBk,h ∈                                                                              episodes. This suggests that SIT increases the weight of
                                                 k
    Rd×d where Bk,h aggregates the alignment equation                                                                                 signature-based priors precisely when cross-asset relations
    (10) between the query’s informational need and the                                                                               are most informative and prediction noise is elevated. We
    cross-signature embedding. Theorem 2.2 predicts that in-                                                                          therefore conjecture that this financial bias offers a plausi-
    creasing this alignment in the query direction strictly raises                                                                    ble explanation for the results in Table 1. Specifically, it
    attention weight on the corresponding key when γ > 0. Cou-                                                                        allows SIT to achieve the high risk-adjusted returns while
    pled with Proposition 2.1, which links persistent lead–lag                                                                        maintaining a robust diversification profile comparable to
    to non zero second-order signatures, the method suggests                                                                          the EWP.
    a testable implication. Consequently, assets whose signa-
    tures are stronger should systematically attract more in-                                                                         3.5. Why PFL approach fail financial objectives?
    bound attention. We formalize this implication by defin-
                                                                                                                                      Across all eight forecasting models, prediction alone does
    ing, at each decision time t, a per-asset signature-strength
                            PH PNH Pd                                                                                                 not translate into superior trading performance. As illus-
    score st,j = HN1H d k=1 h=1             m=1 (Bk,h )m,j and                                                                        trated in Figure 4, which reports out-of-sample Sharpe ra-
    the corresponding inbound-attention share at,j =
       1
            PH PNH Pd                                                                                                                 tios after CVaR optimization, the decision-focused learning
    HNH d     k=1     h=1    m=1 αk,h,m→j . We then compute                                                                           (blue) consistently dominates the prediction-only approach
    the Pearson correlation between {st,j }dj=1 and ({at,j }dj=1 )                                                                    (gray) across both the 40- and 50-asset universes. Moreover,
    at each t and examine the distribution of these correlations                                                                      as observed in Figure 1, the gap widens in the 50-asset uni-
    across the test horizon.                                                                                                          verse, indicating that higher dimensionality amplifies the
                     2.5
                                                                                                                                      failure of the predict-then-optimize pipeline.
                                                       mean=0.540                               mean=0.611
                                                                                         2.0
                     2.0



Density (asset 40)                                                  Density (asset 50)
                                                                                         1.5
                     1.5                                                                                                                                         0.8                                    MSE      DFL




                                                                                                                                       Sharpe Ratio (Asset 40)
                                                                                         1.0
                     1.0
                                                                                                                                                                 0.6
                     0.5                                                                 0.5

                     0.0                                                                 0.0                                                                     0.4
                           0.2     0.4       0.6          0.8                                   0.2     0.4      0.6        0.8
                                 Pearson Corrleation                                                  Pearson Corrleation
                                                                                                                                                                 0.2

    Figure 3. Distribution of correlations between signature strength
    and attention weights.




                                                                                                                                       Sharpe Ratio (Asset 50)
                                                                                                                                                                 0.8
     In Figure 3, the distribution is right-skewed with means of                                                                                                 0.6
     0.540 for the 40-asset universe and 0.611 for the 50-asset                                                                                                  0.4
     universe, indicating that stronger signature signals are as-                                                                                                0.2
     sociated with higher inbound attention mass. The heavy
                                                                                                                                                                 0.0
     right tail shows frequent periods in which attention concen-
                                                                                                                                                                       rme
                                                                                                                                                                          r       ear         me
                                                                                                                                                                                                 r         er        er        ST         et         er
     trates on assets whose signature-derived relations are most                                                                                                    oFo       DLin         For         orm       orm       chT        esN        orm
                                                                                                                                                                 Aut                    FED         nsF       NSF       Pat       Tim        RFf
                                                                                                                                                                                               iTra
     salient, while the paucity of negative correlations rules out
     a degeneracy in which the bias is ignored by the attention                                                                       Figure 4. Out-of-sample Sharpe ratios after CVaR portfolio opti-
     mechanism. These empirical patterns directly instantiate the                                                                     mization on 40- and 50-asset S&P100 universes.
     monotonicity predicted by Theorem 2.2. So, as alignment
                                                                                                                                      The failure of MSE-based approaches stems from the objec-
     bk,h,j,l strengthens, the induced change in αj,l is positive,
                                                                                                                                      tive mismatch. See Appendix F for details on the two-
     and the learned γ scales this effect without flipping its sign.
                                                                                                                                      stage implementation. Prediction-focused training opti-
    The financial significance of this correlation is twofold.                                                                        mizes a surrogate that is misaligned with the financial goal.
    First, B is not a static embedding. This couples dynamic                                                                          Therefore, prediction losses weight all errors equally and
    queries qdyn
              k,j with cross-signatures β i,j,l . Hence, the cor-                                                                     are blind to the downstream mapping from forecasts to
    relation becomes most apparent when the model routes                                                                              actions. A model that is optimal for Lpred need not be
    information toward assets whose relational signatures are                                                                         even approximately optimal for CVaR. Consequently, tiny
    currently informative. Second, because SIT is trained solely                                                                      cross-sectional ranking errors induced by MSE training can
    through the portfolio-level CVaRα loss, the learned atten-                                                                        be amplified by the optimizer, effectively flipping the iden-
    tion must improve tail-aware allocations rather than just                                                                         tity of the largest weights. The evidence in Figure 4 and
    forecast error. The observed right-skew therefore indicates                                                                       the mechanisms above explain why predict-then-optimize
    that signatures are not merely present but actively utilized to                                                                   pipelines produce low and unstable Sharpe despite compet-

                                                                                                                                  7

===== PAGE 8 =====

                                                                            Signature-Informed Transformer for Asset Allocation

                                                        Universe: 40 Assets                                                                                            Universe: 50 Assets

                          0.0   0.619      0.561      0.612      0.615        0.618     0.672      0.630      0.515                                 0.532            0.543          0.615           0.593                                    0.771           0.763                  0.75




Transaction Cost (bps)
                                (±0.159)   (±0.142)   (±0.056)   (±0.040)    (±0.130)   (±0.063)   (±0.094)   (±0.077)                             (±0.080)         (±0.072)        (±0.073)        (±0.122)                                (±0.063)         (±0.087)




                                                                                                                                                                                                                                                                                            Mean Sharpe Ratio
                                                                                                                                                                                                                                                                                    0.70

                          5.0   0.598      0.542      0.593      0.598        0.598     0.655      0.614      0.501                                 0.519            0.529          0.598           0.577                                    0.754           0.747                  0.65
                                (±0.159)   (±0.140)   (±0.051)   (±0.036)    (±0.126)   (±0.056)   (±0.091)   (±0.076)                             (±0.079)         (±0.071)        (±0.076)        (±0.124)                                (±0.059)         (±0.082)               0.60
                                                                                                                                                                                                                                                                                    0.55
                         10.0   0.578      0.522      0.575      0.580        0.579     0.638      0.598      0.486                                 0.505            0.515          0.581           0.561                                    0.736           0.731                  0.50
                                (±0.158)   (±0.137)   (±0.047)   (±0.031)    (±0.122)   (±0.049)   (±0.087)   (±0.074)                             (±0.078)         (±0.070)        (±0.079)        (±0.127)                                (±0.055)         (±0.078)
                                  0.8        0.9        1.0        1.1         1.2        1.3        1.4          0.8                                 0.9              1.0             1.1            1.2                                      1.3              1.4
                                                       Allocation Concentration                                                                                       Allocation Concentration

                                Figure 5. Sharpe ratio sensitivity to transaction costs and allocation concentration (τ ). Left: 40 assets Right: 50 assets.
itive Lpred . By differentiating through the portfolio layer                                                             erate diversification can temper trading; with more assets,
and optimizing the risk metric of interest, decision-focused                                                             broader participation slightly increases cost sensitivity.
learning reshapes the logits so that only forecast features that
                                                                                                                                                          HHI                                                                         3.5          HHI
improve allocation under constraints and tails are amplified.                                                                                3.0          Entropy                                                                                  Entropy




                                                                                                                  Concentration (asset 40)                                                                 Concentration (asset 50)
                                                                                                                                                                                                                                      3.0
This alignment both raises risk-adjusted returns and tightens                                                                                2.5
                                                                                                                                                                                                                                      2.5
                                                                                                                                             2.0                                                                                      2.0
variability across runs, which we observe consistently across                                                                                1.5                                                                                      1.5
backbones and universes. We believe that aligning the train-                                                                                 1.0                                                                                      1.0
ing objective with the financial objective is necessary for                                                                                  0.5                                                                                      0.5
                                                                                                                                             0.0                                                                                      0.0
turning predictive signals into reliable portfolios.                                                                                               0.50   0.75      1.00     1.25   1.50     1.75   2.00                                    0.50     0.75    1.00     1.25   1.50    1.75         2.00
                                                                                                                                                                     Temperature τ                                                                            Temperature τ

3.6. Sensitivity Analysis                                                                                                                Figure 6. Impact of temperature τ on portfolio diversification.

We examine how proportional trading frictions and allo-                                                                 Also, as shown in Figure 6, increasing the softmax temper-
cation concentration affect SIT. The concentration param-                                                               ature τ monotonically reduces cross-sectional concentra-
eter τ is the softmax temperature in the allocation layer,                                                              tion and increases diversification.  Herfindahl–Hirschman
                                                                                                                        Index HHI(w) =P j wj2 declines, while Shannon en-
                                                                                                                                              P
   (k)                (k)
wt = softmax(µ̂t /τ ). Smaller τ concentrates capital,
larger τ spreads it. We sweep τ ∈ {0.8, ..., 1.4}. Transac-                                                             tropy H(w) = − j wj log wj rises. For any fixed τ , the
tion costs are one-way proportional fees of c ∈ 0, 5, 10 basis                                                          50-asset universe achieves lower HHI and higher H than the
points per dollar traded. All other settings follow the main                                                            40-asset universe, indicating a more diffuse allocation when
evaluation: long-only, fully invested, monthly (k-step) rebal-                                                          the investable set is broader. These diagnostics provide an
ancing on the 40- and 50-asset universes, and a zero risk-free                                                          interpretable, one-to-one control of concentration through τ ,
rate for all risk-adjusted metrics. Figure 5 reports mean (±                                                            useful when desk policies cap the effective number of active
std) Sharpe ratios for every (τ, c) pair, with the 40-asset                                                             lines or impose minimum diversification.
universe on the left and 50-asset on the right. Two patterns                                                             4. Conclusion
are stable across universes. First, performance peaks at mod-
erate dispersion, near τ ≈ 1.3. Second, frictions compress                                                              This work argues that effective quantitative portfolio man-
Sharpe roughly linearly over this range: moving from 0 to                                                               agement requires robust allocation policies, not just opti-
10 bps reduces Sharpe by about 0.03–0.04 at the optimum.                                                                mizing prediction accuracy. We introduce the Signature-
                                                                                                                        informed Transformer, a novel framework using path signa-
Trading costs predictably erode realized performance, yet
                                                                                                                        tures for rich feature representation, a signature-augmented
the impact is mitigated when allocations avoid both extreme
                                                                                                                        attention mechanism for financial biases like lead-lag ef-
concentration (small τ ) and excessive diffusion (very large
                                                                                                                        fects, and a training objective that directly minimizes port-
τ ). The interior optimum near τ ≈ 1.3 indicates that SIT’s
                                                                                                                        folio Conditional Value-at-Risk. Our empirical results show
gains arise from robust allocation—balancing diversification
                                                                                                                        that SIT decisively outperforms baselines, which often
with conviction rather than from raw prediction accuracy
                                                                                                                        are harmed by objective mismatch and error amplification.
alone. The cost penalty is slightly smaller at the optimum in
                                                                                                                        SIT’s performance remains superior under realistic trans-
the 40-asset case (drop 0.034) than for concentrated settings
                                                                                                                        action costs, underscoring the importance of its calibrated,
such as τ ∈ {0.8, 0.9} (drops 0.039–0.041), whereas in the
                                                                                                                        signature-based architecture. While tested on U.S. equity
50-asset universe the smallest penalty occurs at more con-
                                                                                                                        data, this framework could be extended to higher-frequency,
centrated τ (e.g., τ = 0.9 drops 0.027). This non-linearity
                                                                                                                        global, multi-asset markets. Ultimately, SIT provides a
suggests that the turnover induced by spreading capital inter-
                                                                                                                        blueprint for ML systems to progress from forecasting to-
acts with cross-sectional breadth. With fewer assets, mod-
                                                                                                                        wards a more end-to-end, risk-aware capital allocation.

                                                                                                              8

===== PAGE 9 =====

                                     Signature-Informed Transformer for Asset Allocation

References                                                            Hwang, Y., Kong, Y., Zohren, S., and Lee, Y. Decision-
                                                                       informed neural networks with large language model
Arribas, I. P., Salvi, C., and Szpruch, L. Sig-sdes model
                                                                       integration for portfolio optimization. arXiv preprint
  for quantitative finance. In Proceedings of the First ACM
                                                                       arXiv:2502.00828, 2025a.
  International Conference on AI in Finance, pp. 1–8, 2020.
Bonnier, P., Kidger, P., Arribas, I. P., Salvi, C., and               Hwang, Y., Lee, Y., Lee, J., Zohren, S., Kim, J. H., Kim,
  Lyons, T. Deep signature transforms. arXiv preprint                  W. C., Lee, Y., and Fabozzi, F. J. Deep learning in as-
  arXiv:1905.08494, 2019.                                              set management: Architectures, applications, and chal-
                                                                       lenges. Applications, and Challenges (September 15,
Buehler, H., Gonon, L., Teichmann, J., and Wood, B. Deep               2025), 2025b.
  hedging. Quantitative Finance, 19(8):1271–1291, 2019.
                                                                      Kidger, P., Morrill, J., Foster, J., and Lyons, T. Neural
Cartea, Á., Cucuringu, M., and Jin, Q. Detecting lead-                 controlled differential equations for irregular time series.
  lag relationships in stock returns and portfolio strategies.          Advances in neural information processing systems, 33:
  Available at SSRN 4599565, 2023.                                      6696–6707, 2020.
Chevyrev, I. and Kormilitzin, A. A primer on the sig-
  nature method in machine learning. arXiv preprint                   Király, F. J. and Oberhauser, H. Kernels for sequentially
  arXiv:1603.03788, 2016.                                               ordered data. Journal of Machine Learning Research, 20
                                                                        (31):1–45, 2019.
Chung, M., Lee, Y., Kim, J. H., Kim, W. C., and Fabozzi,
  F. J. The effects of errors in means, variances, and cor-           Lee, J., Tae, I., and Lee, Y. Anatomy of machines for
  relations on the mean-variance framework. Quantitative                markowitz: Decision-focused learning for mean-variance
  Finance, 22(10):1893–1903, 2022.                                      portfolio optimization. arXiv preprint arXiv:2409.09684,
                                                                        2024a.
Clarke, R., De Silva, H., and Thorley, S. Minimum-variance
  portfolio composition. Journal of Portfolio Management,             Lee, Y., Kim, J. H., Kim, W. C., and Fabozzi, F. J. An
  37(2):31, 2011.                                                       overview of machine learning for portfolio optimization.
                                                                        Journal of Portfolio Management, 51(2), 2024b.
Cont, R. Empirical properties of asset returns: stylized
  facts and statistical issues. Quantitative finance, 1(2):223,       Li, S., Jin, X., Xuan, Y., Zhou, X., Chen, W., Wang, Y.-
  2001.                                                                 X., and Yan, X. Enhancing the locality and breaking the
Costa, G. and Iyengar, G. N. Distributionally robust end-to-            memory bottleneck of transformer on time series forecast-
  end portfolio construction. Quantitative Finance, 23(10):             ing. Advances in neural information processing systems,
  1465–1482, 2023.                                                      32, 2019.

DeMiguel, V., Garlappi, L., and Uppal, R. Optimal versus              Lim, B., Arık, S. Ö., Loeff, N., and Pfister, T. Temporal
  naive diversification: How inefficient is the 1/n portfolio           fusion transformers for interpretable multi-horizon time
  strategy? The review of Financial studies, 22(5):1915–                series forecasting. International journal of forecasting,
 1953, 2009.                                                            37(4):1748–1764, 2021.
Duan, Y., Wang, W., and Li, J. Factorgcl: A hypergraph-               Liu, Y., Wu, H., Wang, J., and Long, M. Non-stationary
  based factor model with temporal residual contrastive                 transformers: Exploring the stationarity in time series
  learning for stock returns prediction. In Proceedings                 forecasting. Advances in neural information processing
  of the AAAI Conference on Artificial Intelligence, vol-               systems, 35:9881–9893, 2022.
  ume 39, pp. 173–181, 2025.
                                                                      Liu, Y., Hu, T., Zhang, H., Wu, H., Wang, S., Ma, L.,
Fama, E. F. Efficient capital markets. Journal of finance, 25
                                                                        and Long, M. itransformer: Inverted transformers are
  (2):383–417, 1970.
                                                                        effective for time series forecasting. arXiv preprint
Fischer, T. and Krauss, C. Deep learning with long short-               arXiv:2310.06625, 2023.
  term memory networks for financial market predictions.
  European journal of operational research, 270(2):654–               Lopez de Prado, M. Building diversified portfolios that out-
  669, 2018.                                                            perform out-of-sample. Journal of Portfolio Management,
                                                                        2016.
Gyurkó, L. G., Lyons, T., Kontkowski, M., and Field, J.
  Extracting information from the signature of a financial            Lyons, T. and McLeod, A. D. Signature methods in machine
  data stream. arXiv preprint arXiv:1307.7244, 2013.                    learning. arXiv preprint arXiv:2206.14674, 2022.

                                                                  9

===== PAGE 10 =====

                                    Signature-Informed Transformer for Asset Allocation

Lyons, T. J. Differential equations driven by rough sig-              Wu, H., Hu, T., Liu, Y., Zhou, H., Wang, J., and Long, M.
  nals. Revista Matemática Iberoamericana, 14(2):215–                 Timesnet: Temporal 2d-variation modeling for general
  310, 1998.                                                           time series analysis. arXiv preprint arXiv:2210.02186,
                                                                       2022.
Lyons, T. J., Caruana, M., and Lévy, T. Differential equa-
  tions driven by rough paths: Ecole d’Eté de Probabilités          Xu, W., Liu, W., Wang, L., Xia, Y., Bian, J., Yin, J., and Liu,
  de Saint-Flour XXXIV-2004. Springer, 2007.                            T.-Y. Hist: A graph-based framework for stock trend fore-
                                                                        casting via mining concept-oriented shared information.
Markowitz, H. Portfolio selection. The Journal of Finance,              arXiv preprint arXiv:2110.13716, 2021.
 7(1):77–91, March 1952. doi: 10.2307/2975974. URL
 https://www.jstor.org/stable/2975974.                                Yoo, J., Soun, Y., Park, Y.-c., and Kang, U. Accurate mul-
                                                                        tivariate stock movement prediction via data-axis trans-
Miori, D. and Cucuringu, M. Returns-driven macro                        former with multi-level contexts. In Proceedings of the
 regimes and characteristic lead-lag behaviour between                  27th ACM SIGKDD Conference on Knowledge Discovery
 asset classes. arXiv preprint arXiv:2209.00268, 2022.                  & Data Mining, pp. 2037–2045, 2021.

Moody, J. and Saffell, M. Learning to trade via direct                Zeng, A., Chen, M., Zhang, L., and Xu, Q. Are transformers
 reinforcement. IEEE transactions on neural Networks,                   effective for time series forecasting? In Proceedings of
 12(4):875–889, 2001.                                                   the AAAI conference on artificial intelligence, volume 37,
                                                                        pp. 11121–11128, 2023.
Moreno-Pino, F., Arroyo, Á., Waldon, H., Dong, X., and
 Cartea, Á. Rough transformers: Lightweight and contin-              Zhang, Z., Zohren, S., and Roberts, S. Deep learning for
 uous time series modelling through signature patching.                 portfolio optimization. arXiv preprint arXiv:2005.13665,
 Advances in Neural Information Processing Systems, 37:                 2020.
 106264–106294, 2024.
                                                                      Zhou, H., Zhang, S., Peng, J., Zhang, S., Li, J., Xiong, H.,
Nie, Y., Nguyen, N. H., Sinthong, P., and Kalagnanam, J. A              and Zhang, W. Informer: Beyond efficient transformer for
  time series is worth 64 words: Long-term forecasting with             long sequence time-series forecasting. In Proceedings of
  transformers. arXiv preprint arXiv:2211.14730, 2022.                  the AAAI conference on artificial intelligence, volume 35,
                                                                        pp. 11106–11115, 2021.
Rockafellar, R. T., Uryasev, S., et al. Optimization of condi-
                                                                      Zhou, T., Ma, Z., Wen, Q., Wang, X., Sun, L., and Jin,
  tional value-at-risk. Journal of risk, 2:21–42, 2000.
                                                                        R. Fedformer: Frequency enhanced decomposed trans-
Salvi, C., Cass, T., Foster, J., Lyons, T., and Yang, W. The            former for long-term series forecasting. In Interna-
  signature kernel is the solution of a goursat pde. SIAM               tional conference on machine learning, pp. 27268–27286.
  Journal on Mathematics of Data Science, 3(3):873–899,                 PMLR, 2022.
  2021.

Tong, A., Nguyen-Tang, T., Lee, D., Tran, T. M., and Choi,
  J. Sigformer: Signature transformers for deep hedging. In
  Proceedings of the Fourth ACM International Conference
  on AI in Finance, pp. 124–132, 2023.

Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones,
  L., Gomez, A. N., Kaiser, Ł., and Polosukhin, I. At-
  tention is all you need. Advances in neural information
  processing systems, 30, 2017.

Woo, G., Liu, C., Sahoo, D., Kumar, A., and Hoi, S. Ets-
 former: Exponential smoothing transformers for time-
 series forecasting. arXiv preprint arXiv:2202.01381,
 2022.

Wu, H., Xu, J., Wang, J., and Long, M. Autoformer: Decom-
 position transformers with auto-correlation for long-term
 series forecasting. Advances in neural information pro-
 cessing systems, 34:22419–22430, 2021.

                                                                 10

===== PAGE 11 =====

                                    Signature-Informed Transformer for Asset Allocation

A. Appendix. Related works
Deep Learning in Asset Allocation The application of deep learning in quantitative trading has largely bifurcated into two
distinct paradigms. The first, the classic Predict Focused Learning (PFL) pipeline, focuses on developing return-prediction
models. In this stream of research, complex architectures map market data to future price movements. For instance,
Transformers have been adapted to capture temporal dependencies in asset prices for return forecasting (Fischer & Krauss,
2018; Yoo et al., 2021; Lim et al., 2021). Some models employ Graph Neural Networks (GNNs) to explicitly model
inter-asset relationships, such as sector correlations, to improve prediction accuracy (Xu et al., 2021; Duan et al., 2025).
Despite their architectural novelty, these methods inherit the fundamental flaws of a decoupled approach (Lee et al., 2024b).
They suffer from objective mismatch, as optimizing for prediction error (e.g., Mean Squared Error) does not guarantee
profitable portfolio construction, and are susceptible to error amplification, where small prediction inaccuracies lead to
drastically suboptimal and unstable allocations (Chung et al., 2022). A more promising direction, which we term Decision
Focused Learning (DFL), seeks to overcome these limitations by training policies end-to-end. These models learn a direct
mapping from market state to portfolio allocations, optimizing a true financial objective like a risk-adjusted return metric.
Foundational work demonstrated how to embed financial operators, such as portfolio value and Sharpe ratio, within a deep
network, making the entire strategy differentiable and trainable via gradient descent (Buehler et al., 2019; Zhang et al., 2020;
Costa & Iyengar, 2023). Recent research has increasingly emphasized embedding practical portfolio constraints into the
model training phase. Typical examples include prohibiting short selling, ensuring full investment (i.e., portfolio weights
sum to one), and placing upper or lower bounds on individual asset allocations, all of which are incorporated directly into the
model architecture or loss function (Lee et al., 2024a; Hwang et al., 2025a). While these end-to-end frameworks efficiently
align the model’s training objective with financial goals, they often fall short in explicitly guiding the model to learn and
utilize the diverse information present in multi-asset settings. This leaves a critical research gap. These models lack a
strong financial inductive bias to explicitly represent the non-linear, path-dependent nature of price series and the geometric,
time-local lead-lag relationships between assets. In our implementation, the predicted returns µ̂ serve only as internal logits
for a differentiable allocation layer. All parameters are trained end-to-end solely through the portfolio-level CVaR objective,
not a pointwise prediction loss, aligning with decision-focused learning. Our work addresses this gap by integrating the
mathematical theory of path signatures directly into a transformer’s attention mechanism, creating an optimization-aware
model that is architecturally designed to understand the underlying geometry of market dynamics. See (Lee et al., 2024b;
Hwang et al., 2025b) for more detailed review of asset allocations

Transformer-Based Time Series Forecasting The success of the Transformer architecture in natural language processing
has inspired its widespread adoption for time series forecasting. The core innovation, the self-attention mechanism,
allows these models to dynamically weigh the importance of all past time steps when predicting future values, enabling
them to capture complex, long-range dependencies without the sequential processing limitations of recurrent neural
networks(Vaswani et al., 2017; Li et al., 2019). To extend the receptive field without incurring the quadratic cost of
full attention, a stream of variants introduce sparsity or hierarchical structure. For example, LogSparse(Li et al., 2019),
ProbSparse(Zhou et al., 2021) and related kernels discard low-magnitude query–key interactions to achieve O(L log L)
complexity while retaining global context. From a more fundamental time series data perspective, Autoformer(Wu et al.,
2021), FEDformer(Zhou et al., 2022) and ETSformer(Woo et al., 2022) decompose signals into trend–seasonality (or
frequency-domain) components so that long-horizon patterns can be modeled additively and multiplicatively with reduced
error accumulation. More recent PatchTST(Nie et al., 2022) and TimesNet(Wu et al., 2022) patch neighboring observations
or convolve multi-scale windows before attention, embedding stronger inductive biases for periodicity and aliasing control.
While these innovations alleviate the long-range dependency bottleneck, they remain largely data-agnostic. When applied
to financial series they struggle with regime-dependent non-stationary, heavy-tailed noise, and asynchronous cross-asset
lead–lag effects, causing attention scores to lock onto transient outliers and degrading out-of-sample robustness (Cartea
et al., 2023; Cont, 2001; Miori & Cucuringu, 2022). Our approach departs from this paradigm by embedding each asset’s
path in a Rough Path Signature space that is stable under time-reparameterization and robust to micro-structure noise, and by
augmenting the attention logits with second-order cross-signature terms that encode the signed-area geometry underpinning
lead–lag dynamics. Coupled with scenario-based optimization to hedge against structural breaks, SIT addresses both the
generic long-range dependency problem and the finance-specific pathologies that limit existing Transformer forecasters.

Path Signatures in Time Series and Finance The path signature, originating from Rough Path Theory, offers a non-
parametric and faithful representation of streamed data by summarizing the geometry of a path as a sequence of iterated
integrals (Lyons, 1998). A key property is its universality: any continuous function on the space of paths can be arbitrarily

                                                              11

===== PAGE 12 =====

                                        Signature-Informed Transformer for Asset Allocation

well-approximated by a linear function of the signature’s terms, making it a powerful basis for feature extraction (Chevyrev
& Kormilitzin, 2016). In practice, the signature is truncated at a finite order M , yielding a vector SigM (X) that is robust
to irregular sampling due to its invariance to time reparameterization. However, this truncation introduces a trade-off,
as the feature dimension grows exponentially with the order M and polynomially with the path dimension d, posing a
significant computational burden. This challenge has motivated alternatives like signature kernels, which compute inner
products in the high-dimensional feature space implicitly, avoiding explicit feature construction (Király & Oberhauser,
2019). In machine learning, signatures provide a potent inductive bias for modeling systems with path-dependent memory.
The most direct application involves using truncated signatures as static input features for standard models (Gyurkó et al.,
2013). More sophisticated integrations are found in continuous-time models like Neural Controlled Differential Equations
(CDEs), which learn a vector field that is controlled by the input path, effectively modeling the system’s response to a
driving signal (Kidger et al., 2020). For finance, a crucial insight arises from the signature’s geometry: the second-order
terms of a joint signature over two asset paths precisely encode their signed area, a direct and robust measure of their
temporal lead-lag relationship (Lyons & McLeod, 2022). This property has been successfully leveraged to build kernels for
detecting asymmetric dependencies between financial instruments, offering a principled alternative to traditional correlation
measures (Bonnier et al., 2019). Recent advancements extend this to attention mechanisms. the Rough Transformer
(Moreno-Pino et al., 2024) introduces multi-view signature attention to operate directly on continuous-time representations.
Also, applications to finance span volatility/return modeling, derivatives, and market microstructure. Early studies extracted
signature coordinates to forecast realized volatility and to detect temporal asymmetries (Gyurkó et al., 2013). In options,
signatures parameterize no-arbitrage dynamics and enable data-driven pricing/hedging (Arribas et al., 2020), including
transformer-style encoders fed with log/signatures (Tong et al., 2023). A crucial geometric motif is the second-order signed
area,                                                    Z               Z
                                             A(X i , X j ) =   X i dX j −    X j dX i ,                                      (21)

which encodes temporal asymmetry and lead–lag; signature kernels exploit this to compare pairs or small baskets of
assets (Chevyrev & Kormilitzin, 2016; Király & Oberhauser, 2019). Our architecture operationalization this motif at
scale: SIT injects cross-asset signature information as a dynamic, query-conditioned bias inside attention, so that pairwise
signed-area evidence modulates which assets attend to which others at each decision point (cf. Theorem 2.1). While
signatures mitigate non-stationarity and encode higher-order interactions, they incur truncation bias and can suffer from a
curse of dimensionality as either degree M or the number of assets grows; kernelization trades feature savings for quadratic
kernel costs (Salvi et al., 2021; Bonnier et al., 2019). Compared with state-space or transformer baselines, signatures
offer complementary bias—geometric invariances and lead–lag structure—rather than longer receptive fields alone. Prior
signature-based works typically (i) use signatures as fixed inputs or kernels outside the attention mechanism and (ii)
optimize predictive losses, not portfolio objectives (Gyurkó et al., 2013; Tong et al., 2023; Bonnier et al., 2019). SIT differs
by coupling signature-augmented, cross-asset attention with end-to-end CVaR optimization for long-only, fully-invested
portfolios, aligning representation, interaction, and objective (Buehler et al., 2019).

B. Appendix. Notation
For clarity and ease of reference, Table 3 provides a comprehensive summary of the key notations used throughout this
paper.

C. Appendix. Mathematical Proofs
Definition C.1. (Strict Lead-Lag Structure) Let Xt = (Xt1 , Xt2 ) be a continuous path of bounded variation on [0, T ]. We
say it possesses a strict lead-lag structure if there exist an integer N ≥ 1 and a partition 0 = t0 < t1 < · · · < t2N = T of
the interval [0, T ] such that the following conditions hold:

 (i) For each k ∈ {0, 1, . . . , N }, the coordinates coincide at the even-indexed partition points: Xt12k = Xt22k . Let this
     common value be denoted by Sk .

(ii) For each k ∈ {1, 2, . . . , N }:
        • On [t2k−2 , t2k−1 ] (the k-th lead interval), Xt1 varies to satisfy Xt12k−1 = Sk , while Xt2 remains constant at Sk−1 .
        • On [t2k−1 , t2k ] (the k-th lag interval), Xt1 remains constant at Sk , while Xt2 varies to satisfy Xt22k = Sk .

                                                                12

===== PAGE 13 =====

                                     Signature-Informed Transformer for Asset Allocation

    Symbol                      Description                                                   Type / Dimension
    R                           Set of real numbers                                           —
    E[·]                        Expectation operator                                          —
    0 = t0 < · · · < tn = T     Discrete decision times                                       Scalars
    d                           Number of tradable assets                                     ∈N
    Stji                        Price of asset j at time ti                                   Scalar
    Su                          Price vector (Su1 , . . . , Sud )                             ∈ Rd
    Ω                           Set of market scenarios (price paths)                         Sample space
    θ∈Θ                         Trainable parameters / parameter space                        Vector / set
    H                           Look-back window length (time steps)                          ∈N
    K                           Forecasting window length (time steps)                        ∈N
    M                           Signature truncation level                                    ∈N
    SigM (X[s,t] )              Truncated signature of path X up to level M                   ∈ Rdsig
    CVaRα (·)                   Conditional Value-at-Risk at level α                          Scalar
    sk,j                        Signature vector for slice k, asset j                         ∈ Rdsig
    vt                          Calendar/feature vector at time t                             ∈ RF
    ejasset                     Learnable embedding of asset j                                ∈ Rdmodel
    xk,j                        Input token for slice k, asset j                              ∈ Rdmodel
    Q, K, V                     Query, key, value matrices (per slice)                        ∈ Rd×dmodel
    β i,j,l                     Cross-signature embedding for pair (j, l)                     ∈ RNH ×dβ
    qdyn
      k,j                       Dynamic query bias for asset j, slice k                       ∈ RNH ×dβ
    γ                           Positive gate for signature bias                              ∈ R>0
         (k)
    {wti }K                                                                                   Each ∈ Rd , w = 1
                                                                                                           P
             k=1                Future portfolio weights at ti (long-only)
    {rti+k }Kk=1                Realized returns for steps 1:K                                Each ∈ Rd
        (k)
    {Lti+k }K k=1               Portfolio losses for steps 1:K                                Each scalar
    µ̂1:K
      ti                        Predicted k-step-ahead returns for k = 1, . . . , K           ∈ RK per asset; stacked as ∈ RK×d
    τ                           Softmax temperature (Allocation Concentration)                ∈ R>0
                               Table 3. Summary of the principal notation used throughout the paper.



(iii) For each k ∈ {1, 2, . . . , N }, the change between synchronization points is non-zero, i.e., Sk ̸= Sk−1 .
Theorem C.2. (Strict Lead-Lag Implies Positive Second-Order Signature) Let Xt = (Xt1 , Xt2 ) for t ∈ [0, T ] satisfy the
strict lead-lag structure of Definition C.1. Then the second-level signature cross-term
                                                      Z T             Z T
                                                            1    2
                                             A(X) =       Xt dXt −        Xt2 dXt1                                  (22)
                                                        0                   0

is strictly positive. In particular, A(X) > 0.

Proof. Let Xt = (Xt1 , Xt2 )t∈[0,T ] be a path of bounded variation with the strict lead-lag structure of Definition C.1. By this
structure, there exists a partition 0 = t0 < t1 < · · · < t2N = T such that on each interval [t2k−2 , t2k−1 ] only X 1 varies
(while X 2 remains constant), and on the following interval [t2k−1 , t2k ] only X 2 varies (while X 1 is constant). Moreover, at
the synchronization times t2k both coordinates coincide, and no increment is zero.
Recall from Definition C.1 the common values at the synchronization points:

                                   Sk−1 = Xt12k−2 = Xt22k−2          and    Sk = Xt12k = Xt22k .                              (23)

Then Sk ̸= Sk−1 by strictness. Let ∆Sk := Sk − Sk−1 . By construction, on [t2k−2 , t2k−1 ] (the k-th lead step) X 1 varies
from Sk−1 to Sk while X 2 stays at Sk−1 ; on [t2k−1 , t2k ] (the lag step) X 1 remains Sk while X 2 moves from Sk−1 to Sk .
Now we compute the cross-integral:
                                                      Z T                  Z T
                                            A(X) =          Xt1 dXt2 −           Xt2 dXt1 .                                   (24)
                                                        0                   0

                                                                13

===== PAGE 14 =====

                                            Signature-Informed Transformer for Asset Allocation

Using the piecewise structure, we have for each k:
             Z t2k             Z t2k
                      1    2
                   Xt dXt =           Xt1 dXt2                                   (since dXt2 = 0 on [t2k−2 , t2k−1 ])              (25)
                 t2k−2                 t2k−1
                                       h                i
                                   = Sk Xt22k − Xt22k−1                          (since Xt1 = Sk is constant on [t2k−1 , t2k ])    (26)
                                   = Sk ∆Sk .                                                                                      (27)

Similarly,
             Z t2k                 Z t2k−1
                      Xt2 dXt1 =             Xt2 dXt1                         (since dXt1 = 0 on [t2k−1 , t2k ])                   (28)
              t2k−2                 t2k−2
                                    h                  i
                              = Sk−1 Xt12k−1 − Xt12k−2                        (since Xt2 = Sk−1 is constant on [t2k−2 , t2k−1 ])   (29)
                              = Sk−1 ∆Sk .                                                                                         (30)

Summing over k = 1 to N and subtracting:
                                                               N
                                                               X
                                                    A(X) =           (Sk ∆Sk − Sk−1 ∆Sk )                                          (31)
                                                               k=1
                                                               N
                                                               X
                                                           =         (Sk − Sk−1 )∆Sk                                               (32)
                                                               k=1
                                                               N
                                                               X
                                                           =         (∆Sk )2 .                                                     (33)
                                                               k=1

                 PN
Thus A(X) = k=1 (∆Sk )2 . Since Sk ̸= Sk−1 for each k by condition (iii), we have ∆Sk ̸= 0, so each term (∆Sk )2 is
strictly positive. Therefore, the sum A(X) is strictly positive.
Theorem C.3 (Positive directional derivative of attention weight). Assume d ≥ 2, γ > 0, and fix (k, h, j, l). Let the query
vector (qdyn
         k,j )h ∈ R
                   dβ
                      satisfy ∥(qdyn
                                 k,j )h ∥2 > 0. For

                                     (Qk,h K⊤   )j,m                                                  ezj,m
                           zj,m =         √ k,h      + γ⟨(qdyn
                                                           k,j )h , (β i,j,m )h ⟩,            αj,m = Pd          ,
                                            dk                                                        r=1 e
                                                                                                            zj,r


assume 0 < αj,l < 1. Then the directional derivative of αj,l with respect to β i,j,l in the direction (qdyn
                                                                                                        k,j )h equals

                                               (β)                                             2
                                                                                       (qdyn
                                                                                   
                                             D          αj,l = γ αj,l   1 − αj,l         k,j )h 2 > 0.                             (34)
                                               (qdyn
                                                 k,j )h



Proof. For a fixed time slice k and head h, the attention weight αk,h,j→l is the l-th component of the softmax function
applied to the j-th row of the logits matrix. Let zj,m be the logit for query asset j and key asset m ∈ {1, . . . , d}.

                                                             (Qk,h K⊤   )j,m
                                                    zj,m =        √ k,h      + γbk,h,j,m                                           (35)
                                                                    dk

The bias term bk,h,j,l is given by the inner product bk,h,j,l = ⟨(qdyn
                                                                   k,j )h , (β i,j,l )h ⟩. The attention weight is:

                                                                             exp(zj,l )
                                                        αk,h,j→l = Pd                                                              (36)
                                                                          m=1 exp(zj,m )

We wish to compute the directional derivative of αk,h,j→l with respect to the vector (β i,j,l )h in the direction of u = (qdyn
                                                                                                                           k,j )h ,
which is defined as Du αk,h,j→l = ⟨∇(βi,j,l )h αk,h,j→l , u⟩.

                                                                        14

===== PAGE 15 =====

                                        Signature-Informed Transformer for Asset Allocation

First, we find the gradient of αk,h,j→l . By the chain rule,
                                                                 d
                                                                 X   ∂αk,h,j→l
                                        ∇(βi,j,l )h αk,h,j→l =                 ∇(βi,j,l )h zj,m                                (37)
                                                                 m=1
                                                                      ∂zj,m

The relational embedding (β i,j,l )h only appears in the bias term bk,h,j,l , and thus only affects the logit zj,l . For any m ̸= l,
∇(βi,j,l )h zj,m = 0. Therefore, the sum collapses to a single term:

                                                                    ∂αk,h,j→l
                                           ∇(βi,j,l )h αk,h,j→l =             ∇(βi,j,l )h zj,l                                 (38)
                                                                      ∂zj,l
                                              ∂αk,h,j→l
The derivative of the softmax function is       ∂zj,l   = αk,h,j→l (1 − αk,h,j→l ). The gradient of the logit zj,l with respect to
(β i,j,l )h is:
                                                                                                     !
                                                       (Qk,h K⊤  )j,l
                      ∇(βi,j,l )h zj,l = ∇(βi,j,l )h       √ k,h      + γ⟨(qdyn
                                                                            k,j )h , (β i,j,l )h ⟩       = γ(qdyn
                                                                                                              k,j )h           (39)
                                                             dk
Substituting these back, we get the gradient of the attention weight:

                                   ∇(βi,j,l )h αk,h,j→l = γ · αk,h,j→l (1 − αk,h,j→l ) · (qdyn
                                                                                           k,j )h                              (40)

Now, we compute the directional derivative:

                             D(qdyn )h αk,h,j→l = ⟨γ · αk,h,j→l (1 − αk,h,j→l ) · (qdyn        dyn
                                                                                    k,j )h , (qk,j )h ⟩                        (41)
                                  k,j

                                                   = γ · αk,h,j→l (1 − αk,h,j→l ) · ⟨(qdyn        dyn
                                                                                       k,j )h , (qk,j )h ⟩                     (42)
                                                   = γ · αk,h,j→l (1 − αk,h,j→l ) · ∥(qdyn
                                                                                       k,j )h ∥
                                                                                                2
                                                                                                                               (43)

By assumption, γ > 0. The attention weight satisfies 0 < αk,h,j→l < 1 (for any non-degenerate case with at least two
assets), so the term αk,h,j→l (1 − αk,h,j→l ) is strictly positive. By assumption, (qdyn                                   dyn
                                                                                       k,j )h ̸= 0, so its squared norm ∥(qk,j )h ∥
                                                                                                                                   2

is also strictly positive. The product of three strictly positive terms is strictly positive, which concludes the proof.




                                                                    15

===== PAGE 16 =====

                                      Signature-Informed Transformer for Asset Allocation

D. Appendix. Implementation details
To ensure a fair and robust comparison, we perform an extensive hyperparameter search for our proposed SIT model and all
baseline models. For each model, we conduct a comprehensive grid search to identify the optimal set of hyperparameters
from the search space defined in Table 4. The combination of parameters yielding the best performance on the validation set
was selected for the final evaluation on the test set. For all models and experiments, we maintain a consistent set of general
training parameters: the Adam optimizer with a learning rate of 10−3 , a batch size of 64, a dropout rate of 0.1. We train
all models for a maximum of 100 epochs, utilizing an early stopping mechanism with a patience of 10 epochs to prevent
overfitting.

                                            Panel A. General Time Series Forecasting Models
                                            Parameter           Values
                                            D MODELS            32, 64, 128, 256
                                            D FFS               32, 64, 128, 256
                                            E LAYERS LIST       1, 2
                                            N HEADS LIST        2, 4, 8

                                            Panel B. Nonstationary Transformer (NSformer)
                                            Parameter           Values
                                            D MODELS            32, 64, 128, 256
                                            D FFS               32, 64, 128, 256
                                            E LAYERS LIST       1, 2
                                            N HEADS LIST        2, 4, 8
                                            P HIDDEN            64, 128, 256
                                            P LAYER             1,2

                                            Panel C. TimesNet
                                            Parameter           Values
                                            D MODELS            32, 64, 128, 256
                                            D FFS               32, 64, 128, 256
                                            E LAYERS LIST       1, 2
                                            N HEADS LIST        2, 4, 8
                                            TOP K               3, 5, 7

                                            Panel D. RFormer
                                            Parameter           Values
                                            Embedding Dim       8, 16, 32
                                            E LAYERS LIST       1, 2
                                            N HEADS LIST        2, 4, 8
                                            Sig Level           2, 3

                                            Panel E. SIT (Ours)
                                            Parameter           Values
                                            D MODELS            8, 16, 32, 64
                                            D FFS               8, 16, 32, 64
                                            E LAYERS LIST       1, 2
                                            N HEADS LIST        2, 4, 8
                                            Sig Level           2
                                            HIDDEN C            8, 16, 32
Table 4. The hyperparameter search space for the models used in this study. Each panel shows the parameters and their range of values
assigned to a specific model or model group.




                                                                   16

===== PAGE 17 =====

                                   Signature-Informed Transformer for Asset Allocation

E. Appendix. Why we choose CVaR?
1. Model and Definitions
Let S = {1, . . . , N } be a finite state space for an integer N ≥ 2. Let P be a probability measure on S assigning a
                                                          PN
probability ps = P({s}) > 0 to each state s ∈ S, with s=1 ps = 1. We designate state s = 1 as the unique crash state,
with probability p1 = q ∈ (0, 1).
We consider two portfolios, a primary portfolio (PF) and a hedged portfolio (HF), with associated losses given by the random
variables X and Y , respectively. We denote their specific loss values in state s by Xs and Ys . We impose two structural
assumptions on these portfolios:

  1. Crash State Exceptionalism: The loss of the PF portfolio in the crash state is strictly greater than its loss in any
     non-crash state. That is, X1 > Xs for all s ∈ {2, . . . , N }.

  2. Strict State-wise Dominance: The HF portfolio is strictly less risky than the PF portfolio in every state. That is,
     Ys < Xs for all s ∈ S.

For a loss variable Z and a confidence level p ∈ (0, 1), the Value-at-Risk is the p–quantile

                                        VaRp (Z) = inf{z ∈ R | P(Z ≤ z) ≥ p}.                                          (44)

The Conditional Value-at-Risk (CVaR), also known as Expected Shortfall, at level α ∈ (0, 1) averages the upper tail of
mass 1 − α:                              Z 1
                                   1                           n        1                 o
                                                                              E (Z − ν)+ .
                                                                               
                    CVaRα (Z) =              VaRp (Z) dp = min ν +                                               (45)
                                  1−α α                    ν∈R       1−α
We define the risk gap between the two portfolios at level α as

                                            ∆α := CVaRα (X) − CVaRα (Y ).                                              (46)

Theorem E.1 (HF dominates PF in CVaR). Let α ∈ (0, 1) satisfy 1 − α < q (equivalently, α > 1 − q). For any portfolios PF
and HF satisfying the assumptions above, the risk gap is strictly positive and bounded below by the minimum performance
gap:
                                                      ∆α ≥ Lmin ,                                                    (47)
where the minimum performance gap is defined as
                                                                    
                                                 Lmin := min Xs − Ys .                                                 (48)
                                                           s∈S

Since Ys < Xs for all s in the finite set S, it follows that Lmin > 0, confirming that HF strictly dominates PF in terms of
CVaR for this range of α.

Proof. We proceed in three steps. First, we compute CVaRα (X) under the stated tail condition. Second, we upper-bound
CVaRα (Y ). Finally, we combine these results.
Exact value of CVaRα (X) for α > 1 − q. Let FX (z) = P(X ≤ z) be the cumulative distribution function of X. By Crash
State Exceptionalism, X1 is the unique maximum of X. Hence, for any z < X1 ,
                                                                  N
                                                                  X
                                         FX (z) = P(X ≤ z) ≤            ps = 1 − q.                                    (49)
                                                                  s=2

Therefore, for every p ∈ (1 − q, 1], the smallest z with FX (z) ≥ p is z = X1 , i.e., VaRp (X) = X1 . If α > 1 − q
(equivalently, the tail mass 1 − α < q), then
                                                  Z 1                          Z 1
                                             1                            1
                            CVaRα (X) =                 VaRp (X) dp =                X1 dp = X1 .                      (50)
                                            1−α     α                    1−α    α

                                                            17

===== PAGE 18 =====

                                    Signature-Informed Transformer for Asset Allocation

Upper bound for CVaRα (Y ). By definition of Lmin , we have Xs − Ys ≥ Lmin for all s ∈ S, equivalently

                                               Y ≤ X − Lmin        (state-wise).                                          (51)

Two standard properties of CVaR at a fixed level α are:

  1. Monotonicity: If Z1 ≤ Z2 state-wise, then CVaRα (Z1 ) ≤ CVaRα (Z2 ).
  2. Translation Equivariance: For any constant c ∈ R, CVaRα (Z − c) = CVaRα (Z) − c.

Applying these to Y ≤ X − Lmin yields

                         CVaRα (Y ) ≤ CVaRα (X − Lmin ) = CVaRα (X) − Lmin = X1 − Lmin .                                  (52)

So, to get the risk gap, we combine the steps mentioned above.

                            ∆α = CVaRα (X) − CVaRα (Y ) ≥ X1 − (X1 − Lmin ) = Lmin > 0.                                   (53)

This completes the proof.

F. Details of Predict-then-Optimize Baselines
The deep learning baselines evaluated in our experiments operate under a two-stage predict-then-optimize approach. Unlike
SIT, these baselines treat the two tasks as disjoint stages. This section details the mathematical formulation of this process.

Stage 1: Return Prediction via MSE In the first stage, a forecasting model fθ is trained to minimize the statistical
discrepancy between the predicted returns and the ground truth. Let Xt denote the lookback window of historical asset
features at time t, and rt+1 ∈ Rd denote the realized returns at time t + 1. The model parameters θ are optimized using the
Mean Squared Error (MSE) loss function:

                                                              T
                                                          1X
                                             LMSE (θ) =         ∥rt+1 − r̂t+1 ∥22                                         (54)
                                                          T t=1

where r̂t+1 = fθ (Xt ) is the point forecast of the asset returns. The training process focuses solely on maximizing predictive
accuracy (minimizing L2 distance) without considering the downstream portfolio risk metric or the covariance structure
between assets.

Stage 2: Portfolio Optimization via Mean-CVaR In the second stage, the trained forecasting model is frozen. Its output
r̂t+1 is treated as the vector of expected returns to construct the portfolio. To ensure a fair comparison with our proposed
method, we employ a CVaR optimization framework. The solver seeks a portfolio weight vector wt that minimizes the
Conditional Value-at-Risk (CVaR) while satisfying a target return constraint derived from the prediction r̂t+1 .
The optimization problem at time t is formulated as follows:

                                                                   S
                                                         1    X                +
                                      minimize    ζ+              −(w⊤ rs ) − ζ
                                     w∈∆d ,ζ∈R       (1 − α)S s=1
                                                                                                                          (55)
                                     subject to   w⊤ r̂t+1 ≥ µtarget ,
                                                  w∈W

Here, ∆d represents the simplex of valid portfolio weights (e.g., wi = 1, wi ≥ 0 for long-only strategies). The risk term
                                                                 P
CVaRα is approximated using S historical scenarios rs sampled from the immediate past, and ζ represents the Value-at-Risk
(VaR) auxiliary variable.


                                                              18

===== PAGE 19 =====

                                        Signature-Informed Transformer for Asset Allocation

G. Appendix. Additional Experiments
                           Panel A. Asset 30 Universe (S&P100)
                              Model              Sharpe            Sortino            MDD               Wealth
                               CVaR              0.2883             0.3707            0.3499            1.1915
                                EW               0.5268             0.6569            0.3724            1.5648
                               GMV               0.1690             0.2177            0.2853            1.0723
                               HRP               0.4609             0.5711            0.3287            1.4099
                            Autoformer      0.3228 ± 0.0549    0.4500 ± 0.0840   0.3782 ± 0.0062   1.2989 ±0.1028
                              DLinear       0.3929 ± 0.1294    0.5399 ± 0.1758   0.3863 ± 0.0266   1.4235 ± 0.2587
                            FEDformer       0.1594 ± 0.1323    0.2162 ± 0.1790   0.4345 ± 0.0319    1.032 ± 0.2090
                           iTransformer     0.2948 ± 0.0721    0.3853 ± 0.0942   0.4169 ± 0.0118   1.2447 ± 0.1459
                             NSformer       0.2227 ± 0.1535    0.3070 ± 0.2126   0.4422 ± 0.0535   1.1190 ± 0.2650
                             PatchTST       0.2189 ± 0.1446    0.2916 ± 0.1945   0.5003 ± 0.0667   1.1238 ± 0.2287
                             TimesNet       0.2192 ± 0.1520    0.2999 ± 0.2103   0.4434 ± 0.0311   1.1213 ± 0.2853
                             RFormer        0.4631 ± 0.2771    0.5854 ± 0.2094   0.4561 ± 0.0501   1.5566 ± 0.2038
                            SIT (Ours)      0.5496 ± 0.0552    0.6797 ± 0.0792   0.3415 ± 0.0162   1.5678 ± 0.0973
Table 5. Portfolio performance of SIT versus baselines across 30-asset universes. The best, second-best, and third-best results for each
metric are highlighted in red, blue, and bold, respectively. SIT consistently delivers superior risk-adjusted returns.


                    Panel A. Asset 10 Universe (DOW30)
                       Models        Sharpe Ratio (↑)  Sortino Ratio (↑)    Maximum Drawdown (↓)    Final Wealth Factor (↑)
                        CVaR              0.4584            0.5617                  0.3053                  1.4341
                         EW               0.9123            1.1714                  0.3191                  2.4551
                        GMV               1.0394            1.3191                  0.2467                  2.3841
                        HRP               0.8407            1.0332                  0.3104                  2.0583
                     Autoformer      0.6767 ± 0.3150   0.9581 ± 0.4848         0.4655 ± 0.0265         2.2787 ± 1.3004
                       DLinear       0.8223 ± 0.1251   0.9789 ± 0.1692         0.4240 ± 0.0414         2.4523 ± 0.6336
                     FEDformer       0.7664 ± 0.0867   0.8245 ± 0.1460         0.4948 ± 0.0116         2.0578 ± 0.7550
                    iTransformer     0.9458 ± 0.1279   1.1248 ± 0.2274         0.4230 ± 0.0532         2.4016 ± 1.7240
                      NSformer       0.8863 ± 0.2525   0.9630 ± 0.4478         0.4733 ± 0.0825         2.1044 ± 1.1644
                      PatchTST       0.7815 ± 0.1745   0.9712 ± 0.2462         0.4133 ± 0.0224         2.1454 ± 0.8895
                      TimesNet       0.4249 ± 0.2673   0.5876 ± 0.3658         0.6326 ± 0.0967         1.6655 ± 0.6016
                      RFormer        0.8605 ± 0.1936   1.1928 ± 0.2708         0.3615 ± 0.0407         2.1120 ± 0.5219
                     SIT (Ours)      1.0312 ± 0.0671   1.3798 ± 0.1049         0.2766 ± 0.0413         2.8674 ± 0.2263

                    Panel B. Asset 20 Universe (DOW30)
                       Models        Sharpe Ratio (↑)  Sortino Ratio (↑)    Maximum Drawdown (↓)    Final Wealth Factor (↑)
                        CVaR              0.5453            0.6871                  0.3249                  1.5166
                         EW               0.8603            1.0472                  0.3503                  2.2293
                        GMV               0.8618            1.0730                  0.2853                  1.9457
                        HRP               0.7500            0.8917                  0.3253                  1.8443
                     Autoformer      0.5688 ± 0.2224   0.8312 ± 0.3437         0.4642 ± 0.0244         1.8605 ± 0.9118
                       DLinear       0.7969 ± 0.1057   0.9339 ± 0.1475         0.3276 ± 0.0415         2.1966 ± 0.4046
                     FEDformer       0.3341 ± 0.5907   0.5471 ± 0.8805         0.4671 ± 0.0763         1.8039 ± 1.1031
                    iTransformer     0.4668 ± 0.2290   0.6682 ± 0.3666         0.6001 ± 0.0208         1.8563 ± 0.9329
                      NSformer       0.6541 ± 0.4828   0.9751 ± 0.7710         0.5620 ± 0.0778         2.1464 ± 1.0281
                      PatchTST       0.6828 ± 0.1866   0.9499 ± 0.2417         0.5109 ± 0.0395         2.0649 ± 0.4307
                      TimesNet       0.2381 ± 0.2584   0.3428 ± 0.3871         0.4919 ± 0.0511         1.2356 ± 0.5723
                      RFormer        0.7055 ± 0.1568   0.8295 ± 0.1663         0.4514 ± 0.1046         2.0048 ± 0.6198
                     SIT (Ours)      0.8861 ± 0.1243   1.0949 ± 0.1607         0.3151 ± 0.0181         2.2039 ± 0.2983
Table 6. Portfolio performance of SIT versus baselines across 10 and 20-asset universes from DOW30. The best, second-best, and
third-best results for each metric are highlighted in red, blue, and bold, respectively. SIT consistently delivers superior risk-adjusted
returns.




                                                                       19

===== PAGE 20 =====

                                         Signature-Informed Transformer for Asset Allocation




                    Panel A. Asset 50 Universe (CSI300)
                       Models        Sharpe Ratio (↑)   Sortino Ratio (↑)     Maximum Drawdown (↓)   Final Wealth Factor (↑)
                        CVaR              0.8292             1.0038                   0.1220                 1.0971
                         EW               1.1695             1.3671                   0.1263                 1.1413
                        GMV               1.6717             2.1255                   0.0942                 1.1766
                        HRP               1.7428             2.0183                   0.1136                 1.1825
                     Autoformer      0.5834 ± 0.4666    0.5923 ± 0.5446          0.2441 ± 0.0779        0.9079 ± 0.1257
                       DLinear       0.5122 ± 0.3699    0.6819 ± 0.5769          0.2032 ± 0.0664        1.1252 ± 0.1615
                     FEDformer       0.3267 ± 0.7165    0.4185 ± 0.8655          0.2822 ± 0.0371        1.0383 ± 0.2970
                    iTransformer     0.6161 ± 0.1936    0.8566 ± 0.2296          0.2001 ± 0.0234        1.0204 ± 0.1806
                      NSformer       0.3010 ± 0.1859    0.4132 ± 0.2395          0.2889 ± 0.0689        1.0775 ± 0.0704
                      PatchTST       0.2789 ± 0.1646    0.3368 ± 0.2040          0.1913 ± 0.0124        1.0394 ± 0.0442
                      TimesNet       0.8213 ± 0.1636    1.0533 ± 0.1929          0.2855 ± 0.0954        1.1700 ± 0.2386
                      RFormer        0.8867 ± 0.2363    1.0921 ± 0.2451          0.2579 ± 0.0554        1.1665 ± 0.1245
                     SIT (Ours)      1.9373 ± 0.0091    2.3399 ± 0.1711          0.0964 ± 0.0046        1.2804 ± 0.0105

                    Panel B. Asset 100 Universe (CSI300)
                       Models        Sharpe Ratio (↑)    Sortino Ratio (↑)    Maximum Drawdown (↓)   Final Wealth Factor (↑)
                        CVaR              1.5199              2.0863                  0.1155                 1.2905
                         EW               1.1179              1.2660                  0.1302                 1.1252
                        GMV               1.5365              2.0612                  0.1175                 1.2724
                        HRP               1.2424              1.6540                  0.1229                 1.2097
                     Autoformer      0.5681 ± 0.3129     0.6014 ± 0.4024         0.2529 ± 0.0206        0.9725 ± 0.1396
                       DLinear       0.7382 ± 0.4826     0.8309 ± 0.4303         0.2314 ± 0.0778        1.0934 ± 0.3219
                     FEDformer       0.4269 ± 0.4916     0.5356 ± 0.6167         0.2831 ± 0.0344        1.0846 ± 0.1694
                    iTransformer     0.9865 ± 0.2055     1.2495 ± 0.2386         0.2492 ± 0.0741        1.1169 ± 0.3491
                      NSformer       0.5470 ± 0.3975     0.7586 ± 0.5326         0.2175 ± 0.0851        1.1560 ± 0.1387
                      PatchTST       0.4650 ± 0.1313     0.5551 ± 0.1793         0.2547 ± 0.5590        1.0809 ± 0.1104
                      TimesNet       0.7353 ± 0.1357     1.0598 ± 0.1992         0.2997 ± 0.0940        1.1610 ± 0.2039
                      RFormer        1.0267 ± 0.2152     1.2359 ± 0.2599         0.2111 ± 0.0732        1.2321 ± 0.1094
                     SIT (Ours)      1.8772 ± 0.0918     2.3637 ± 0.0936         0.1199 ± 0.0048        1.2777 ± 0.0214
Table 7. Portfolio performance of SIT versus baselines across 10 and 20-asset universes from CSI300. The best, second-best, and
third-best results for each metric are highlighted in red, blue, and bold, respectively. SIT consistently delivers superior risk-adjusted
returns.




                                                                         20

===== PAGE 21 =====

                                      Signature-Informed Transformer for Asset Allocation

H. Appendix. Drawdown with Gamma(γ)




Figure 7. Visual analysis of the dynamic gate γ relative to portfolio drawdown over the test period (2020-2024). The plots display the
drawdown curves for the 40-asset (top) and 50-asset (bottom) universes, where the line color intensity encodes the magnitude of the
learnable scalar γ.




                                                                 21

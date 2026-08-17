===== PAGE 1 =====

      When Do Anomalies Deserve Capital?
    Macro-Regime Memory and Dynamic Cross-Sectional
                   Factor Allocation
                                 Nima Taheri Hosseinkhani

                                         June 17, 2026


                                            Abstract

          This paper studies when characteristic-based return predictors deserve capital. A
      broad anomaly panel is organized into economic families, and a macro-regime memory
      allocator assigns capital across those families under an annual walk-forward protocol.
      The lead allocation rule earns 2.13 percent per month, with a Newey–West t-statistic
      of 9.21 and an annualized Sharpe ratio of 1.51. The same family allocation structure
      improves the full 212-signal hierarchy by 0.0197 monthly information-coefficient points
      relative to static aggregation, with a t-statistic of 6.25. The model’s answer is con-
      centrated: Continuation and Valuation absorb most capital and account for nearly all
      allocation performance, while the other families operate as state-contingent exposures.
      The sharpest mechanism is Liquidity/Limits by market trend. The Liquidity/Limits
      family earns 1.41 percent per month in low-trend states and reverses to -1.79 percent
      in high-trend states, with the low-minus-high premium strongest outside the deepest-
      capacity stocks. The findings show that the economic value of anomalies is not fixed
      characteristic by characteristic; it is state dependent, organized by anomaly family,
      and shaped by macro conditions and arbitrage capacity.

Keywords: Anomaly portfolios; macro regimes; characteristic-based asset pricing; limits to
arbitrage; cross-sectional returns; machine learning benchmarks.
JEL Classification: G11; G12; G14; C58.


1    Introduction
Characteristics forecast the cross section of returns, but investors allocate capital to those
characteristics in macroeconomic states. A value signal, a continuation signal, a profitability
signal, and a liquidity signal enter portfolio choice when inflation, growth, interest rates,
funding conditions, volatility, market trend, and valuation conditions jointly determine the
opportunity cost of capital, the risk of arbitrage, and the set of firms in which mispricing can

                                                1

===== PAGE 2 =====

be absorbed. This paper studies that allocation problem. It evaluates when broad anomaly
families deserve capital, using the full Chen–Zimmermann/OpenAP characteristic panel and
an information-set preserving walk-forward design that begins in 1963.
   The object is deliberately different from the standard single-anomaly exercise. A single-
anomaly paper evaluates whether one firm characteristic earns a premium after portfolio
sorts, factor adjustment, or cross-sectional regressions. A pooled stock-level prediction paper
evaluates whether a high-dimensional model forecasts returns better than competing stock-
level models. Both questions matter, and both have shaped modern empirical asset pricing.
The object here is the allocation value of economic characteristic families. The paper groups
the 212 characteristics into families such as valuation, continuation, profitability and quality,
investment and issuance, safety and downside, liquidity and limits to arbitrage, correction,
and expectations. It then studies whether macro-regime memory reallocates capital across
these families in ways that improve expected-return measurement and portfolio choice.
   The distinction is economically important. The anomaly literature has produced many
predictors, and the high-dimensional prediction literature has shown that a broad charac-
teristic set contains substantial cross-sectional information. Yet a portfolio manager who
believes that many characteristics forecast returns still faces an allocation problem: which
kind of characteristic information should receive capital in the current state? A full stock-
level model can forecast each stock directly, while its fitted values can obscure whether the
economic source of return predictability is valuation, continuation, liquidity, profitability,
investment, safety, expectations, or correction. A family-level allocation model reveals when
a source of characteristic information becomes valuable even when stock-level prediction
remains well captured by a strong pooled ridge benchmark.
   The empirical design uses a strict out-of-sample protocol. The sample starts in 1963.
The first prediction year is 1985, after a 10-year initial training window and a fixed 12-year
validation window. Each subsequent prediction year rolls forward annually. Training infor-
mation expands through time, while the validation window keeps the fixed-length validation
protocol fixed in length. Macro states are constructed from economically grouped macro
variables, with timing aligned to information available at portfolio formation. The result-
ing prediction sample contains 479 monthly out-of-sample observations from January 1985
through November 2024.
   The design makes the timing of learning part of the research object. A family receives
capital in a prediction year because the rule selected before that year assigns it weight under
the macro state observed at the time. The model therefore evaluates the allocation value of
characteristic information as an investor would face it: with past family histories, past macro
states, and a fixed validation protocol. The rolling structure also means that the paper’s
estimates are built from repeated out-of-sample decisions rather than a single full-sample fit.
   The family layer gives the paper economic resolution beyond a pooled prediction exercise.
A pooled predictor can deliver a strong stock-level score, while the score mixes valuation,
continuation, profitability, liquidity, investment, safety, correction, and expectations infor-
mation. The family allocation layer preserves those economic categories and lets the evidence
say which source of information is valuable in each macro environment. This is the sense in
which the paper studies allocation rather than discovery.

                                               2

===== PAGE 3 =====

   This object is economically substantive because capital is scarce across styles. A manager
can hold many stocks, but a style book still allocates risk budget across value, momentum,
quality, investment, safety, liquidity, and expectation-based signals. A high-dimensional
score answers which stocks rank high today. It says less about whether the opportunity
set is currently being driven by delayed correction, trend continuation, strained arbitrage
capital, durable profitability, balance-sheet conservatism, or valuation pressure. The family-
allocation problem is therefore a portfolio-choice problem as much as a forecasting problem.
   The macro dimension is equally central. Macro states summarize the outside option for
capital, the price of risk, the cost of leverage, the supply of arbitrage balance sheet, and
investor willingness to absorb temporary losses. These forces naturally affect the payoff to
characteristic information. Liquidity and limits-to-arbitrage signals should carry different
content when market trend is poor and capital is harder to mobilize. Profitability and
quality signals should carry different content when macro uncertainty raises the value of
durable cash flows. Continuation signals should carry different content when market trends
persist. The design lets these channels compete in a common out-of-sample allocation rule.
   The first result is that macro-regime memory produces large anomaly-family allocation
returns. The mixture-of-experts allocation earns a mean monthly return of 2.13 percent with
a Newey–West t-statistic of 9.21 and an annualized Sharpe ratio of 1.51. The validation
ensemble earns 2.08 percent per month with a t-statistic of 9.09. These magnitudes are
large because the model does more than smooth past family returns. It changes family
weights across macro states, as shown by the family-by-year allocation heatmap, and the
cumulative performance evidence shows that the main macro-regime rules dominate fixed
family aggregation over the out-of-sample period.
   The allocation model concentrates capital in Continuation and Valuation, the two families
with the largest and most persistent macro-conditional premia, and treats the remaining
families as option-like exposures activated when macro states warrant.
   The magnitude is best read as the return to conditioning the characteristic opportunity set
on macro memory. The comparison is against family sleeves built from the same underlying
characteristic information and the same out-of-sample calendar. The model earns allocation
value by changing which economic source of cross-sectional information receives capital, with
no new set of proprietary signals. That distinction matters for asset pricing: the empirical
object is the time-varying price of characteristic information, measured through portfolios
formed from public accounting, price, and macro histories.
   The second result is that the family allocation result survives the full 212-characteristic
layer. Applying the allocation structure to the complete signal panel produces a mean
hierarchical information coefficient of 0.0508 for the mixture-of-experts rule. The incremental
IC relative to static 212-characteristic aggregation is 0.0197 with a t-statistic of 6.25. The
corresponding equal-weight long-short return is 2.40 percent per month, and the factor alpha
is 1.89 percent per month with a t-statistic of 7.63. This evidence establishes the result as
broad-panel evidence. The empirical object is broad characteristic information organized
into economic families.
  The full-panel layer is the key difference between a selected-style timing exercise and a


                                              3

===== PAGE 4 =====

broad cross-sectional asset-pricing result. The allocation weights are learned at the family
level, but the performance test returns to the complete signal set. Each family weight affects
a collection of underlying characteristics, so the test evaluates whether a state-dependent
family structure improves the use of a large anomaly panel. The positive incremental IC
and large factor alpha show that the state-dependent family map remains valuable after the
paper restores the full characteristic universe.
   The third result clarifies the relation between family-level allocation and stock-level pre-
diction. A pooled all-212 ridge is a demanding benchmark, with a mean monthly IC of
0.0725 and an IC t-statistic of 15.93. The best macro-residual stock-level model has a
mean IC of 0.0727, producing an incremental IC of 0.0002 relative to pooled ridge. This
benchmark result is central to the interpretation. It separates stock-level prediction from
family-level allocation. State-dependent allocation across anomaly families supplies the con-
tribution; machine-learning and high-dimensional models provide benchmark comparisons
for interpreting the family-allocation evidence. The evidence is evaluated against a hard
all-characteristic stock-level benchmark.
   The strongest economic mechanism is the Liquidity/Limits family across market-trend
states. For that family, the high-trend minus low-trend return spread is -3.13 percent per
month in the full universe, with a t-statistic of -7.41. Because the table reports high minus
low, the negative sign means that Liquidity/Limits payoffs are stronger in low-trend states.
The effect remains large outside microcaps: the outside-microcap high-minus-low spread is
-1.71 percent per month with a t-statistic of -4.58, and the middle-cap spread is -1.42 percent
per month with a t-statistic of -3.67. The pattern attenuates in the largest stocks and mega-
cap names. That attenuation is part of the economics. A limits-to-arbitrage mechanism
should be strongest where arbitrage capital is constrained and where capacity is less deep.
   This mechanism gives the paper a finance-theoretic spine. Liquidity/limits signals identify
firms whose prices are more difficult to arbitrage, and trend states proxy for the condition of
the market environment in which arbitrageurs deploy capital. Low-trend states are precisely
the periods in which financing frictions, redemption risk, risk-management constraints, and
balance-sheet costs can make arbitrage capital less elastic. The evidence therefore links a
cross-sectional family of characteristics to a macro state that changes the economic value of
exploiting that family.
   The capacity pattern is equally important. A friction-based mechanism should appear
with force in regions where trading frictions and arbitrage constraints remain meaningful,
while the deepest-capacity mega-cap region should absorb such pressure more easily. The
results follow that ordering: strong in the full universe, strong outside microcaps, strong in
the middle-cap region, and attenuated near the top of the market-cap distribution. This
sequence turns the mechanism from a single cell into an economically ordered frontier.
   The paper makes three contributions. First, it moves the anomaly literature from predic-
tor discovery to capital allocation. The central empirical object is when an economic family
of characteristics deserves capital relative to other families. This shift matters because in-
vestors allocate risk budgets across styles and economic sources of return predictability.
  Second, the paper brings macro conditioning into the cross section through the economic


                                              4

===== PAGE 5 =====

content of characteristics. Macro states determine which kind of cross-sectional information
receives capital. This produces a state-dependent organization of expected-return infor-
mation: Continuation and Valuation carry the dominant allocation share, while Liquid-
ity/Limits becomes valuable precisely in the states where arbitrage capacity is most con-
strained.
   Third, the paper links dynamic anomaly allocation to a capacity-shaped limits-to-
arbitrage mechanism. The Liquidity/Limits by trend premium is strong in the full
universe, remains visible outside microcaps and in middle-cap regions, and attenuates in
the largest stocks. This ordered capacity gradient gives the mechanism economic structure.
Macro-regime memory identifies when a constrained family of characteristics earns larger
expected returns and where that compensation is most likely to be absorbed.
   The resulting contribution is a statement about the organization of expected-return in-
formation. Characteristic signals have economic types, macro states change the payoff to
those types, and portfolio choice requires a rule for moving capital across them. The paper
shows that this rule can be estimated out of sample in a full-characteristic panel, and that
the strongest mechanism aligns with the economics of limits to arbitrage.
   The remainder of the paper develops this argument. Section 2 provides the economic
motivation. Section 3 positions the paper in the literature. Section 4 describes the data,
timing, and construction. Section 5 explains the macro-regime memory method. Section 6
reports the main allocation and 212-signal evidence. Section 7 studies the liquidity/limits
mechanism and capacity frontier. Section 8 reports state-specificity, placebo, and model-
benchmark evidence. Section 9 concludes. The main tables and figures are placed after
the references. The Internet Appendix reports construction detail and expanded empirical
evidence in a separate document.
   The empirical story is intentionally layered. The first layer establishes that macro-regime
memory allocates across families in a way that earns large returns. The second layer es-
tablishes that this allocation survives the full 212-characteristic signal panel. The third
layer shows that a hard all-characteristic ridge remains a powerful stock-level benchmark.
The fourth layer identifies liquidity/limits × trend as the sharp mechanism. The fifth layer
shows that the mechanism is strongest where limits to arbitrage are most economically plau-
sible. Each layer answers a different interpretation challenge while preserving the central
interpretation.


2     Economic Motivation
The economic premise is that anomaly-family payoffs are state dependent. A characteristic is
a cross-sectional sorting variable, but its payoff is determined by the interaction between firm-
level information and the state of the economy. Valuation characteristics reflect discount-
rate and cash-flow expectations. Continuation characteristics reflect trend persistence and
investor underreaction. Profitability and quality characteristics reflect the durability of cash
flows and the value of resilient firms. Investment and issuance characteristics reflect financ-
ing conditions and capital allocation discipline. Safety and downside characteristics reflect

                                               5

===== PAGE 6 =====

demand for protection during stress. Liquidity and limits-to-arbitrage characteristics reflect
the difficulty of absorbing mispricing when arbitrage capital is constrained.
   These families have different state exposures. In high-growth, low-stress states, capital can
be abundant, risk appetite can be high, and arbitrageurs can absorb mispricing more easily.
In low-trend or stressed states, arbitrage capital can become scarce, financing constraints
can bind, and liquidity-demanding trades can move prices. A signal that captures limits
to arbitrage should therefore have different payoff content across market-trend states. The
same logic applies to valuation when discount-rate conditions change, continuation when
trend persistence changes, profitability when macro uncertainty raises the value of durable
cash flows, and safety when downside protection becomes more valuable.
   Family-level allocation is the natural level at which to study this state dependence. Indi-
vidual characteristics are numerous and often highly correlated. Stock-level predictors can
aggregate them efficiently, but the aggregation can obscure the economic source of the fore-
cast. Families provide a middle layer: broad enough to avoid making the paper about a single
historical anomaly, but structured enough to preserve economic interpretation. This middle
layer lets the paper study whether macro states reprice types of characteristic information.
   The family layer also addresses a practical portfolio-choice problem. Asset managers
rarely allocate capital to hundreds of raw variables one by one. They allocate to investment
styles, sleeves, and mandates that summarize economic beliefs about returns. A portfolio
can tilt toward value, quality, momentum, safety, liquidity, or expectations-based informa-
tion, and each tilt has different drawdown, crowding, turnover, and capacity properties.
The empirical design translates the 212-characteristic panel into this economically familiar
capital-allocation language while retaining the breadth of the original data.
   A state-dependent view is natural because the opportunity cost of capital varies through
time. When funding is abundant, arbitrage capital can absorb mispricing more readily
and the payoff to limits-related signals can compress. When trend is poor and capital is
scarce, the same limits-related signals can become more valuable because investors require
compensation for bearing positions that are difficult to finance or unwind. Similar logic
applies to valuation, continuation, and quality. Macro-regime memory estimates these state-
contingent payoffs directly from historical family outcomes.
   The families have distinct economic interpretations. Valuation signals identify firms whose
prices look low relative to fundamentals, so their payoff can depend on discount rates, mar-
ket sentiment, and the willingness of investors to wait for correction. Continuation signals
identify persistence and delayed reaction, so their payoff can depend on trend strength and
investor extrapolation. Profitability and quality signals identify durable operating perfor-
mance, which becomes especially valuable when uncertainty raises the premium on cash-flow
resilience. Investment and issuance signals identify firms whose financing and capital allo-
cation decisions reveal information about expected returns. Safety and downside signals
capture protection and demand for defensive characteristics. Expectations signals collect
forecast-related information. Liquidity/limits signals identify firms where trading frictions,
arbitrage constraints, and price pressure are central.
  This economic heterogeneity is exactly why the families should react differently to macro


                                               6

===== PAGE 7 =====

states. A single aggregate allocation to the entire characteristic panel treats all types of
expected-return information as if their state dependence were the same. The family de-
sign lets valuation, continuation, quality, investment, safety, expectations, correction, and
liquidity/limits respond differently. The paper’s core empirical question is whether those
differences are strong enough to matter for realized returns, cross-sectional ranking, and
portfolio alphas.
   The limits-to-arbitrage channel provides the clearest mechanism. If arbitrage is risky
and capital intensive, as in Shleifer and Vishny (1997) and Pontiff (2006), then expected
returns tied to liquidity and arbitrage constraints should vary with states that affect funding,
trend, volatility, and capital supply. Low-trend market states are natural candidates. They
often coincide with lower risk appetite, reduced balance-sheet capacity, and greater difficulty
absorbing mispriced securities. In such states, liquidity/limits characteristics can command
larger payoffs because they identify firms where trading frictions and arbitrage constraints
matter most.
   Capacity provides a further implication. If the mechanism is limits to arbitrage, the state
dependence should be strongest where limits are economically plausible and more attenuated
where arbitrage capacity is deepest. The paper therefore evaluates the full universe, microcap
and outside-microcap samples, middle-cap regions, top-half and top-third regions, large top-
20 percent stocks, and mega-cap top-10 percent stocks. The pattern is expected to be
strongest outside the largest names and to attenuate as one moves toward the deepest-
capacity part of the market. This is a central prediction of the mechanism.
   The macro-regime memory design operationalizes the motivation. The model uses his-
torical analogs and fixed-length validation protocol to decide which anomaly-family sleeves
deserve capital in each prediction year. The design allows the identity of valuable families to
change across states. It estimates state-contingent allocation value under a common infor-
mation set. A family that earns little average payoff unconditionally can still deserve capital
in a subset of macro states; a family that looks strong on average can receive less capital
when the macro state is unfavorable.
   The key empirical comparison is therefore conditional versus unconditional use of the
same information. Fixed family aggregation treats the value of each economic source as
stable. Macro-regime memory lets the value of the source vary with the state of the econ-
omy. The design evaluates whether state dependence adds allocation value after respecting
the information set, the prediction-year calendar, and the validation window. A strong an-
swer to that question is informative about expected returns because it says that the same
characteristic family carries different compensation in different macro environments.
   The paper uses stock-level all-212 ridge as a demanding benchmark because family-level
allocation and direct stock-level prediction are distinct empirical objects. A strong stock-
level ridge can absorb much of the cross-sectional signal. The family-allocation contribu-
tion identifies when economic sources of characteristic information deserve capital. The
benchmark therefore strengthens the interpretation by separating the paper from a generic
model-complexity comparison.
  The benchmark layer also gives the paper a high bar. A pooled ridge forecast built from


                                               7

===== PAGE 8 =====

all 212 characteristics is a powerful stock-level object. It can combine many related signals,
shrink noisy predictors, and exploit the breadth of the panel. Showing that macro-regime
memory adds its strongest value at the family-allocation layer, while the pooled ridge remains
the stock-level anchor, gives the paper a cleaner interpretation: state dependence changes the
economic composition of characteristic capital, while full-panel ridge summarizes stock-level
ranking information.
   This motivation also fixes the contribution on expected returns, information, risk, lim-
its to arbitrage, model reliability, anomaly decay, and portfolio choice. The paper studies
how macro-regime memory changes the value of characteristic information. Capacity evi-
dence shows where the mechanism is economically strongest and gives the limits-to-arbitrage
interpretation its cross-sectional shape.
   The anomaly-decay interpretation is especially useful. A characteristic family can appear
to decay in an unconditional average while still carrying strong payoffs in the right macro
states. Conversely, a family with a strong unconditional history can become less valuable
when the macro state turns against the economic mechanism behind it. Macro-regime mem-
ory turns decay from a single average into a conditional allocation question. The paper
therefore links the anomaly literature’s focus on persistence to a portfolio-choice rule that
learns when each family remains valuable.


3     Related Literature
The first related literature studies characteristic-based expected returns. The classic evidence
on size, value, and momentum established that firm characteristics forecast returns and raised
the question of whether those patterns reflect risk, mispricing, or limits to arbitrage (Fama
and French, 1993; Jegadeesh and Titman, 1993; Lakonishok, Shleifer, and Vishny, 1994;
Daniel and Titman, 1997). Later work expanded the set of characteristics and organized
the anomaly zoo into a large empirical object. Harvey, Liu, and Zhu (2016) emphasize the
multiple-testing challenge created by the proliferation of factors, while McLean and Pontiff
(2016) show that published predictability often decays after discovery. Green, Hand, and
Zhang (2017) study which characteristics provide independent information after microcap
and data-snooping controls, and Chen and Zimmermann (2022) provide a large open-source
cross-sectional asset-pricing dataset. This paper builds directly on that broad-characteristic
view but changes the object from discovery to allocation across economic families.
   That shift is important because the anomaly zoo creates both a discovery problem and
an allocation problem. Discovery evaluates which characteristics contain reliable expected-
return information. Allocation determines how much capital should be assigned to different
types of reliable information as market conditions change. The second question becomes
increasingly important as the characteristic set grows. A large panel can contain many
signals that overlap, decay, revive, or become valuable in particular states. The family
structure used here treats the zoo as an organized menu of economic sources rather than a
flat list of predictors.
    The second literature studies conditional asset pricing and time-varying expected re-

                                               8

===== PAGE 9 =====

turns. Aggregate expected returns vary with state variables, consumption-wealth ratios,
term spreads, valuation ratios, and combinations of macro predictors (Lettau and Ludvig-
son, 2001; Cochrane, 2011; Rapach, Strauss, and Zhou, 2010). That work motivates the
use of macro states, while this paper applies the idea to the cross-sectional allocation value
of anomaly families. The comparison separates aggregate market prediction from cross-
sectional family allocation: macro states can change which type of firm-level characteristic
information deserves capital.
   This extension is economically meaningful because macro predictors can affect cross-
sectional opportunities even when the aggregate market premium is hard to forecast. A state
variable can change the relative attractiveness of liquidity, valuation, continuation, and safety
information without delivering a standalone market-timing strategy. The paper therefore
uses macro states as conditional information for cross-sectional allocation. That design
places macro variables inside the characteristic-allocation problem rather than treating them
as separate market-level forecasts.
   The third literature studies limits to arbitrage. Shleifer and Vishny (1997) emphasize
that arbitrage requires capital and is risky. Pontiff (2006) studies costly arbitrage and
idiosyncratic risk. Stambaugh, Yu, and Yuan (2015) show that arbitrage asymmetry can
shape return patterns associated with mispricing. This paper contributes by using macro-
trend states to identify when liquidity/limits characteristics become especially valuable and
by showing that the effect is strongest outside the largest names. The capacity frontier
is central because it aligns the cross-sectional scope of the result with the economics of
constrained arbitrage.
   The limits-to-arbitrage evidence also gives the paper a mechanism that is broader than
style timing. Liquidity/limits characteristics have economic content because they describe
securities where arbitrage can be costly, slow, capital intensive, or exposed to interim loss.
Market-trend states describe the environment in which arbitrage capital is supplied. The
interaction between the two produces a direct prediction: limits-related characteristics should
command larger payoffs when market states make arbitrage harder, with the effect strongest
in regions where capacity remains economically constrained.
   The fourth literature studies high-dimensional and machine-learning return prediction.
Kelly, Pruitt, and Su (2019) use characteristics to instrument dynamic factor loadings. Gu,
Kelly, and Xiu (2020) show that machine-learning methods can improve empirical asset-
pricing forecasts by capturing nonlinear interactions. Freyberger, Neuhierl, and Weber
(2020) study characteristic effects nonparametrically. This paper uses machine-learning
benchmarks and all-characteristic ridge discipline, while the contribution is state-dependent
allocation value across interpretable anomaly families.
   The benchmark evidence is deliberately demanding. A pooled all-characteristic ridge can
summarize a large amount of stock-level information, and compute-heavy alternatives test
whether flexible prediction alone explains the findings. The results assign these models an
important role: they anchor the stock-level comparison while preserving the separate family-
allocation result. The paper therefore connects the machine-learning asset-pricing literature
to an interpretable portfolio-choice object.


                                               9

===== PAGE 10 =====

   The fifth literature studies factor organization and anomaly decay. A large set of charac-
teristics can be represented as many individual signals, as latent factors, or as economically
grouped families. The family representation used here is designed for portfolio choice. It
keeps the broad panel, but it gives the reader an interpretable allocation object: valuation,
continuation, profitability, investment, safety, liquidity/limits, correction, and expectations.
That organization allows the paper to study how macro states change the value of different
types of characteristic information.
   The paper therefore sits between two common approaches. It is broader than a single-
anomaly paper because it uses the full 212-characteristic panel and aggregates signals into
families. It is more interpretable than a pure stock-level prediction comparison because
it studies family weights, macro states, mechanism cells, and capacity scope. The pooled
all-212 ridge benchmark is important precisely because it is strong. It anchors stock-level
prediction comparisons while leaving room for a separate family-level allocation contribution.
   The literature also clarifies the paper’s interpretation boundary. The evidence is an
information-set preserving out-of-sample asset-pricing design that shows macro-regime mem-
ory reallocating characteristic information in economically meaningful ways, with liquid-
ity/limits × trend as the strongest channel. The mechanism language is evidence-bound and
confident: the pattern aligns with limits to arbitrage because it is strongest in low-trend
states and attenuates where market capacity is deepest.


4    Data and Timing
The empirical analysis uses the Chen–Zimmermann/OpenAP cross-sectional asset-pricing
panel. The panel contains 212 characteristics after applying the project construction used
in the empirical package. The unit of observation is the stock-month. Characteristics are
oriented so that higher values correspond to higher expected returns under the documented
signal direction, and each signal is assigned to one of eight economic families. The family
mapping gives the paper a stable economic layer between individual characteristics and
stock-level forecasts.
   The paper uses the full 212-characteristic Chen–Zimmermann panel as the signal input
set. Internet Appendix Table IA.34 reports the publication-year coverage of the signals,
and Figure IA.11 plots the number of signals published before each prediction year. The
contribution of the paper is not the discovery or validation of the individual anomalies. It is
the demonstration that macro-regime conditioning generates incremental predictive power
over static aggregation of a given signal set. In the full 212-signal hierarchy, the mixture-
of-experts rule improves the monthly information coefficient by 0.0197 relative to the static
212-signal aggregate, with a t-statistic of 6.25. That estimate measures the value of dynamic
allocation across economic signal families.
  The eight families are valuation, continuation, correction, profitability and quality, invest-
ment and issuance, safety and downside, liquidity and limits to arbitrage, and expectations.
Valuation contains 36 signals, continuation 27, correction 4, profitability/quality 27, invest-
ment/issuance 46, safety/downside 26, liquidity/limits 21, and expectations 25. The families

                                              10

===== PAGE 11 =====

are intentionally broad. They are designed to summarize the economic content of many pre-
dictors while preserving enough structure for state-dependent allocation.
   The family mapping is fixed before the allocation tests. This matters because the alloca-
tion rule is allowed to move capital across economic sleeves, while the definition of the sleeves
remains stable. The mapping uses the economic content of the characteristic rather than
realized performance in the prediction sample. That separation preserves the interpretation
of a family weight. A high liquidity/limits weight means that the model is assigning capital
to signals tied to trading frictions and arbitrage constraints, rather than to an ex post cluster
of successful variables.
   The sample begins in 1963. The first prediction year is 1985. The first prediction year uses
1963–1972 as the training window and 1973–1984 as the validation window. Thereafter, the
prediction year rolls forward annually. The training window expands; the validation window
remains fixed at 12 years. This design produces 479 monthly out-of-sample prediction months
through November 2024. The fixed validation length gives the allocation rules a stable fixed-
length validation protocol while allowing the training set to incorporate more historical
observations through time.
   The expanding training window and fixed validation window play different roles. The
expanding training window gives the model more historical experience as the sample evolves.
The fixed validation window keeps the selection criterion comparable across prediction years
and avoids letting the validation period become dominated by distant early decades. This
design mirrors the information problem faced by an investor who learns from a growing
history while still selecting models on a recent, disciplined validation record.
   Macro variables are grouped into eight blocks: inflation, growth, rates, credit, liquidity,
risk, valuation, and trend. The empirical package contains 23 macro series. Inflation, growth,
and rates blocks capture real activity, price pressure, and discount-rate conditions. Credit,
liquidity, and risk blocks capture financing and stress conditions. Valuation and trend blocks
capture market-state information. Each macro block is used to form state histories that enter
the regime-memory allocation rules.
   Of the 23 macro conditioning variables, eleven are market prices, rates, spreads, or direct
market states: VIX, the federal funds rate, Treasury yields, credit spreads, the S&P 500 level,
market returns, market trend, and market drawdown. Four additional variables are panel-
derived cross-sectional market states, including volatility, dispersion, aggregate valuation,
and aggregate liquidity. The remaining variables are real-activity and inflation measures
sourced with conservative vintage discipline. Internet Appendix Table IA.32 reports the full
classification and separates economic content from source treatment.
   The macro blocks are designed to be economically interpretable rather than mechanically
exhaustive. Inflation, growth, and rates summarize the discount-rate and cash-flow environ-
ment. Credit, liquidity, and risk summarize the availability and cost of risk-bearing capacity.
Valuation and trend summarize the market state in which characteristic-based strategies are
deployed. This organization lets the paper evaluate whether different macro forces matter
for different anomaly families, and it keeps the mechanism evidence readable.
  Information timing design is central. The portfolio formed for a prediction month uses


                                               11

===== PAGE 12 =====

characteristics, returns, and macro-state information available before the prediction-period
return is realized. The macro timing tables document the vintage or conservative timing
construction. The design uses annual prediction windows, which keeps model selection out-
side the realized prediction period. The tables in the appendix document the walk-forward
splits, macro-state definitions, signal-family mapping, and macro timing checks.
    The main dependent variables are family-sleeve returns, family-sleeve information coef-
ficients, hierarchical 212-signal information coefficients, stock-level information coefficients,
Fama–MacBeth slopes, long-short portfolio returns, and factor-adjusted alphas. Allocation
evidence is evaluated using monthly time-series inference. Stock-level prediction evidence is
evaluated through cross-sectional ICs and Fama–MacBeth regressions. Portfolio evidence is
evaluated with equal-weight and value-weight long-short returns and factor-adjusted alphas
using the five Fama–French factors plus momentum.
   The empirical objects are deliberately redundant across measurement approaches. Family-
sleeve returns measure realized allocation payoffs. ICs measure cross-sectional ranking abil-
ity. Fama–MacBeth slopes connect the signal layer to monthly cross-sectional return regres-
sions. Long-short returns translate ranking ability into portfolio spreads. Factor-adjusted
alphas measure whether the portfolio evidence survives standard factor controls. This struc-
ture gives the reader several ways to see the same economic pattern.
   The design separates three layers. The first layer is family allocation: how much capital
each broad anomaly family receives in a macro state. The second layer is the hierarchical
212-signal layer: how family allocation weights affect the full signal panel. The third layer
is the stock-level benchmark layer: how macro-residual stock-level models compare with a
pooled all-212 ridge. Keeping these layers separate is essential for interpretation.
   The separation also prevents a common source of confusion in high-dimensional asset-
pricing work. A strong stock-level model can rank stocks well while revealing little about
which economic family drives the opportunity set. A family-level allocation model can
explain the economic composition of expected-return information while leaving stock-level
ranking to a separate benchmark. The paper uses both objects and assigns each one a clear
role.


5     Macro-Regime Memory and Allocation Method
Macro-regime memory estimates how the payoff to an anomaly family varies across macro
states. For each prediction date, the model observes historical family returns, family ICs,
and macro-state histories. It then assigns capital across the family sleeves using rules that
are selected under the walk-forward validation design. The allocation rules are nonnegative
and sum to one across families. This keeps the family allocation layer interpretable as capital
shares rather than unrestricted regression coefficients.
   The main allocation rule is a mixture-of-experts design. The rule combines state-
dependent family information and validation performance to determine which families
receive capital. A validation ensemble provides a second leading rule that averages strong


                                               12

===== PAGE 13 =====

validated specifications. Macro ridge, macro analog, attention memory, Bayesian dynamic,
and other rules provide comparison points. Fixed equal-weight family allocation, trailing
Sharpe, and factor momentum provide non-macro or simpler timing benchmarks.
   The mixture-of-experts design is useful because it can represent different state-contingent
specialists. A specialist can be effective when the current macro environment resembles
past states in which a family carried high expected-return information. The validation layer
then determines which specialists earn capital in the prediction year. The resulting weights
are interpretable: they are capital shares across economic anomaly families, conditioned on
macro memory and historical performance under the walk-forward design.
   The allocation weights are constrained to be nonnegative and to sum to one. This restric-
tion is important for interpretation. A negative unrestricted coefficient in a timing regression
can be difficult to translate into a style allocation. A nonnegative capital share has a direct
portfolio meaning: the rule increases or decreases exposure to an economic family, while
total family capital remains fully allocated. Figure 2 and Table 4 show an actual allocation
map across characteristic families rather than a collection of regression slopes.
   The validation window creates a repeated model-selection contest. In each prediction year,
candidate allocation rules are evaluated on the prior validation window and then carried into
the next out-of-sample year. The same procedure repeats as the training history expands.
This design gives the model enough flexibility to learn state-dependent family payoffs, while
forcing every selected rule to earn its place before the prediction returns arrive. The resulting
performance series is a sequence of real-time allocation decisions.
   The method treats anomaly families as economic sleeves. Each sleeve has its own history of
returns and ICs. Macro-regime memory uses the similarity between current macro states and
prior macro states to identify when a sleeve has historically carried higher expected-return
information. The rule therefore gives capital to families whose state-conditioned histories
are favorable under the current information set.
   Validation matters because state-conditioned allocation is flexible. The empirical design
selects the allocation rule before the prediction year, using an expanding training window
and a fixed validation window. The validation structure is the reason the same design can
compare mixture-of-experts, validation ensemble, macro ridge, factor momentum, trailing
Sharpe, and equal-weight allocation on a common prediction sample.
   The hierarchical 212-signal layer converts family allocation into full-panel expected-return
information. Within each family, the underlying characteristics remain part of the signal
panel. The family weights determine how much capital is allocated to each type of charac-
teristic information. This layer answers whether macro-regime memory still matters when
all 212 signals are used, rather than when the paper studies a small manually selected set of
family portfolios.
   The hierarchical layer is also the bridge from economic interpretation to breadth. The
family weights give economic meaning, and the 212 underlying characteristics give empirical
scope. A positive result in this layer says that state-dependent family allocation improves
the organization of a large characteristic panel, extending beyond the return of a stylized
set of eight sleeves. The hierarchical IC and long-short alpha are central because they


                                               13

===== PAGE 14 =====

show that state-dependent family allocation remains valuable when mapped back to the full
characteristic universe.
   The stock-level benchmark layer uses a pooled all-212 ridge as the demanding benchmark.
The pooled ridge directly forecasts stock-level returns from the complete characteristic panel.
Macro-residual models add state-dependent residual information after this benchmark. If
the macro-residual layer adds little IC relative to pooled ridge, that result disciplines the
interpretation. It says that the all-characteristic stock-level benchmark is strong and that
the paper’s contribution is the interpretable family allocation layer.
   This benchmark structure makes the empirical interpretation sharper. The paper gives
the stock-level model access to the full characteristic panel and allows shrinkage to combine
signals efficiently. The family-allocation result must then earn its place through a differ-
ent channel: explaining which type of characteristic information deserves capital under the
current macro state. The pooled ridge is therefore an anchor for stock-level ranking and a
complement to the central mechanism.
   The method is therefore designed around separation. Family allocation evaluates the
economic timing of anomaly families. The hierarchical layer evaluates whether the timing
survives the complete characteristic panel. The stock-level benchmark evaluates whether
the result is simply a high-dimensional prediction race. The mechanism tests evaluate which
family-state cell carries the economic content. The capacity tests evaluate where that mech-
anism is strongest in the cross section.


6    Main Anomaly-Family Allocation Results
Table 1 defines the empirical objects and timing. The allocation layer uses eight economi-
cally motivated families covering all 212 signals. The prediction design begins in 1985 after
the initial training and validation windows. The same timing structure is used for all main
allocation, hierarchy, benchmark, mechanism, and capacity tests. Table 1 defines the empir-
ical objects and timing design, and Figure 1 summarizes the economic architecture: signals
are mapped to families, macro-state memory allocates across families, the full 212 ridge
anchors stock-level prediction, and the liquidity/limits capacity frontier identifies the main
mechanism.
   Table 2 reports the macro blocks and allocation designs. The macro information set covers
inflation, growth, rates, credit, liquidity, risk, valuation, and trend blocks. The leading
allocation designs all use the same prediction sample, which permits direct comparison.
The mixture-of-experts and validation-ensemble rules are the main allocation specifications
because they combine state dependence with fixed-length validation protocol and deliver the
strongest out-of-sample performance.
   The table also clarifies that the main comparison is within a common empirical architec-
ture. Each allocation rule observes the same family histories and macro blocks, and each is
evaluated on the same out-of-sample months. The differences across rows therefore reflect
how the rule uses macro memory, validation information, and family histories. This common


                                              14

===== PAGE 15 =====

structure is what allows the mixture-of-experts and validation-ensemble evidence to be read
as allocation evidence rather than sample-composition evidence.
   Table 3 reports the family-allocation returns. The mixture-of-experts rule earns a mean
monthly return of 0.0213 with a Newey–West t-statistic of 9.21 and an annualized Sharpe
ratio of 1.51. The validation ensemble earns 0.0208 per month with a t-statistic of 9.09.
Bayesian dynamic, ensemble, macro ridge, and factor momentum rules also produce eco-
nomically large returns. These results show that the allocation value of anomaly families is
state dependent.
   The economic magnitude is large for a family-allocation problem. The rules allocate
among broad characteristic sleeves, so their returns measure the value of selecting the right
economic source of expected-return information in each macro state. Equal-weight family
aggregation is a natural baseline because it uses the same families without state condition-
ing. The large spread between macro-regime rules and fixed aggregation shows that state
dependence is economically important.
   The validation ensemble is important because it demonstrates that the result extends
across related validated specifications. It pools validated allocation structures and still
produces a mean monthly return above two percent with a t-statistic above nine. The
mixture-of-experts rule is the lead specification because it gives the most interpretable state-
dependent weighting structure, while the ensemble shows that the macro-regime allocation
result is robust across nearby model choices.
   Figure 2 and Table 4 show the time variation in family weights. Figure 2 reports an-
nual average mixture-of-experts weights by family, and Table 4 reports average weights,
dispersion, distributional percentiles, and correlations with trend and valuation states. Con-
tinuation receives high capital shares in many years, and the figure also shows meaningful
reallocation toward valuation, profitability/quality, liquidity/limits, and other families in
specific periods. The visual evidence is important because it shows a time-varying charac-
teristic combination. Macro-regime memory changes the economic source of expected-return
information over time.
   Figure 2 and Table 4 are central to the paper’s interpretation. It shows that the model is
learning an allocation surface rather than a fixed ranking of families. Some periods emphasize
continuation, others raise valuation, quality, expectations, or liquidity/limits exposure. The
model therefore behaves like a state-dependent allocator across economic sources of return
predictability. That is the portfolio-choice object the paper brings to the anomaly panel.
   The time variation also helps explain why full-sample averages can miss the economics.
A family can receive low capital in states where its historical payoff is poor and high capital
in states where its payoff is strong. Averaging across those states can dilute the source of
return predictability. Macro-regime memory attempts to recover that conditional structure
and express it as capital weights.
   Table 15 reports family-group ablations. Continuation and Valuation account for the dom-
inant share of allocated capital and return. Keeping only those two families preserves 78.18
percent of the original average mixture-of-experts weight and earns 2.08 percent per month,
compared with 2.13 percent for the full eight-family model. Adding Profitability raises the


                                              15

===== PAGE 16 =====

retained weight to 92.58 percent and earns 2.12 percent per month. This concentration
is the model’s empirical answer to the paper’s central question: when anomalies deserve
capital, the dominant channels are continuation and valuation, conditioned on the macro
regime. The remaining families serve as mechanism channels and option-like exposures that
the model can use when state histories warrant.
   Table 3 and Figure 3 translate the allocation evidence into monthly returns, long-short
portfolio spreads, factor-adjusted alphas, and cumulative out-of-sample performance. The
mixture-of-experts and validation-ensemble rules deliver large growth of one dollar relative
to fixed equal-weight aggregation and simpler timing alternatives. The log scale makes the
long-run magnitude visible while preserving drawdowns. This evidence complements Table 3:
the statistical inference is strong, and the cumulative path shows that the result is distributed
across the sample.
   The cumulative plot is also a useful check on the economics of the result. A state-
dependent allocation rule that earned its return from a brief isolated episode would be
less compelling as an asset-pricing object. Figure 3 shows sustained divergence over the
out-of-sample period. The path still contains drawdowns, as any expected-return strategy
should, but the long-run ordering is consistent with Table 3: macro-regime memory generates
persistent allocation value.


7     Full 212-Characteristic and Stock-Level Benchmark
      Evidence
Table 5 reports the full 212-characteristic hierarchical layer. The mixture-of-experts rule
has a mean hierarchical IC of 0.0508 and an incremental IC of 0.0197 relative to static 212
aggregation, with an incremental t-statistic of 6.25. It also generates an equal-weight long-
short return of 0.0240 per month and a factor alpha of 0.0189 per month with a t-statistic
of 7.63. This table establishes that the allocation result is broad-panel evidence.
    This table is central because it uses the complete characteristic universe. The family-level
model assigns weights across economic sleeves, and the full-panel test applies those weights to
all 212 signals. The positive incremental IC means that the state-dependent family structure
improves monthly cross-sectional ranking relative to a static full-panel aggregation. The
portfolio and alpha evidence then show that the improved ranking has economic value after
standard factor controls.
   The result also addresses the interpretation that family allocation could simply select
a few strong historical sleeves. The full-panel test restores the underlying signal breadth
and evaluates the allocation structure in the same out-of-sample months. The evidence
therefore says that macro-regime memory improves the organization of broad characteristic
information across the full anomaly panel.
   Table 5 and Figure 4 report the stock-level benchmark evidence. The pooled all-212
ridge has a mean IC of 0.0725 and an IC t-statistic of 15.93. The ridge plus macro-residual
specification has a mean IC of 0.0727, with an incremental IC of 0.0002 relative to pooled

                                               16

===== PAGE 17 =====

ridge. The benchmark comparison clarifies the economic object. The paper targets the
allocation value of family-level characteristic information, while the all-212 ridge anchors
stock-level prediction.
   This benchmark result strengthens the paper because it prevents an overbroad interpre-
tation. The pooled ridge is highly successful at stock-level ranking. The paper uses the
pooled ridge to establish that stock-level prediction is a demanding benchmark, then shows
that the family-allocation layer delivers a distinct economic object: state-dependent capital
allocation across types of characteristic information.
   The main results therefore form a coherent sequence. Macro-regime memory reallocates
capital across anomaly families. The resulting allocation returns are large and statistically
sharp. The result survives the full 212-characteristic layer. A strong pooled ridge anchors
stock-level prediction and prevents the paper from overinterpreting generic model complexity.
The next section studies the economic mechanism that explains where the family-allocation
value is concentrated.
   The sequence matters for the paper’s contribution. If the paper ended with Table 3, it
would be a style-allocation result. If it ended with Table 4, it would show broad-panel alloca-
tion value but provide less direct evidence on why the allocation works. If it centered solely
on Table 5, it would become a stock-level prediction comparison. The package of Tables 3–5
and 15 shows that macro-regime memory is valuable as an interpretable allocation structure
in a broad characteristic panel, while stock-level ridge remains the correct benchmark for
direct stock ranking.


8    Liquidity/Limits, Trend States, and Capacity
Table 9 reports the mechanism evidence, and Figure 6 plots the cross-sample t-statistics
for the lead channel and comparison pair. The liquidity/limits × trend cell is the central
channel. In the full universe, the high-trend minus low-trend liquidity/limits return spread
is -0.0313 per month, with a t-statistic of -7.41. The sign convention is high minus low.
Thus, the negative value means that liquidity/limits payoffs are stronger in low-trend states.
In the all-firm sleeve evidence, the Liquidity/Limits family earns 1.41 percent per month in
low-trend states and reverses to -1.79 percent per month in high-trend states. The reversal
gives the mechanism a direct economic interpretation: unconditional exposure to liquidity-
constrained characteristics is costly in states where trend conditions predict negative payoffs,
and state-dependent allocation is economically necessary.
   The sign is economically intuitive. In low-trend states, risk appetite is lower, funding
conditions are more fragile, and intermediated arbitrage capital can be more constrained.
Securities with stronger liquidity and limits-to-arbitrage characteristics then require larger
compensation. In high-trend states, the same family can carry negative expected payoffs
as capital rotates away from those constrained names. The liquidity/limits sleeve captures
precisely that type of firm-level information. Internet Appendix Table IA.33 shows that
excluding any named market episode leaves the high-minus-low spread between -3.27 percent
and -3.15 percent per month, so the reversal is structural rather than episodic.

                                              17

===== PAGE 18 =====

   The same table shows that the result remains strong outside microcaps. In the outside-
microcap sample, the high-minus-low spread is -0.0171 with a t-statistic of -4.58. In the
value-weighted outside-microcap specification, the spread is -0.0146 with a t-statistic of -3.73.
These estimates matter because they move the mechanism beyond the smallest firms while
preserving the limits-to-arbitrage interpretation. The evidence is strongest where arbitrage
constraints remain economically plausible.
   The outside-microcap and value-weighted evidence are important because they answer a
natural capacity question. Many anomaly results are strongest among the smallest firms,
where implementation concerns can dominate interpretation. Here the mechanism remains
visible after removing microcaps and after value-weighting the outside-microcap universe.
The result therefore has economic scope beyond the smallest stocks while still retaining the
ordered attenuation predicted by limits-to-arbitrage theory.
    Table 8 and Figure 5 report the regime-family payoff map across macro blocks and fam-
ilies. Liquidity/limits × trend is one of the most economically sharp cells. The heatmap
also shows state dependence in expectations, continuation, safety/downside, and profitabil-
ity/quality cells. This broader map is useful because it shows that macro states reprice
several types of characteristic information, while also identifying liquidity/limits × trend as
the lead mechanism.
   Figure 5 gives the reader a complete view of the family-state surface. Several families
interact with macro blocks, but the liquidity/limits × trend cell stands out because it com-
bines economic clarity, large magnitude, and strong inference. This matters for contribution
framing. A broad allocation model can use many sources of state dependence, while the lead
mechanism can be concentrated in the cell where the theory is sharpest.
   Table 9 and Figure 6 compare liquidity/limits × trend with continuation × valuation
across cross-sectional controls. The liquidity/limits estimates remain large and positive after
transforming the sign to low-trend minus high-trend t-statistics. Continuation × valuation
provides supporting context, but it lacks the same confirmation strength. The figure therefore
separates the central channel from secondary state dependence.
   The transformed sign in Table 9 and Figure 6 is designed for readability: positive val-
ues indicate stronger low-trend liquidity/limits payoffs. The pattern remains economically
large across the full universe, outside microcaps, and middle-cap regions. The comparison
pair helps calibrate the evidence. Continuation × valuation shows that other macro-family
interactions exist, while liquidity/limits × trend carries the clearest combination of theory,
magnitude, and cross-sectional scope.
   The mechanism also explains the relation between return spreads and IC evidence. Return
spreads show the economic payoff to the family-state cell. ICs show whether the same state
dependence improves the ranking of stocks inside the cross section. A strong mechanism
should appear in both forms. The liquidity/limits × trend evidence satisfies that require-
ment: it is economically large in returns and aligned with ranking evidence across capacity
regions.




                                               18

===== PAGE 19 =====

8.1    Capacity and Size
Table 10 and Figures 7 and 8 report the capacity frontier. The full-universe low-trend
minus high-trend equal-weight return spread is 0.0313 with a transformed t-statistic of 7.41.
Outside microcaps, the transformed spread is 0.0171 with a t-statistic of 4.58. In the middle
60 percent of the market-cap distribution, the transformed spread is 0.0142 with a t-statistic
of 3.67. The upper half remains positive but smaller. The large top-20 percent and mega
top-10 percent rows move toward zero or negative transformed values.
   The same economic scope appears in portfolio implementation measures already reported
in the main tables. The value-weighted mixture-of-experts long-short portfolio earns 1.39
percent per month with a t-statistic of 5.36, and the average monthly turnover is 0.610.
The value-weighted evidence confirms that the allocation result is not confined to microcap
stocks, while turnover records the amount of capital reallocation required by the dynamic
rule.
   This pattern sharpens the mechanism. A liquidity/limits mechanism should be strongest
where arbitrage is difficult and attenuated where capacity is deepest. The data show pre-
cisely that scope. The strongest return and IC evidence appears outside the largest names,
including the outside-microcap and middle-cap regions. The largest-stock attenuation is the
cross-sectional footprint of the limits-to-arbitrage mechanism.
   The capacity frontier turns a return spread into a mechanism test. A pure statistical
timing effect has little reason to line up monotonically with market-capacity regions. A
limits-to-arbitrage effect has a clear reason to do so: capital constraints and trading frictions
bind more tightly outside the deepest-capacity stocks. The observed ordering is therefore
economically informative. It says that the state-dependent payoff is strongest where limits
to arbitrage should matter and fades where capacity is deepest.
   The holdout evidence in Table 13 reinforces this interpretation. For liquidity/limits ×
trend, the formation-period high-minus-low return is -0.0426 with a t-statistic of -5.69, and
the confirmation-period estimate remains negative at -0.0186 with a t-statistic of -3.11. The
continuation × valuation pair has materially smaller confirmation-period magnitude. The
lead mechanism therefore combines economic intuition, cross-sectional scope, and holdout
behavior.
   The holdout design is useful because it separates mechanism discovery from mechanism
confirmation. The formation period identifies strong family-state pairs, and the confirmation
period evaluates whether the selected pair continues to carry the predicted sign and economic
magnitude. Liquidity/limits × trend retains this direction with a large confirmation-period
estimate. The result therefore does more than rank cells by in-sample strength; it shows
that the lead mechanism has out-of-sample persistence within the mechanism-design layer.
   The capacity evidence also guides economic scope. The paper’s strongest mechanism lan-
guage should center on liquidity/limits payoffs in low-trend states, with the effect strongest
outside the largest names. The evidence supports a broad family-allocation contribution and
a capacity-shaped limits-to-arbitrage mechanism centered away from the deepest-capacity
mega-cap region.


                                               19

===== PAGE 20 =====

   This scope is a strength. Asset-pricing mechanisms often have natural domains. Limits
to arbitrage should matter most where trading, funding, and price-pressure frictions remain
relevant. The paper therefore states the mechanism with precision: macro-regime memory
reallocates anomaly-family capital in a broad full-characteristic panel, and the strongest
economic channel is liquidity/limits compensation in low-trend states with the sharpest
evidence outside the deepest-capacity stocks.


9     State-Specificity and Model-Benchmark Evidence
Table 8 reports placebo and information timing design. Macro-regime allocation beats equal-
weight family allocation for several validated macro rules. Macro-shuffle, random-macro,
release-lag, calendar-state, and block-drop comparisons clarify that the result is tied to
macro-state content rather than arbitrary time labels. The trend block matters for the
liquidity/limits channel, while other macro blocks help discipline the broader allocation
layer.
   The placebo structure is designed to preserve the empirical architecture while removing
the economic content of the macro state. Calendar-state and shifted-state comparisons keep
a time-series pattern but detach it from the macro interpretation. Family-label placebos
preserve the distribution of family outcomes but break the economic link between a family
and its state. These comparisons are valuable because the main result survives when the
economically meaningful state-family link is present and is materially smaller when that link
is mechanically disrupted.
   Table 11 and Internet Appendix Table IA.28 report relabeling and shifted-state evidence
for the lead mechanism. The liquidity/limits × trend pair has an actual t-statistic of -7.41.
Circularly shifted macro states, calendar-month states, and family-label placebos produce
smaller patterns. This evidence is important because it separates the mechanism from a
relabeled calendar pattern. The actual macro-state pair is sharper than the alternatives.
   The same logic applies to the block-drop evidence. The trend block is central for liq-
uidity/limits because it summarizes the market environment in which arbitrage capital is
deployed. Dropping or replacing that block reduces the sharpness of the mechanism. The
result therefore has a specific macro source rather than a generic dependence on any state
variable.
   Table 12 reports model-class benchmark evidence. The pooled all-212 ridge remains
the strongest stock-level anchor. Decay-weighted ridge, ridge-decay blends, family-balanced
ridge, SGD variants, and a neural benchmark provide useful comparisons, and they leave
the central interpretation unchanged. Compute intensity provides benchmark comparisons.
The evidence points to state-dependent allocation across economic anomaly families.
   The compute-heavy comparisons are included for interpretation and benchmark compar-
ison. They show that the paper can accommodate flexible stock-level prediction methods
while keeping the contribution at the family-allocation layer. The strong pooled ridge is in-
formative because it establishes that full-panel linear shrinkage is difficult to beat for direct


                                               20

===== PAGE 21 =====

monthly stock ranking. The family-allocation result is evaluated alongside that benchmark
and retains its economic role.
  Internet Appendix Table IA.30 expands the compute-heavy comparison. The pooled ridge
has a mean IC of 0.0725 and an alpha t-statistic of 14.48. The neural benchmark has a mean
IC of 0.0526, and the SGD variants remain below the pooled ridge in mean IC. These results
matter because they prevent the paper from being misread as a generic machine-learning
paper. The family allocation layer is the economic contribution.
   Internet Appendix Table IA.4 reports information-set timing evidence. The table docu-
ments target timing, macro timing, panel return-state timing, family mapping, stock-level
benchmark controls, mechanism pairs, and capacity scope. The appendix presents these
checks in reader-facing form because information timing design is essential for a walk-forward
asset-pricing design.
   Internet Appendix Tables IA.24–IA.26 report additional state-specificity and timing ev-
idence. These tables show that the allocation evidence is distributed beyond a single cal-
endar episode, crisis exclusion, or benchmark comparison. Internet Appendix Tables IA.29
and IA.30 and Figures IA.9 and IA.10 report the corresponding frontier and compute-heavy
benchmark evidence. Together, the robustness evidence supports the interpretation that
macro-regime memory changes the allocation value of anomaly-family information.
   The Internet Appendix reports construction detail and expanded evidence for the same
empirical sequence: timing and family mapping, allocation performance, full-panel bench-
marks, mechanism evidence, capacity scope, state specificity, and model comparisons. Data-
construction tables document timing and family mapping. Allocation tables expand the
baseline evidence. Benchmark tables show how the result relates to stock-level prediction.
Mechanism tables establish the liquidity/limits × trend channel. Capacity tables show where
the mechanism is strongest. This organization keeps every exhibit attached to an economic
interpretation.
   Table 14 summarizes the economic scope of the main finding. The family allocation
result is broad and economically large. The full 212 layer establishes the breadth of the
characteristic panel. The pooled ridge benchmark establishes that the paper’s object differs
from stock-level prediction dominance. The liquidity/limits × trend mechanism establishes
the economic channel. The capacity frontier establishes where the mechanism is strongest.
This is the package of evidence that supports the paper’s contribution.
   Table 14 summarizes the economic interpretation of the empirical layers. The evidence
identifies state-dependent allocation value across economic anomaly families, broad-panel
support from the full 212-characteristic hierarchy, a strong stock-level benchmark in pooled
ridge, and a capacity-shaped liquidity/limits mechanism. Each empirical layer has a distinct
economic role.
   This discipline is useful for readers because the paper contains several large empirical
objects. The allocation result, hierarchical 212 result, pooled ridge benchmark, mechanism
map, placebo evidence, and capacity frontier each answer a different question. Table 10
prevents those objects from blending into a single oversized interpretation. The contribution
is powerful precisely because the pieces fit: broad state-dependent allocation, full-panel


                                             21

===== PAGE 22 =====

support, demanding benchmark evidence, and a mechanism whose cross-sectional shape
matches limits-to-arbitrage economics.
   Table 7 links the allocation evidence to controlled cross-sectional prediction and factor-
adjusted portfolio performance. This table matters because it places the family-allocation
object beside the stock-level and hierarchical objects in a common evidence set. The allo-
cation rows show that the main rules generate large long-short returns and factor alphas.
The stock-level and hierarchical rows show that the full-characteristic benchmark remains
strong. The table therefore connects three pieces of the paper: the family allocator earns
capital-allocation returns, the 212-characteristic layer preserves breadth, and the stock-level
ridge benchmark supplies a demanding comparison for direct stock ranking.
   Table 4 is the bridge between portfolio performance and economic interpretation. The
average weights show which families receive capital under the lead allocation rule; the dis-
persion and percentile columns show how much those capital shares move through time; the
state correlations show how the weights relate to market trend and valuation conditions.
A fixed family portfolio would have no such state-contingent composition. Macro-regime
memory instead produces a changing mix of continuation, valuation, quality, expectations,
investment, safety, correction, and liquidity/limits information. That changing mix is central
to the paper because it converts a large characteristic panel into a portfolio-choice object.
   The table also clarifies why the allocation result is broader than a timing rule for a
single familiar style. Continuation receives substantial average weight, but the model also
moves capital toward other families when the state history supports doing so. The family
weights are nonnegative and sum to one, so the rows can be read directly as capital shares.
This is the economic meaning of regime memory in the paper: the model learns which
type of characteristic information deserves capital under the current macro environment and
expresses that information as a portfolio allocation across families.
   Table 11 reports state-specificity evidence in three panels. The macro-state comparisons
replace or perturb the macro information set. The block-drop panel shows how the allocation
evidence changes when one economic macro block is removed from the full state description.
The relabeling panel compares the actual family-state pair with shifted, calendar, and re-
labeled alternatives. The estimates are materially smaller when the economic macro-family
link is removed, which supports the interpretation that the allocation value comes from
meaningful state dependence rather than a relabeled calendar pattern.
   The state-specificity evidence has an important role in the architecture of the paper.
A macro-conditioned allocation rule could look attractive because it accidentally captures
a calendar pattern, crisis dummy, or persistent family-level return difference. Table 11
addresses that possibility by keeping the empirical setting recognizable while changing the
economic content of the state-family link. When the link is shifted, randomized, or relabeled,
the evidence becomes materially smaller. When the meaningful macro-family link is present,
the allocation and mechanism evidence are sharp. That contrast is what a reader should
take from the table.
   Table 12 puts model class comparisons in the main paper because the benchmark evidence
is part of the contribution. The pooled all-212 ridge is strong, and that strength is useful.


                                              22

===== PAGE 23 =====

It shows that the full characteristic panel contains substantial stock-level ranking informa-
tion and that a simple shrinkage benchmark is difficult to improve upon for direct stock
prediction. The family-allocation contribution is therefore defined precisely: macro-regime
memory changes the allocation value of economic characteristic families, while the pooled
ridge anchors the stock-level benchmark.
   This benchmark structure keeps the paper from becoming a generic model-comparison
exercise. The stock-level models answer a direct ranking question: given all 212 character-
istics, which stocks have higher next-month expected returns? The family-allocation model
answers a different portfolio-choice question: which source of characteristic information de-
serves capital in a given macro state? Table 12 shows that compute-heavy and flexible
models are informative benchmarks, but the empirical contribution is the state-dependent
organization of characteristic information into capital shares across economic families.
   Table 13 reports formation and confirmation-period evidence for the lead mechanism. For
liquidity/limits × trend, the predicted-direction return remains economically large in the
confirmation period after 2005. This matters because the mechanism is evaluated beyond
the formation period that identifies the family-state pair. The table also reports the relevant
comparison channel, which shows that the liquidity/limits result is the central economic
channel rather than a general tendency for every family-state interaction to look equally
sharp.
   The holdout design gives the mechanism a time-series interpretation. The formation
period identifies the predicted sign of the state spread, and the confirmation period evaluates
whether the same economic direction remains visible later in the sample. Liquidity/limits ×
trend retains the predicted sign and meaningful magnitude after 2005. The result is especially
informative because the confirmation period includes very different market environments
from the earlier sample. The mechanism therefore travels across decades while preserving
the economic direction implied by limits to arbitrage.
    Table 14 closes the empirical section by mapping evidence blocks to economic interpre-
tation. The table is deliberately reader-facing: it links allocation value, full-panel breadth,
stock-level benchmark evidence, the liquidity/limits mechanism, capacity shape, state speci-
ficity, holdout behavior, and model-class benchmarks. The table makes clear that the paper’s
argument is cumulative. No single table carries the entire case. The main finding emerges
because the evidence lines up across allocation returns, full-characteristic ranking, stock-level
benchmarks, mechanism estimates, and capacity scope.
   The table is also useful for scope. The strongest statement supported by the evidence
is that macro-regime memory changes the allocation value of broad anomaly-family infor-
mation in the full 212-characteristic cross section. The sharpest economic mechanism is
liquidity/limits information across market-trend states. The market-capacity gradient then
shows where that mechanism is most economically relevant. The largest-stock attenuation is
therefore part of the interpretation, because a limits-to-arbitrage mechanism should be con-
centrated where arbitrage capacity is less elastic and trading frictions remain consequential.
  The sequence of Tables 3 through 15 and Figures 2 through 8 therefore gives the reader a
complete empirical map. Table 3 and Figure 3 establish allocation returns. Table 4 and Fig-


                                               23

===== PAGE 24 =====

ure 2 show state-dependent family weights. Table 5 brings the full characteristic panel back
into the analysis. Tables 6 and 7 and Figure 4 anchor stock-level and controlled return evi-
dence. Tables 8 through 10 and Figures 5 through 8 identify the liquidity/limits mechanism
and its capacity shape. Tables 11 through 13 show state specificity and persistence. Table
14 states the economic scope, and Table 15 shows that concentration in Continuation and
Valuation is an empirical feature of the optimal family allocation. The tables provide exact
estimates and inference; the figures make the allocation dynamics, benchmark comparisons,
mechanism, and capacity shape visible.


10     Conclusion
This paper studies when broad anomaly families deserve capital. Using the full Chen–
Zimmermann/OpenAP 212-characteristic panel and an information-set preserving walk-
forward design, the evidence shows that macro-regime memory reallocates expected-return
information across economic characteristic families. The allocation returns are large, the
full 212-characteristic hierarchical evidence is strong, and the pooled all-characteristic ridge
benchmark clarifies that the contribution is family-level allocation rather than generic stock-
level model complexity.
   The strongest economic mechanism is the Liquidity/Limits family across market-trend
states. Its payoffs are strongest in low-trend states, remain economically sharp outside
microcaps and in middle-cap regions, and attenuate in the largest names where capacity is
deepest. That capacity pattern strengthens the interpretation because it aligns the state
dependence with the economics of constrained arbitrage.
   The evidence shows that anomaly research should evaluate both which characteristics
forecast returns and when each family of characteristic information deserves capital.
Macro-regime memory provides a structured way to make that allocation decision in a
full-characteristic cross section.
   More broadly, the paper argues that the next step in characteristic-based asset pricing is
organization. The field has moved from a small set of factors to a broad panel of signals.
A broad panel creates value, but it also creates a portfolio-choice problem. Macro-regime
memory provides one answer: organize signals into economic families, learn when each family
is valuable, benchmark stock-level prediction with a demanding full-panel model, and use
mechanism and capacity evidence to explain where the value comes from. The result is a
state-dependent view of expected-return information in the cross section.




                                              24

===== PAGE 25 =====

References

References
Chen, Andrew Y., and Tom Zimmermann, 2022, Open source cross-sectional asset pricing,
 Critical Finance Review 11, 207–264.

Cochrane, John H., 2011, Presidential address: Discount rates, Journal of Finance 66, 1047–
  1108.

Daniel, Kent, and Sheridan Titman, 1997, Evidence on the characteristics of cross sectional
 variation in stock returns, Journal of Finance 52, 1–33.

Fama, Eugene F., and Kenneth R. French, 1993, Common risk factors in the returns on
  stocks and bonds, Journal of Financial Economics 33, 3–56.

Fama, Eugene F., and Kenneth R. French, 2015, A five-factor asset pricing model, Journal
  of Financial Economics 116, 1–22.

Freyberger, Joachim, Andreas Neuhierl, and Michael Weber, 2020, Dissecting characteristics
  nonparametrically, Review of Financial Studies 33, 2326–2377.

Green, Jeremiah, John R. M. Hand, and Frank Zhang, 2017, The characteristics that provide
  independent information about average U.S. monthly stock returns, Review of Financial
  Studies 30, 4389–4436.

Gu, Shihao, Bryan Kelly, and Dacheng Xiu, 2020, Empirical asset pricing via machine learn-
 ing, Review of Financial Studies 33, 2223–2273.

Harvey, Campbell R., Yan Liu, and Heqing Zhu, 2016, ... and the cross-section of expected
  returns, Review of Financial Studies 29, 5–68.

Jegadeesh, Narasimhan, and Sheridan Titman, 1993, Returns to buying winners and selling
  losers: Implications for stock market efficiency, Journal of Finance 48, 65–91.

Kelly, Bryan T., Seth Pruitt, and Yinan Su, 2019, Characteristics are covariances: A unified
  model of risk and return, Journal of Financial Economics 134, 501–524.

Lakonishok, Josef, Andrei Shleifer, and Robert W. Vishny, 1994, Contrarian investment,
  extrapolation, and risk, Journal of Finance 49, 1541–1578.

Lettau, Martin, and Sydney Ludvigson, 2001, Consumption, aggregate wealth, and expected
  stock returns, Journal of Finance 56, 815–849.

McLean, R. David, and Jeffrey Pontiff, 2016, Does academic research destroy stock return
 predictability?, Journal of Finance 71, 5–32.

Pontiff, Jeffrey, 2006, Costly arbitrage and the myth of idiosyncratic risk, Journal of Ac-
  counting and Economics 42, 35–52.

                                            25

===== PAGE 26 =====

Rapach, David E., Jack K. Strauss, and Guofu Zhou, 2010, Out-of-sample equity premium
  prediction: Combination forecasts and links to the real economy, Review of Financial
  Studies 23, 821–862.

Shleifer, Andrei, and Robert W. Vishny, 1997, The limits of arbitrage, Journal of Finance
  52, 35–55.

Stambaugh, Robert F., Jianfeng Yu, and Yu Yuan, 2015, Arbitrage asymmetry and the
  idiosyncratic volatility puzzle, Journal of Finance 70, 1903–1948.




                                           26

===== PAGE 27 =====

                                         Table 1: Sample, Signal Families, and Walk-Forward Timing
                                                  Panel A. Anomaly-family construction
             Family                               Signals Positive Negative Economic content
             Valuation                                  36        35          1   Discount-rate and recovery states
             Continuation                               27        26          1   Trend persistence and underreaction
             Correction                                  4         1          3   Post-dislocation reversal
             Profitability/quality                      27        23          4   Quality under uncertainty
             Investment/issuance                        46        20         26   Investment discipline and financing states
             Safety/downside                            26         2         24   Downside protection and stress states
             Liquidity/limits                           21         4         17   Trading frictions and arbitrage capacity
27           Expectations                               25        21          4   Forecast updating and analyst information flow

                                                             Panel B. Prediction design
         Design element                      Value                     Interpretation
         Start of characteristic history     1963                      First year used in model training
         First prediction year               1985                      After initial training and validation windows
         Initial training window             10 years                  1963–1972 for the first prediction year
         Validation window                   12 years                  Fixed length for model selection
         Prediction months                   479                       January 1985 through November 2024
         Roll-forward frequency              Annual                    Training expands; validation rolls forward
     Notes: Panel A reports the economic families used as allocation sleeves. Panel B reports the walk-forward design. Signals are the full Chen–
     Zimmermann/OpenAP characteristic panel used in the empirical package.

===== PAGE 28 =====

                                                Table 2: Macro-State Blocks and Allocation Rules
                                                           Panel A. Macro-state blocks
                                     Block        Series Max timing lag Economic role
                                     Credit            2        0 months   Financing conditions
                                     Growth            4        0 months   Real activity
                                     Inflation         3        0 months   Price pressure
                                     Liquidity         2        0 months   Aggregate liquidity
                                     Rates             4        0 months   Discount-rate conditions
                                     Risk              4        0 months   Market stress and volatility
                                     Trend             3        0 months   Market trend and drawdown state
                                     Valuation         1        0 months   Aggregate valuation
28
                                                       Panel B. Leading allocation rules
                   Allocation rule           Version               Mean return (%) NW t-statistic Sharpe Concentration
                   Mixture of experts        Nonnegative softmax                2.13             9.21      1.51             0.77
                   Bayesian dynamic          Nonnegative softmax                2.05             8.98      1.44             0.71
                   Validation ensemble       Nonnegative softmax                2.08             9.09      1.43             0.75
                   Ensemble                  Nonnegative softmax                1.95             8.05      1.36             0.75
                   Macro ridge               Nonnegative softmax                1.82             7.60      1.30             0.75
                   Factor momentum           Nonnegative softmax                1.82             7.62      1.17             0.68
                   Regime probability        Nonnegative softmax                1.90             7.01      1.16             0.89
                   Trailing Sharpe           Nonnegative softmax                1.70             7.51      1.16             0.73
     Notes: Panel A groups real-time macro information into economic blocks. Panel B reports the leading nonnegative allocation rules evaluated
     on the common prediction sample.

===== PAGE 29 =====

                                                   Table 3: Anomaly-Family Allocation Performance

      Allocation rule       Mean return (%) NW t-statistic   Sharpe   EW L-S (%) EW t-statistic VW L-S (%) Alpha (%) Alpha t-statistic Max drawdown (%)

      Mixture of experts               2.13           9.21     1.51          2.51         9.71         1.39      2.07            7.63             -22.71
      Validation ensemble              2.08           9.09     1.43          2.42         9.46         1.26      1.88            6.62             -31.83
      Bayesian dynamic                 2.05           8.98     1.44          2.43         9.39         1.36      1.94            6.74             -23.97
29    Ensemble                         1.95           8.05     1.36          2.28         8.54         1.12      1.85            6.67             -32.74
      Macro ridge                      1.82           7.60     1.30          2.14         7.89         1.07      1.73            6.39             -26.29
      Factor momentum                  1.82           7.62     1.17          2.20         8.01         1.17      1.64            6.68             -35.38
      Trailing Sharpe                  1.70           7.51     1.16          1.89         7.56         1.05      1.52            6.23             -41.52
      Equal weight                     0.38           5.81     0.94          1.22         6.66         0.41      0.58            4.33             -13.25

     Notes: Returns are monthly out-of-sample family-allocation returns. Long-short columns use decile portfolios formed from the corresponding
     allocation signal. Alpha uses the five Fama–French factors plus momentum. Newey–West inference is monthly.

===== PAGE 30 =====

                                       Table 4: Regime-Allocation Weights Across Anomaly Families

            Family                  Mean weight (%) Std. dev. (%) P10 (%) P90 (%) Max (%) Trend corr. Valuation corr.
            Continuation                        60.74            40.45      0.15      99.88     100.00
            Correction                           0.60             4.71      0.00       0.32      77.32
            Expectations                         1.98             4.79      0.00       5.06      55.00
30          Investment/issuance                  0.27             2.66      0.00       0.02      51.00
            Liquidity/limits                     3.64            15.81      0.00       1.69      99.98
            Profitability/quality               14.40            24.34      0.01      54.84      99.77
            Safety/downside                      0.93             7.24      0.00       0.02      99.12
            Valuation                           17.44            30.22      0.00      74.74      99.94
     Notes: The table reports time-series properties of the mixture-of-experts family weights. Correlations are between monthly family weights
     and macro-state blocks, giving a compact table version of the allocation-weight evidence.

===== PAGE 31 =====

                                             Table 5: Full 212-Characteristic Hierarchical Evidence

             Allocation rule           Mean IC   IC t-statistic Incremental IC   Incremental t   EW L-S (%) VW L-S (%) Alpha (%)   Alpha t-statistic

             Mixture of experts           0.05          11.02             0.02            6.25         2.40        1.46     1.89               7.63
             Bayesian dynamic             0.05          11.14             0.02            6.14         2.38        1.57     1.82               6.56
             Validation ensemble          0.05          10.78             0.02            5.19         2.29        1.40     1.68               5.92
31           Macro ridge                  0.05           9.93             0.02            5.02         2.24        1.44     1.73               8.36
             Ensemble                     0.05          10.25             0.02            4.68         2.21        1.30     1.61               6.46
             Equal weight                 0.05           7.30             0.01            3.36         1.60        1.14     0.84               4.31
             EWMA sleeve performance      0.04           8.81             0.01            3.68         1.98        1.22     1.26               5.41
             Contextual bandit            0.04           8.77             0.01            3.58         1.95        1.04     1.24               5.54

     Notes: The hierarchical layer applies family-allocation weights to the full 212-characteristic panel. Incremental IC is measured relative to
     static full-panel characteristic aggregation.

===== PAGE 32 =====

                                                           Table 6: Stock-Level Benchmark Evidence

     Stock-level model                  Mean IC   IC t-statistic Incremental IC vs pooled ridge   Incremental t   EW L-S (%) VW L-S (%)   Alpha (%)   Alpha t-statistic

     Ridge plus macro residual             0.07          15.63                             0.00            0.21         3.80       2.10        3.32              14.22
     Pooled all-212 ridge                  0.07          15.93                             0.00            0.00         3.88       2.09        3.44              14.48
     Decay-weighted ridge                  0.07          15.08                            -0.00           -0.13         3.82       1.82        3.44              13.08
     Ridge-decay blend                     0.07          15.18                            -0.00           -0.74         3.80       1.81        3.39              13.42
32   Ridge plus validation residual        0.07          15.64                            -0.00           -0.67         3.77       2.01        3.31              13.62
     Ridge plus macro-analog residual      0.07          15.59                            -0.00           -0.90         3.76       1.90        3.27              13.16
     Ridge plus attention residual         0.07          15.71                            -0.00           -1.17         3.74       1.91        3.26              13.55
     Ridge plus ensemble residual          0.07          15.69                            -0.00           -0.94         3.82       2.09        3.34              13.76
     Family-balanced ridge                 0.07          16.32                            -0.00           -2.32         3.84       2.06        3.41              14.40
     SGD Huber                             0.07          10.48                            -0.01           -1.77         3.24       2.24        2.53              12.62

      Notes: The pooled all-212 ridge is the demanding stock-level benchmark. Macro-residual variants are evaluated relative to that benchmark to
      separate stock-level prediction from family-level allocation.

===== PAGE 33 =====

                                     Table 7: Controlled Cross-Sectional Prediction and Factor-Alpha Evidence

     Object                                  Specification                      Mean IC   Controlled FMB t   EW L-S (%)   VW L-S (%)   Alpha (%)   Alpha t-statistic

     Stock-level or hierarchical benchmark   Ridge plus macro residual             0.07               2.42         3.80         2.10        3.32              14.22
     Stock-level or hierarchical benchmark   Pooled all-212 ridge                  0.07              12.83         3.88         2.09        3.44              14.48
     Stock-level or hierarchical benchmark   Hierarchical validation ensemble      0.05               3.08         2.29         1.40        1.68               5.92
33   Stock-level or hierarchical benchmark   Hierarchical macro ridge              0.05               3.29         2.24         1.44        1.73               8.36
     Stock-level or hierarchical benchmark   Static 212 equal weight               0.03               1.59         1.58         0.46        0.92               6.52
     Family allocation                       Mixture of experts                    0.00              10.59         2.51         1.39        2.07               7.63
     Family allocation                       Bayesian dynamic                      0.00              10.44         2.43         1.36        1.94               6.74
     Family allocation                       Validation ensemble                   0.00              10.74         2.42         1.26        1.88               6.62
     Family allocation                       Macro ridge                           0.00               8.17         2.14         1.07        1.73               6.39

     Notes: The table combines Fama–MacBeth, IC, long-short, and factor-alpha evidence for the main allocation and benchmark objects. Factor
     alpha uses the five Fama–French factors plus momentum.

===== PAGE 34 =====

                                                              Table 8: Regime-Family Payoff Map

           Macro block   Family                  High-state return (%)   Low-state return (%) High minus low (%) Return t-statistic IC spread   IC t-statistic

           Trend         Liquidity/limits                        -1.79                  1.41                -3.20            -6.77      -0.06           -7.14
           Valuation     Expectations                            -0.38                  1.94                -2.32            -5.12      -0.04           -5.28
           Valuation     Continuation                            -0.03                  3.07                -3.09            -4.76      -0.04           -4.82
           Valuation     Investment/issuance                     -0.15                 -1.29               +1.14              3.97       0.02            4.26
           Credit        Correction                              -1.54                  0.73                -2.27            -3.94      -0.03           -3.65
           Valuation     Profitability/quality                    0.30                  2.33                -2.03            -3.83      -0.03           -4.25
34         Trend         Safety/downside                         -0.31                 -2.69               +2.39              3.50       0.04            4.24
           Valuation     Valuation                                0.41                  1.93                -1.52            -3.36      -0.04           -5.28
           Inflation     Profitability/quality                    2.85                  1.03               +1.82              3.15       0.02            2.58
           Rates         Correction                               0.63                 -1.06               +1.69              2.94       0.03            3.55
           Inflation     Valuation                                1.84                  0.50               +1.34              2.89       0.02            2.78
           Trend         Valuation                                1.93                  0.52               +1.41              2.87       0.02            2.51
           Rates         Liquidity/limits                         0.53                 -0.88               +1.42              2.87       0.03            3.43
           Risk          Correction                              -1.51                  0.19                -1.70            -2.78      -0.02           -2.11

     Notes: Rows are sorted by the absolute return t-statistic. The liquidity/limits × trend row is the lead economic channel and uses the high-state
     minus low-state sign convention in this table.

===== PAGE 35 =====

                                      Table 9: Liquidity/Limits × Trend Mechanism Across Universes

     Construction            Low minus high (%) t-statistic High-state return (%) Low-state return (%) High months Low months
     All firms                                 3.13        7.41                    -2.23                    0.89            248            248
     Outside microcaps                         1.71        4.58                    -1.45                    0.25            248            248
35   Liquid-proxy universe                     1.71        4.58                    -1.45                    0.25            248            248
     Industry neutral                          2.76        7.06                    -1.99                    0.77            248            248
     Beta neutral                              3.00        7.24                    -2.12                    0.88            248            248
     Large stocks                             -0.18       -0.53                    -0.25                   -0.43            248            248
     Notes: Positive low-minus-high estimates indicate stronger liquidity/limits payoffs in low-trend states. Rows compare universe screens and
     score constructions while preserving the same macro-family channel.

===== PAGE 36 =====

                                        Table 10: Capacity Frontier of the Liquidity/Limits Mechanism

               Capacity region       EW return low-high EW return t VW return low-high VW return t IC low-high                        IC t
               All firms                               3.13            7.41                     2.74            6.16           0.07 8.32
               Micro bottom 20                         1.03            2.11                     0.99            1.98           0.01 1.78
               Outside microcaps                       1.71            4.58                     1.46            3.73           0.05 6.69
36             Middle 60                               1.42            3.67                     1.14            3.02           0.04 4.90
               Upper half                              0.50            1.58                     0.60            1.72           0.02 3.38
               Upper third                             0.17            0.54                    -0.01           -0.03           0.01 1.77
               Large top 20                           -0.18           -0.53                    -0.52           -1.29          -0.00 -0.11
               Mega top 10                            -0.58           -1.57                    -0.93           -2.09          -0.02 -1.54
     Notes: Positive low-high values indicate stronger liquidity/limits payoffs in low-trend states. The market-capacity ordering gives the mechanism
     its economic scope.

===== PAGE 37 =====

                                                             Table 11: State-Specificity Evidence
                                                             Panel A. Macro-state content comparisons

                                     State comparison                               Allocation rule   Estimate (%) t-statistic       Months

                                     Macro shuffle minus full macro                 Macro ridge                 -0.29        -1.03      479
                                     Macro shuffle minus full macro                 Ensemble                    -0.36        -1.53      479
                                     Extra lag minus equal weight                   Macro ridge                +1.45          7.08      479
                                     Extra lag minus equal weight                   Ensemble                   +1.58          7.61      479
                                     Single-risk-state benchmark minus full macro   Macro ridge                +0.15          0.75      479
                                     Single-risk-state benchmark minus full macro   Ensemble                   +0.01          0.04      479
                                     Calendar dummy minus full macro                Macro ridge                +0.31          1.18      479
                                     Calendar dummy minus full macro                Ensemble                   +0.11          0.44      479
                                     Random macro minus full macro                  Macro ridge                 -0.17        -0.72      479
                                     Random macro minus full macro                  Ensemble                    -0.21        -0.95      479

                                                                Panel B. Macro-block drop comparisons

                                             Block comparison                               Estimate (%)       t-statistic Months

                                             Drop Inflation block minus full macro states             +0.04         0.33       479
37                                           Drop Growth block minus full macro states                +0.04         0.52       479
                                             Drop Rates block minus full macro states                 +0.05         1.19       479
                                             Drop Credit block minus full macro states                 -0.03       -0.57       479
                                             Drop Liquidity block minus full macro states             +0.03         0.87       479
                                             Drop Risk block minus full macro states                   -0.04       -0.27       479
                                             Drop Valuation block minus full macro states             +0.02         1.40       479
                                             Drop Trend block minus full macro states                  -0.08       -1.23       479

                                                            Panel C. Mechanism relabeling comparisons

                 Macro-family pair            State comparison                 Actual t Comparison mean abs. t          Comparison max abs. t    Estimate (%)

                 Liquidity/limits × Trend     Actual macro-family pair            -7.41                        0.00                       0.00          -3.13
                 Liquidity/limits × Trend     Circularly shifted macro state      -7.41                        0.56                       1.07          -3.13
                 Liquidity/limits × Trend     Calendar-month state                -7.41                        1.10                       1.10         +0.43
                 Liquidity/limits × Trend     Family-label relabeling             -7.41                        2.00                       4.61          -3.13
                 Continuation × Valuation     Actual macro-family pair            -2.39                        0.00                       0.00          -1.18
                 Continuation × Valuation     Circularly shifted macro state      -2.39                        1.92                       3.27          -1.18
                 Continuation × Valuation     Calendar-month state                -2.39                        0.53                       0.53         +0.25
                 Continuation × Valuation     Family-label relabeling             -2.39                        2.28                       3.38          -1.18

     Notes: Panel A compares altered state definitions with the full macro-state information set. Panel B reports block-drop comparisons for the
     ensemble rule. Panel C compares the actual family-state pair with relabeled or shifted alternatives.

===== PAGE 38 =====

                                                        Table 12: Model-Class Benchmark Evidence

     Model class                       Benchmark role                         Mean IC   IC t-statistic   Incremental IC vs pooled ridge Incremental t   FMB t    Alpha t

     Ridge plus macro residual        Macro residual after full-panel ridge      0.07           15.63                             0.00           0.21     2.42     14.22
     Pooled all-212 ridge             Full-panel stock-level benchmark           0.07           15.93                             0.00           0.00    12.83     14.48
     Decay-weighted ridge             Decay-aware linear benchmark               0.07           15.08                            -0.00          -0.13     2.56     13.08
     Ridge-decay blend                Decay-aware linear benchmark               0.07           15.18                            -0.00          -0.74     0.03     13.42
     Ridge plus validation residual   Macro residual after full-panel ridge      0.07           15.64                            -0.00          -0.67     2.21     13.62
38   Ridge plus macro-analog residual Macro residual after full-panel ridge      0.07           15.59                            -0.00          -0.90     2.76     13.16
     Ridge plus attention residual    Macro residual after full-panel ridge      0.07           15.71                            -0.00          -1.17     3.67     13.55
     Ridge plus ensemble residual     Macro residual after full-panel ridge      0.07           15.69                            -0.00          -0.94     2.42     13.76
     Family-balanced ridge            Family-balanced linear benchmark           0.07           16.32                            -0.00          -2.32    -1.62     14.40
     SGD Huber                        Regularized stock-level benchmark          0.07           10.48                            -0.01          -1.77     0.72     12.62
     SGD elastic net                  Regularized stock-level benchmark          0.06           13.01                            -0.01          -4.25     1.32     11.41
     Neural network benchmark         Neural stock-level benchmark               0.05            9.84                            -0.02          -5.15     2.71     10.41

     Notes: The table compares full-panel ridge, decay-aware ridge variants, family-balanced ridge, regularized stock-level models, and neural
     benchmarks. The evidence clarifies that model complexity is a benchmark object rather than the lead economic mechanism.

===== PAGE 39 =====

                                            Table 13: Holdout and Mechanism Persistence Evidence

           Macro-family channel          Period                                  Pred. ret. (%) t-statistic High months Low months
           Continuation × Valuation      Formation period, 1985–2004                        0.05         0.05             80              80
39         Continuation × Valuation      Confirmation period, 2005 onward                   0.00         0.00            223               2
           Liquidity/limits × Trend      Formation period, 1985–2004                        4.26         5.69             80              80
           Liquidity/limits × Trend      Confirmation period, 2005 onward                   1.86         3.11             62             107
     Notes: The predicted-direction transformation uses the sign learned in the formation period and applies the same direction to the confirmation
     period. The liquidity/limits × trend channel retains the predicted sign and economic magnitude after 2005.

===== PAGE 40 =====

                                                  Table 14: Economic Scope of the Main Finding

     Evidence block                Main tables       Economic interpretation
     Family allocation             Tables 3–4        Macro-regime memory assigns capital across broad anomaly families and generates large
                                                     out-of-sample allocation returns.
     Full characteristic panel     Table 5           The family-allocation structure remains valuable when applied to the complete 212-
                                                     signal panel.
     Stock-level benchmark         Tables 6–7        The pooled all-212 ridge is a demanding stock-level benchmark that sharpens the inter-
40                                                   pretation of the family-allocation result.
     Lead mechanism                Tables 8–9        Liquidity/limits × trend is the strongest family-state channel and has direct limits-to-
                                                     arbitrage content.
     Capacity shape                Table 10          The mechanism is strongest outside the deepest-capacity names, matching the economic
                                                     region where limits to arbitrage should bind most.
     State specificity             Tables 11–13      The evidence is concentrated in economically meaningful state-family links and retains
                                                     the predicted sign in the holdout period.
      Notes: The table maps the main evidence blocks to the paper’s central interpretation. The entries summarize the economic scope of the result
      rather than listing intermediate labels.

===== PAGE 41 =====

                              Table 15: Family-Group Ablations and the Economic Content of Concentration

                            Family set                                 Weight kept Mean NW t All-family mean Full-minus-set Inc. t

                            Continuation only                              60.74%   1.96%   7.06        2.13%         0.17%   0.75
                            Valuation only                                 17.44%   1.17%   4.96        2.13%         0.96%   3.27
                            Continuation + Valuation                       78.18%   2.08%   9.24        2.13%         0.05%   0.66
41
                            Continuation + Valuation + Profitability       92.58%   2.12%   9.11        2.13%         0.01%   0.11
                            All eight families                            100.00%   2.13%   9.21        2.13%         0.00%   0.00

     Notes: The table reports out-of-sample family-group ablations for the mixture-of-experts allocation rule. Restricted rows keep the original
     mixture-of-experts weights for the listed families and renormalize those weights to sum to one in each month. Returns are monthly family-
     allocation returns over the 1985–2024 prediction sample. Newey–West t-statistics use the same monthly time-series inference as the main
     allocation tables. The final two columns report the full eight-family return minus the restricted-family return.

===== PAGE 42 =====

              1      Full 212-characteristic panel


              2      Economic anomaly-family map


              3      Macro-regime memory


              4      Allocation and benchmark evidence


              5      Liquidity/limits by trend and capacity




Figure 1: Research design and economic object. The schematic summarizes the paper’s economic
object. The full 212-characteristic panel is organized into economic anomaly families; macro-regime
memory assigns capital shares across those families; and the evidence layers evaluate allocation re-
turns, full-panel breadth, stock-level benchmark evidence, and the liquidity/limits capacity channel.




                                                 42

===== PAGE 43 =====

           Valuation

       Continuation
                                                                                                                 0.8

          Correction




                                                                                                                   Annual average allocation weight
                                                                                                                 0.6
 Profitability/quality

Investment/issuance                                                                                              0.4

   Safety/downside
                                                                                                                 0.2
     Liquidity/limits

       Expectations                                                                                              0.0

                         1985   1989   1993   1997   2001         2005        2009   2013   2017   2021   2024
                                                            Prediction year

Figure 2: State-dependent family allocation weights. The heatmap reports annual average family
allocation shares from the mixture-of-experts rule in the 1985–2024 out-of-sample prediction period.
Rows are economic anomaly families and columns are prediction years. Darker cells indicate larger
capital shares, showing that macro-regime memory reallocates capital across characteristic families
rather than holding a fixed anomaly mix.




                                                            43

===== PAGE 44 =====

                                  104




Growth of one dollar, log scale
                                  103



                                  102



                                  101



                                  100
                                        1985   1990   1995              2000        2005              2010              2015   2020   2025

                                                             Mixture of experts     Macro ridge              Trailing Sharpe
                                                             Validation ensemble    Factor momentum          Equal weight

       Figure 3: Cumulative allocation performance. The figure plots out-of-sample growth of one
       dollar for selected family-allocation rules using monthly returns from the 1985–2024 walk-forward
       prediction sample. The log scale makes long-horizon differences in allocation value visible while
       preserving drawdowns and periods of slower compounding.




                                                                                   44

===== PAGE 45 =====

   Ridge plus macro residual                                                                                             0.073


         Pooled all-212 ridge                                                                                            0.073


       Decay-weighted ridge                                                                                             0.072


           Ridge-decay blend                                                                                           0.072


Ridge plus validation residual                                                                                         0.072


       Family-balanced ridge                                                                                           0.071


                  SGD Huber                                                                                  0.066


              SGD elastic net                                                                        0.059


  Neural network benchmark                                                                 0.053


                             0.00   0.01   0.02   0.03            0.04              0.05           0.06         0.07
                                                  Mean monthly cross-sectional IC

Figure 4: Stock-level all-characteristic benchmark evidence. Bars report mean monthly cross-
sectional information coefficients for pooled all-212, macro-residual, decayed, family-balanced, and
flexible stock-level benchmarks over the common prediction sample. The pooled all-characteristic
ridge remains a demanding stock-level benchmark, which frames the paper’s contribution as state-
dependent family allocation rather than generic model complexity.




                                                  45

===== PAGE 46 =====

           Valuation       +0.010       +0.007           +0.013          -0.005           -0.010   +0.008      +0.014            -0.015
                                                                                                                                          0.03

       Continuation         -0.006      +0.015           -0.004          -0.012          +0.011    +0.004      -0.001            -0.031
                                                                                                                                          0.02

          Correction        -0.023      -0.007           +0.002          -0.011          +0.017     -0.017     -0.013            +0.000




                                                                                                                                                 High-state minus low-state return
                                                                                                                                          0.01

 Profitability/quality      -0.001      +0.012           +0.018          -0.003          +0.011     -0.004     -0.015            -0.020

                                                                                                                                          0.00
Investment/issuance        +0.001       -0.005           -0.007          +0.002           -0.003    -0.003     +0.002            +0.011

                                                                                                                                           0.01
   Safety/downside         +0.003       -0.007           -0.017          -0.003           -0.018   +0.009      +0.024            +0.014


                                                                                                                                           0.02
     Liquidity/limits       -0.006      +0.000           +0.001          +0.005          +0.014     -0.012     -0.032            +0.003


                                                                                                                                           0.03
       Expectations         -0.007      +0.005           +0.012          -0.007          +0.010     -0.003     -0.002            -0.023


                             it             th        tion            idity                 s      Risk           d           tion
                         Cred        Grow        Infla            Liqu                 Rate                  Tren
                                                                                                                        Valu
                                                                                                                             a


Figure 5: Regime-family payoff map. Cells report high-state minus low-state family returns by
macro block and anomaly family. The color scale is centered at zero, so red cells indicate higher
returns in high macro states and blue cells indicate higher returns in low macro states. The
liquidity/limits row and market-trend column contain the central channel discussed in the text.




                                                                                  46

===== PAGE 47 =====

   Beta Neutral



       Ex Micro



Industry Neutral



   Large Stocks



    Liquid Proxy



  Raw All Firms
                     2             0                        2                      4                  6   8
                                  t-statistic; liquidity/limits shown as low-trend minus high-trend

                                         Liquidity/limits × trend       Continuation × valuation

Figure 6: Liquidity/limits mechanism across universes. Dots report t-statistics across cross-
sectional samples and controls. The liquidity/limits × trend statistic is transformed so positive
values mean stronger low-trend liquidity/limits payoffs; continuation × valuation is plotted as the
comparison channel. The two series are identified in the legend below the plot.




                                                        47

===== PAGE 48 =====

 Micro bottom 20        +2.11                     +1.98                     +1.78

                                                                                               6

Outside microcaps       +4.58                     +3.73                     +6.69
                                                                                               4




                                                                                                   Low-trend minus high-trend t-statistic
        Middle 60       +3.67                     +3.02                     +4.90
                                                                                               2


       Upper half       +1.58                     +1.72                     +3.38              0


                                                                                                   2
      Upper third       +0.54                     -0.03                     +1.77

                                                                                                   4
     Large top 20       -0.53                     -1.29                     -0.11

                                                                                                   6

     Mega top 10        -1.57                     -2.09                     -1.54

                      EW returns                VW returns                   IC

Figure 7: Liquidity/limits capacity frontier. The heatmap reports low-trend minus high-trend
t-statistics for the liquidity/limits mechanism across market-capacity regions and return or ranking
outcomes. Positive cells indicate stronger low-trend payoffs. The gradient shows economic scope:
the mechanism is strongest away from the deepest-capacity largest stocks and attenuates where
arbitrage capacity is most elastic.




                                                48

===== PAGE 49 =====

                                                                                                                                          313
         All firms                                                                                                            274

                                                                                     103
 Micro bottom 20                                                                    99

                                                                                                            171
Outside microcaps                                                                                 146

                                                                                                 142
        Middle 60                                                                      114

                                                                50
       Upper half                                                    60

                                                      17
      Upper third                            -1

                                       -18
     Large top 20           -52

                           -58
     Mega top 10 -93

                     100          50              0        50                 100               150               200   250         300
                                                      Low-trend minus high-trend return, bps per month

                                                                     Equal-weight            Value-weight

Figure 8: Economic magnitudes by market-capacity region. Bars report low-trend minus high-
trend returns in basis points per month for equal-weighted and value-weighted portfolios across
market-capacity regions. Positive bars indicate stronger low-trend liquidity/limits payoffs. The or-
dered attenuation toward the largest names is the capacity shape predicted by a limits-to-arbitrage
mechanism.




                                                                       49

===== PAGE 50 =====

Funding Statement
The author received no external funding for this study.


Conflict of Interest Statement
The author declares no conflict of interest.


Disclosure Statement
The author has no relevant financial or non-financial interests to disclose.




                                               50

===== PAGE 51 =====

                     Internet Appendix
               When Do Anomalies Deserve Capital?

                                  Anonymous Author(s)

                                       June 17, 2026


   This Internet Appendix reports construction detail and additional empirical evidence
supporting the main paper. Appendix A documents data construction and timing. Appendix
B expands anomaly-family predictability and allocation evidence. Appendix C reports full
212-characteristic and stock-level evidence. Appendix D reports mechanism and capacity
evidence. Appendix E reports state-specificity and model-comparison evidence. Appendix F
maps evidence blocks to the paper’s main interpretation. Appendix G reports the additional
source-classification, publication-coverage, and episode-decomposition exhibits.


Appendix A. Data Construction and Timing
Appendix A documents how the sample, characteristic panel, macro-state variables, and
portfolio-formation timing are constructed. The walk-forward calendar begins with an initial
10-year training window and a fixed 12-year validation window, then rolls forward by pre-
diction year. The macro-state variables are grouped into economically interpretable blocks
and aligned to the information set available at portfolio formation.
   The section also reports the fixed mapping from the 212 OpenAP characteristics to eco-
nomic anomaly families. That mapping is what lets family weights be interpreted as capital
shares across valuation, continuation, profitability/quality, investment, safety, liquidity, cor-
rection, and expectations information rather than as anonymous model weights.




                                               1

===== PAGE 52 =====

    The first appendix table documents the exact real-time learning calendar. It shows how the prediction year moves forward while the training
    history expands and the validation window keeps a stable model-selection length.
                                                       Table IA.1. Annual Walk-Forward Windows


                                       Prediction year Months Train start Train end Validation start Validation end
                                                1985        12       1963      1972            1973           1984
                                                1986        12       1963      1973            1974           1985
                                                1987        12       1963      1974            1975           1986
                                                1988        12       1963      1975            1976           1987
                                                1989        12       1963      1976            1977           1988
                                                1990        12       1963      1977            1978           1989
                                                1991        12       1963      1978            1979           1990
                                                1992        12       1963      1979            1980           1991
                                                1993        12       1963      1980            1981           1992
                                                1994        12       1963      1981            1982           1993
                                                1995        12       1963      1982            1983           1994
                                                1996        12       1963      1983            1984           1995
                                                1997        12       1963      1984            1985           1996
                                                1998        12       1963      1985            1986           1997
                                                1999        12       1963      1986            1987           1998
                                                2000        12       1963      1987            1988           1999
                                                2001        12       1963      1988            1989           2000
                                                2002        12       1963      1989            1990           2001
                                                2003        12       1963      1990            1991           2002
2                                               2004        12       1963      1991            1992           2003
                                                2005        12       1963      1992            1993           2004
                                                2006        12       1963      1993            1994           2005
                                                2007        12       1963      1994            1995           2006
                                                2008        12       1963      1995            1996           2007
                                                2009        12       1963      1996            1997           2008
                                                2010        12       1963      1997            1998           2009
                                                2011        12       1963      1998            1999           2010
                                                2012        12       1963      1999            2000           2011
                                                2013        12       1963      2000            2001           2012
                                                2014        12       1963      2001            2002           2013
                                                2015        12       1963      2002            2003           2014
                                                2016        12       1963      2003            2004           2015
                                                2017        12       1963      2004            2005           2016
                                                2018        12       1963      2005            2006           2017
                                                2019        12       1963      2006            2007           2018
                                                2020        12       1963      2007            2008           2019
                                                2021        12       1963      2008            2009           2020
                                                2022        12       1963      2009            2010           2021
                                                2023        12       1963      2010            2011           2022
                                                2024        11       1963      2011            2012           2023

    Notes: The table reports the annual prediction calendar. Training expands through time and the validation window retains a fixed 12-year
    length.

===== PAGE 53 =====

    The second table gives the macro-state ingredients. It is useful for readers who want to see which economic forces enter the regime-memory
    allocation rule.
                                                             Table IA.2. Macro-State Blocks


                                       Series                 Identifier            Block       Frequency Timing lag
                                       Cpi                    CPIAUCSL              Inflation   Monthly    0 months
                                       Pce                    PCEPI                 Inflation   Monthly    0 months
                                       Core cpi               CPILFESL              Inflation   Monthly    0 months
                                       Industrial output      INDPRO                Growth      Monthly    0 months
                                       Unemployment           UNRATE                Growth      Monthly    0 months
                                       Payrolls               PAYEMS                Growth      Monthly    0 months
                                       Recession              USREC                 Growth      Monthly    0 months
                                       Fed funds              FEDFUNDS              Rates       Monthly    0 months
                                       Tbill 3m               TB3MS                 Rates       Monthly    0 months
                                       Treasury 10y           GS10                  Rates       Monthly    0 months
                                       Treasury 2y            GS2                   Rates       Monthly    0 months
                                       Baa 10y spread         BAA10Y                Credit      Monthly    0 months
                                       Corp oas               BAMLC0A0CM            Credit      Daily      0 months
                                       Financial stress       STLFSI4               Liquidity   Weekly     0 months
                                       Vix                    VIXCLS                Risk        Daily      0 months
                                       Sp500                  SP500                 Trend       Daily      0 months
                                       Market ret             market ret            Trend       Monthly    0 months
                                       Market vol proxy       market vol proxy      Risk        Monthly    0 months
                                       Cs dispersion          cs dispersion         Risk        Monthly    0 months
3                                      Aggregate valuation    aggregate valuation   Valuation   Monthly    0 months
                                       Aggregate liquidity    aggregate liquidity   Liquidity   Monthly    0 months
                                       Market trend 12m       market trend 12m      Trend       Monthly    0 months
                                       Market drawdown 12m    market drawdown 12m   Risk        Monthly    0 months

    Notes: The table lists the macro series and economic blocks used to form macro-state histories.

===== PAGE 54 =====

This table shows how the full characteristic panel is organized into interpretable economic sleeves. The
mapping is fixed before prediction and gives each family weight a clear economic meaning.
                             Table IA.3. Signal Family Mapping


 Family                  Signals Positive orientation Negative orientation Share of panel (%)
 Valuation                    36                       35                     1                   17.0
 Continuation                 27                       26                     1                   12.7
 Correction                    4                        1                     3                    1.9
 Profitability/quality        27                       23                     4                   12.7
 Investment/issuance          46                       20                    26                   21.7
 Safety/downside              26                        2                    24                   12.3
 Liquidity/limits             21                        4                    17                    9.9
 Expectations                 25                       21                     4                   11.8

Notes: The table summarizes the fixed mapping of the 212 characteristics into economic families and
signal orientations.




                                                   4

===== PAGE 55 =====

    The fourth table documents information timing. It helps the reader verify that macro states are aligned with the portfolio-formation information
    set.
                                                   Table IA.4. Real-Time Macro Information Timing


      Macro series        Identifier   Vintage months Nonmissing values Real-time values Conservative values First vintage Last vintage Timing violations
      Baa 10y spread      BAA10Y                  743                466               0                 743    1963-01-31   2024-11-30   0
      Corp oas            BAMLC0A0CM              743                 18               0                 743    1963-01-31   2024-11-30   0
      Cpi                 CPIAUCSL                743                743             629                 114    1963-01-31   2024-11-30   0
      Core cpi            CPILFESL                743                743             336                 407    1963-01-31   2024-11-30   0
      Fed funds           FEDFUNDS                743                743             336                 407    1963-01-31   2024-11-30   0
      Treasury 10y        GS10                    743                743             336                 407    1963-01-31   2024-11-30   0
      Treasury 2y         GS2                     743                581             336                 407    1963-01-31   2024-11-30   0
      Industrial output   INDPRO                  743                743             743                   0    1963-01-31   2024-11-30   0
      Payrolls            PAYEMS                  743                743             743                   0    1963-01-31   2024-11-30   0
      Pce                 PCEPI                   743                743             292                 451    1963-01-31   2024-11-30   0
      Sp500               SP500                   743                102               0                 743    1963-01-31   2024-11-30   0
      Financial stress    STLFSI4                 743                372               0                 743    1963-01-31   2024-11-30   0
      Tbill 3m            TB3MS                   743                743             336                 407    1963-01-31   2024-11-30   0
      Unemployment        UNRATE                  743                743             743                   0    1963-01-31   2024-11-30   0
      Recession           USREC                   743                743             123                 620    1963-01-31   2024-11-30   0
      Vix                 VIXCLS                  743                419               0                 743    1963-01-31   2024-11-30   0

    Notes: The table reports the information timing used for macro states. The construction aligns macro information with the information
5   available at portfolio formation.

===== PAGE 56 =====

    This table summarizes the dependence structure across macro blocks. It keeps the appendix exhibit-based while documenting that the state
    variables are economically related rather than interchangeable.
                                                           Table IA.5. Macro-State Correlations


                                        Row block Credit Growth Inflation Liquidity Rates Risk Trend Valuation
                                        Credit      0.56     0.12    0.07     0.21   0.16   0.18   0.12   0.08
                                        Growth      0.12     0.26    0.12     0.09   0.17   0.09   0.10   0.10
                                        Inflation   0.07     0.12    0.35     0.12   0.20   0.06   0.03   0.20
                                        Liquidity   0.21     0.09    0.12     0.33   0.13   0.15   0.12   0.34
                                        Rates       0.16     0.17    0.20     0.13   0.44   0.08   0.08   0.18
                                        Risk        0.18     0.09    0.06     0.15   0.08   0.32   0.26   0.07
                                        Trend       0.12     0.10    0.03     0.12   0.08   0.26   0.48   0.07
                                        Valuation   0.08     0.10    0.20     0.34   0.18   0.07   0.07   0.64

    Notes: Entries are mean absolute correlations across transformed macro-state series within each block pair.




6

===== PAGE 57 =====

                                                                                                               1.00
 Inflation       +0.35        +0.09      +0.19       -0.01         -0.10    +0.00      -0.01           -0.19

                                                                                                               0.75
  Growth         +0.09        +0.10      +0.09       +0.03         -0.00    +0.02      -0.02           -0.05

                                                                                                               0.50
    Rates        +0.19        +0.09      +0.44       -0.15         -0.12    -0.04      -0.05           -0.17

                                                                                                               0.25
   Credit        -0.01        +0.03      -0.15       +0.53         +0.19    +0.08      -0.05          +0.07


                                                                                                                      Correlation
                                                                                                               0.00
 Liquidity       -0.10        -0.00      -0.12       +0.19         +0.31    +0.05      -0.05          +0.32

                                                                                                                0.25
     Risk        +0.00        +0.02      -0.04       +0.08         +0.05    +0.23      +0.15          +0.00

                                                                                                                0.50
    Trend        -0.01        -0.02      -0.05       -0.05         -0.05    +0.15      +0.44          +0.07

                                                                                                                0.75
Valuation        -0.19        -0.05      -0.17       +0.07         +0.32    +0.00      +0.07          +0.64

                                                                                                                1.00
                 ion          wth         es          it            ty     Risk          d               n
             flat          ro         Rat        Cred           uidi                Tren            atio
         In              G                                   Liq                             Valu
Figure IA.1. Macro-state correlation structure. The heatmap reports correlations among
macro-state blocks used by the allocation and mechanism tests.




                                                                   7

===== PAGE 58 =====

Appendix B. Anomaly-Family Predictability and Allo-
cation Detail
Appendix B expands the family-level allocation evidence behind the main tables. The ex-
hibits report baseline family predictability, family-sleeve portfolio returns, allocation-rule
variants, the distribution of family weights, and the relation between those weights and
macro-state blocks.
  This section establishes that macro-regime memory reallocates capital across economically
named anomaly families in the out-of-sample period. The weight and return exhibits show
both the economic magnitude of allocation and the state dependence of the family shares.




                                              8

===== PAGE 59 =====

    This table shows that family histories contain predictive content before the full allocation tests. It motivates the use of family-level state
    histories in the allocation rule.
                                                Table IA.6. Baseline Family Predictability


                     Allocation rule                 Future return slope Return t Future IC slope IC t Family-months
                     Attention memory                                  0.01       2.88             0.01 3.06               3832
                     Bayesian dynamic                                  0.01       4.17             0.02 3.94               3832
                     Contextual bandit                                 0.01       2.86             0.01 2.99               3832
                     Ensemble                                          0.01       3.73             0.02 3.13               3832
                     Equal weight                                      0.00       0.00             0.00 0.00               3832
                     EWMA sleeve performance                           0.00       1.27             0.01 0.86               3832
                     Factor momentum                                   0.01       3.10             0.01 2.34               3832
                     Macro analog                                      0.01       2.86             0.01 2.99               3832
                     Macro ridge                                       0.01       4.06             0.02 3.84               3832
                     Mixture of experts                                0.01       4.24             0.02 4.23               3832
                     Regime probability                               -0.00      -0.36            -0.01 -0.72              3832
                     Trailing ic                                       0.00       0.96             0.01 0.94               3832
9
    Notes: The table reports sleeve-level predictive relationships for family returns and ICs.

===== PAGE 60 =====

     This table expands the portfolio evidence behind the main allocation results. It connects allocation performance to long-short portfolio returns
     and factor-adjusted returns.
                                                        Table IA.7. Family Sleeve Return Evidence


                              Allocation rule           EW return (%) EW t VW return (%) VW t Alpha (%) Alpha t Turnover
                              Mixture of experts                 2.51   9.71          1.39   5.36     2.07    7.63      0.61
                              Bayesian dynamic                   2.43   9.39          1.36   5.32     1.94    6.74      0.57
                              Validation ensemble                2.42   9.46          1.26   4.82     1.88    6.62      0.61
                              Ensemble                           2.28   8.54          1.12   4.06     1.85    6.67      0.62
                              Macro ridge                        2.14   7.89          1.07   3.85     1.73    6.39      0.66
                              EWMA sleeve performance            2.16   7.98          1.16   4.10     1.68    6.83      0.41
                              Factor momentum                    2.20   8.01          1.17   4.14     1.64    6.68      0.43
                              Regime probability                 2.05   7.32          1.00   3.43     1.47    7.73      0.53
                              Trailing ic                        2.11   7.27          1.03   3.45     1.56    7.41      0.42
                              Contextual bandit                  1.93   7.51          0.87   3.30     1.40    5.88      0.65
                              Macro analog                       1.93   7.51          0.87   3.30     1.40    5.88      0.65
                              Trailing Sharpe                    1.89   7.56          1.05   4.10     1.52    6.23      0.37

     Notes: The table reports long-short family allocation portfolios under equal and value weighting, with factor-adjusted alpha.



10

===== PAGE 61 =====

     This table gives the broader allocation-rule comparison. It shows that the leading results are part of a wider set of state-dependent allocation
     specifications.
                                                              Table IA.8. Allocation Rule Variants


                          Allocation rule           Version               Mean return (%) NW t Sharpe Drawdown (%) Concentration
                          Mixture of experts        Nonnegative softmax              2.13  9.21      1.51     -22.71        0.77
                          Bayesian dynamic          Nonnegative softmax              2.05  8.98      1.44     -23.97        0.71
                          Validation ensemble       Nonnegative softmax              2.08  9.09      1.43     -31.83        0.75
                          Ensemble                  Nonnegative softmax              1.95  8.05      1.36     -32.74        0.75
                          Macro ridge               Nonnegative softmax              1.82  7.60      1.30     -26.29        0.75
                          Factor momentum           Nonnegative softmax              1.82  7.62      1.17     -35.38        0.68
                          Regime probability        Nonnegative softmax              1.90  7.01      1.16     -48.30        0.89
                          Trailing Sharpe           Nonnegative softmax              1.70  7.51      1.16     -41.52        0.73
                          Macro analog              Nonnegative softmax              1.62  6.91      1.14     -32.24        0.74
                          Contextual bandit         Nonnegative softmax              1.62  6.91      1.14     -32.24        0.74
                          Trailing ic               Nonnegative softmax              1.69  6.98      1.12     -40.00        0.62
                          Trailing return           Nonnegative softmax              1.74  7.19      1.12     -41.55        0.73
                          EWMA sleeve performance   Nonnegative softmax              1.75  7.16      1.11     -41.35        0.67
                          Attention memory          Nonnegative softmax              1.48  6.56      1.03     -30.56        0.76
                          Equal weight              Nonnegative softmax              0.38  5.81      0.94     -13.25        0.12
                          Mixture of experts        Long short l1                    1.44 10.23      1.57     -18.87        0.18
                          Regime probability        Long short l1                    1.19  8.85      1.57     -17.00        0.15
                          Validation ensemble       Long short l1                    1.41 10.00      1.53     -17.60        0.18

11   Notes: Rows report allocation-rule variants evaluated on the same prediction sample.

===== PAGE 62 =====

     This table provides the table version of the allocation-weight evidence. It shows how much each family receives on average and how widely
     the allocation moves through time.
                                           Table IA.9. Family Weight Distribution Over Time


                     Family                  Mean (%) Std. dev. (%) Min (%) P25 (%) Median (%) P75 (%) Max (%)
                     Continuation                 60.74            40.45       0.00     12.80      80.08     98.33     100.00
                     Correction                    0.60             4.71       0.00      0.00       0.00      0.03      77.32
                     Expectations                  1.98             4.79       0.00      0.05       0.39      1.82      55.00
                     Investment/issuance           0.27             2.66       0.00      0.00       0.00      0.00      51.00
                     Liquidity/limits              3.64            15.81       0.00      0.00       0.00      0.07      99.98
                     Profitability/quality        14.40            24.34       0.00      0.10       1.81     17.48      99.77
                     Safety/downside               0.93             7.24       0.00      0.00       0.00      0.00      99.12
                     Valuation                    17.44            30.22       0.00      0.02       0.87     19.45      99.94

     Notes: The table reports the time-series distribution of mixture-of-experts family weights.



12

===== PAGE 63 =====

     This table connects allocation weights to macro-state blocks. It helps interpret the family weights as state-dependent capital shares rather
     than static style tilts.
                                               Table IA.10. Family Weight Distribution by Macro State


                                                                        Family


     Notes: Entries are correlations between mixture-of-experts family weights and macro-state blocks.




13

===== PAGE 64 =====

       Continuation


 Profitability/quality


           Valuation


       Expectations


     Liquidity/limits


          Correction


Investment/issuance


   Safety/downside

                     0.0   0.2        0.4                      0.6      0.8   1.0
                                            Monthly allocation weight

Figure IA.2. Distribution of family allocation weights. The boxplots summarize the
monthly distribution of mixture-of-experts capital shares across anomaly families.




                                            14

===== PAGE 65 =====

This table summarizes the signal-level content within each family. It shows that the family layer
preserves broad characteristic information rather than collapsing the panel into a single style.
             Table IA.11. Signal Composition Within Anomaly Families


             Family                  Signals Average IC Average IC t Max signal t
             Continuation                27            0.01          5.98          13.63
             Correction                   4           -0.00          0.08           7.53
             Expectations                25            0.00          3.67          13.04
             Investment/issuance         46           -0.00         -1.17           7.76
             Liquidity/limits            21           -0.00         -1.76           5.80
             Profitability/quality       27            0.01          3.51          11.92
             Safety/downside             26           -0.01         -2.97           3.46
             Valuation                   36            0.01          4.26          12.58

Notes: The table summarizes signal-level cross-sectional content within each family.




                                                 15

===== PAGE 66 =====

Appendix C. Full 212-Characteristic and Stock-Level
Evidence
Appendix C brings the full characteristic panel and the direct stock-level prediction layer into
the evidence set. The hierarchical exhibits apply family allocation weights to the complete
212-signal panel, while the stock-level exhibits compare the allocation object with pooled
all-characteristic ridge, macro-residual variants, and factor-adjusted return evidence.
   The section is designed to separate two claims. The paper’s contribution is state-
dependent allocation across economic families, and the pooled all-212 ridge remains a
demanding direct stock-level benchmark. Reading both layers together shows that the
allocation evidence has breadth in the full panel while the benchmark evidence anchors the
interpretation.




                                              16

===== PAGE 67 =====

     This table expands the full 212-characteristic evidence. It shows how each allocation rule behaves when family weights are applied to the
     complete signal panel.
                                                   Table IA.12. Full 212-Signal Hierarchical Layer Detail


                             Allocation rule           Mean IC    IC t Incremental IC Incremental t EW L-S (%) Alpha (%) Alpha t
                             Mixture of experts           0.05   11.02          0.02         6.25        2.40       1.89    7.63
                             Bayesian dynamic             0.05   11.14          0.02         6.14        2.38       1.82    6.56
                             Validation ensemble          0.05   10.78          0.02         5.19        2.29       1.68    5.92
                             Macro ridge                  0.05    9.93          0.02         5.02        2.24       1.73    8.36
                             Ensemble                     0.05   10.25          0.02         4.68        2.21       1.61    6.46
                             Equal weight                 0.05    7.30          0.01         3.36        1.60       0.84    4.31
                             EWMA sleeve performance      0.04    8.81          0.01         3.68        1.98       1.26    5.41
                             Contextual bandit            0.04    8.77          0.01         3.58        1.95       1.24    5.54
                             Macro analog                 0.04    8.77          0.01         3.58        1.95       1.24    5.54
                             Factor momentum              0.04    8.35          0.01         3.42        2.06       1.34    5.35
                             Trailing return              0.04    8.57          0.01         3.33        1.86       1.22    5.28
                             Trailing ic                  0.04    7.93          0.01         3.03        1.84       1.12    4.98
                             Trailing Sharpe              0.04    9.19          0.01         3.44        1.84       1.27    4.86
                             Attention memory             0.04    8.31          0.01         2.92        1.80       1.12    5.27
                             Regime probability           0.04    7.89          0.01         2.46        1.77       1.05    5.67

     Notes: The table reports the full set of hierarchical 212-signal allocation results.

17

===== PAGE 68 =====

     This table translates the hierarchical ranking evidence into portfolio returns. It complements IC evidence by showing long-short spreads and
     factor-adjusted performance.
                                                   Table IA.13. Hierarchical Decile Portfolio Evidence


                                 Allocation rule           EW L-S (%) EW t VW L-S (%) VW t Alpha (%) Alpha t Months
                                 Mixture of experts              2.40   8.84        1.46   4.46      1.89    7.63   479
                                 Bayesian dynamic                2.38   8.94        1.57   4.98      1.82    6.56   479
                                 Validation ensemble             2.29   8.83        1.40   4.39      1.68    5.92   479
                                 Macro ridge                     2.24   7.86        1.44   4.15      1.73    8.36   479
                                 Ensemble                        2.21   8.32        1.30   3.96      1.61    6.46   479
                                 Equal weight                    1.60   4.28        1.14   2.68      0.84    4.31   479
                                 EWMA sleeve performance         1.98   6.49        1.22   3.35      1.26    5.41   479
                                 Contextual bandit               1.95   6.67        1.04   3.39      1.24    5.54   479
                                 Macro analog                    1.95   6.67        1.04   3.39      1.24    5.54   479
                                 Factor momentum                 2.06   6.65        1.24   3.32      1.34    5.35   479
                                 Trailing return                 1.86   6.01        1.07   2.88      1.22    5.28   479
                                 Trailing ic                     1.84   5.32        1.03   2.65      1.12    4.98   479
                                 Trailing Sharpe                 1.84   6.46        0.90   2.72      1.27    4.86   479
                                 Attention memory                1.80   6.31        0.94   2.98      1.12    5.27   479
                                 Regime probability              1.77   5.44        0.97   2.39      1.05    5.67   479

     Notes: The table reports decile long-short returns and factor alphas for the hierarchical 212-signal layer.

18

===== PAGE 69 =====

                                  104




Growth of one dollar, log scale
                                  103



                                  102



                                  101



                                  100
                                        1985   1990   1995   2000            2005             2010        2015   2020   2025


                                                              Equal weight          Mixture of experts
                                                              Macro ridge           Validation ensemble

       Figure IA.3. Hierarchical full-characteristic portfolio evidence. The figure plots cumula-
       tive long-short performance for the hierarchical 212-signal portfolio layer under selected allocation
       rules.




                                                                         19

===== PAGE 70 =====

     This table reports stock-level prediction evidence for allocation-rule signals. It helps separate family allocation from direct stock-level ranking.
                                                  Table IA.14. Stock-Level IC and Fama-MacBeth Detail


                               Allocation rule           Mean IC     IC t Incremental IC Incremental t FMB slope FMB t Months
                               Mixture of experts            0.05   11.46          0.02        6.10        0.03   8.56     479
                               Validation ensemble           0.05   11.52          0.02        6.00        0.03   9.48     479
                               Bayesian dynamic              0.05   11.16          0.02        5.86        0.03   8.61     479
                               Trailing ic                   0.04    9.94          0.02        6.07        0.03   7.42     479
                               EWMA sleeve performance       0.04    9.78          0.02        5.31        0.03   7.92     479
                               Ensemble                      0.04    9.99          0.02        5.11        0.03   7.68     479
                               Factor momentum               0.04    9.64          0.02        4.97        0.03   7.23     479
                               Trailing return               0.04   10.14          0.02        5.30        0.02   8.13     479
                               Regime probability            0.04    9.41          0.02        5.36        0.02   6.98     479
                               Macro ridge                   0.04    8.92          0.02        3.79        0.03   7.48     479
                               Trailing Sharpe               0.04   10.56          0.02        4.42        0.02   7.48     479
                               Contextual bandit             0.04    8.62          0.02        4.07        0.02   7.98     479
                               Macro analog                  0.04    8.62          0.02        4.07        0.02   7.98     479
                               Attention memory              0.03    7.81          0.01        2.73        0.02   6.43     479
                               Equal weight                  0.03    8.68          0.01        3.62        0.06   6.39     479

     Notes: The table reports stock-level IC and Fama–MacBeth evidence for allocation-rule signals.

20

===== PAGE 71 =====

     This table gives the full stock-level model comparison. The pooled all-212 ridge provides the benchmark that anchors direct stock prediction.
                                                          Table IA.15. Stock-Level Horse-Race Detail


                  Model                              Mean IC    IC t Incremental IC vs pooled ridge Incremental t EW L-S (%) Alpha (%) Alpha t
                  Ridge plus macro residual             0.07   15.63                         0.00         0.21         3.80       3.32   14.22
                  Pooled all-212 ridge                  0.07   15.93                         0.00         0.00         3.88       3.44   14.48
                  Decay-weighted ridge                  0.07   15.08                        -0.00        -0.13         3.82       3.44   13.08
                  Ridge-decay blend                     0.07   15.18                        -0.00        -0.74         3.80       3.39   13.42
                  Ridge plus validation residual        0.07   15.64                        -0.00        -0.67         3.77       3.31   13.62
                  Ridge plus macro-analog residual      0.07   15.59                        -0.00        -0.90         3.76       3.27   13.16
                  Ridge plus attention residual         0.07   15.71                        -0.00        -1.17         3.74       3.26   13.55
                  Ridge plus ensemble residual          0.07   15.69                        -0.00        -0.94         3.82       3.34   13.76
                  Family-balanced ridge                 0.07   16.32                        -0.00        -2.32         3.84       3.41   14.40
                  SGD Huber                             0.07   10.48                        -0.01        -1.77         3.24       2.53   12.62
                  SGD elastic net                       0.06   13.01                        -0.01        -4.25         3.30       2.97   11.41
                  Neural network benchmark              0.05    9.84                        -0.02        -5.15         2.83       2.42   10.41
                  Hierarchical validation ensemble      0.05   10.70                        -0.03        -7.39         2.29       1.68    5.92
                  Hierarchical macro ridge              0.05    9.83                        -0.03        -7.32         2.24       1.73    8.36
                  Hierarchical ensemble                 0.05   10.20                        -0.03        -7.26         2.21       1.61    6.46
                  Hierarchical macro analog             0.04    8.79                        -0.03        -7.60         1.95       1.24    5.54
                  Hierarchical attention memory         0.04    8.24                        -0.03        -8.01         1.80       1.12    5.27
                  Static 212 equal weight               0.03    9.42                        -0.04       -13.69         1.58       0.92    6.52

21   Notes: The table reports the complete stock-level model comparison used to benchmark direct stock ranking.

===== PAGE 72 =====

     This table collects factor-adjusted and controlled cross-sectional evidence in one place. It supports the main paper’s interpretation of ranking,
     portfolio, and alpha results.
                                                           Table IA.16. Factor-Adjusted Performance Detail


             Object                              Name                               Mean IC Controlled FMB t EW L-S (%) VW L-S (%) Alpha (%) Alpha t
             Stock-level or hierarchical model   Ridge plus macro residual             0.07            2.42        3.80        2.10      3.32   14.22
             Stock-level or hierarchical model   Pooled all-212 ridge                  0.07           12.83        3.88        2.09      3.44   14.48
             Stock-level or hierarchical model   Decay-weighted ridge                  0.07            2.56        3.82        1.82      3.44   13.08
             Stock-level or hierarchical model   Ridge-decay blend                     0.07            0.03        3.80        1.81      3.39   13.42
             Stock-level or hierarchical model   Ridge plus validation residual        0.07            2.21        3.77        2.01      3.31   13.62
             Stock-level or hierarchical model   Ridge plus macro-analog residual      0.07            2.76        3.76        1.90      3.27   13.16
             Stock-level or hierarchical model   Ridge plus attention residual         0.07            3.67        3.74        1.91      3.26   13.55
             Stock-level or hierarchical model   Ridge plus ensemble residual          0.07            2.42        3.82        2.09      3.34   13.76
             Stock-level or hierarchical model   Family-balanced ridge                 0.07           -1.62        3.84        2.06      3.41   14.40
             Stock-level or hierarchical model   SGD Huber                             0.07            0.72        3.24        2.24      2.53   12.62
             Stock-level or hierarchical model   SGD elastic net                       0.06            1.32        3.30        1.54      2.97   11.41
             Stock-level or hierarchical model   Neural network benchmark              0.05            2.71        2.83        1.77      2.42   10.41
             Stock-level or hierarchical model   Hierarchical validation ensemble      0.05            3.08        2.29        1.40      1.68    5.92
             Stock-level or hierarchical model   Hierarchical macro ridge              0.05            3.29        2.24        1.44      1.73    8.36
             Stock-level or hierarchical model   Hierarchical ensemble                 0.05            2.74        2.21        1.30      1.61    6.46
             Stock-level or hierarchical model   Hierarchical macro analog             0.04            2.38        1.95        1.04      1.24    5.54
             Stock-level or hierarchical model   Hierarchical attention memory         0.04            2.06        1.80        0.94      1.12    5.27
             Stock-level or hierarchical model   Static 212 equal weight               0.03            1.59        1.58        0.46      0.92    6.52
             Family allocation                   Mixture of experts                    0.00           10.59        2.51        1.39      2.07    7.63
22           Family allocation                   Bayesian dynamic                      0.00           10.44        2.43        1.36      1.94    6.74
             Family allocation                   Validation ensemble                   0.00           10.74        2.42        1.26      1.88    6.62
             Family allocation                   Ensemble                              0.00            9.44        2.28        1.12      1.85    6.67
             Family allocation                   Macro ridge                           0.00            8.17        2.14        1.07      1.73    6.39
             Family allocation                   EWMA sleeve performance               0.00            8.37        2.16        1.16      1.68    6.83
             Family allocation                   Factor momentum                       0.00            8.76        2.20        1.17      1.64    6.68
             Family allocation                   Regime probability                    0.00            6.85        2.05        1.00      1.47    7.73
             Family allocation                   Trailing ic                           0.00            6.82        2.11        1.03      1.56    7.41
             Family allocation                   Contextual bandit                     0.00            7.93        1.93        0.87      1.40    5.88
             Family allocation                   Macro analog                          0.00            7.93        1.93        0.87      1.40    5.88
             Family allocation                   Trailing Sharpe                       0.00            8.11        1.89        1.05      1.52    6.23
             Family allocation                   Trailing return                       0.00            7.38        1.99        1.05      1.57    7.02
             Family allocation                   Equal weight                          0.00            5.66        1.22        0.41      0.58    4.33
             Family allocation                   Attention memory                      0.00            6.50        1.71        0.71      1.23    5.13

     Notes: The table reports controlled Fama–MacBeth and factor-adjusted return evidence for allocation and benchmark objects.

===== PAGE 73 =====

                                  108

                                  107

                                  106




Growth of one dollar, log scale
                                  105

                                  104

                                  103

                                  102

                                  101

                                  100
                                        1985   1990   1995          2000                 2005          2010            2015   2020   2025

                                                             Pooled all-212 ridge               Static 212 equal weight
                                                             Ridge plus macro residual          Neural network benchmark
                                                             SGD Huber

       Figure IA.4. Stock-level benchmark portfolio evidence. The figure plots cumulative long-
       short performance for pooled all-212, macro-residual, flexible, and fixed stock-level benchmarks.




                                                                                  23

===== PAGE 74 =====

Appendix D. Mechanism, Payoff Surface, and Capacity
Evidence
Appendix D expands the mechanism evidence. The payoff-surface tables report family-by-
macro-block return and ranking spreads, the drop-one tables show the contribution of each
family to allocation returns, and the regime-local reliability tables describe where stock-level
ranking evidence changes across states.
   The central economic channel is liquidity/limits × trend. The section reports the mech-
anism across cross-sectional constructions, evaluates holdout behavior, and then links the
same channel to a market-capacity frontier. The resulting pattern gives the mechanism both
expected-return content and economic scope.




                                              24

===== PAGE 75 =====

     Tables IA.17A and IA.17B provide the full state-family payoff surface behind the main payoff table. The split keeps the evidence readable
     while preserving every macro-family cell.
                                            Table IA.17A. Regime-Family Payoff Cells: Credit Through Liquidity


                                Macro block Family                    High ret. (%) Low ret. (%) H-L ret. (%) Ret. t H-L IC     IC t
                                Credit        Continuation                    1.64          2.23        -0.59   -0.79   -0.01   -0.78
                                Credit        Correction                     -1.54          0.73        -2.27   -3.94   -0.03   -3.65
                                Credit        Expectations                    0.67          1.33        -0.66   -1.16   -0.01   -1.04
                                Credit        Investment/issuance            -0.75         -0.86       +0.12     0.36   -0.00   -0.14
                                Credit        Liquidity/limits               -0.23          0.34        -0.56   -1.17   -0.02   -2.05
                                Credit        Profitability/quality           1.51          1.60        -0.09   -0.15   -0.01   -0.91
                                Credit        Safety/downside                -1.26         -1.53       +0.26     0.39    0.01    0.67
                                Credit        Valuation                       1.78          0.76       +1.01     2.03    0.01    1.25
                                Growth        Continuation                    2.62          1.12       +1.50     2.04    0.02    2.37
                                Growth        Correction                     -0.82         -0.17        -0.65   -1.03   -0.00   -0.54
                                Growth        Expectations                    1.24          0.73       +0.51     0.93    0.01    1.19
                                Growth        Investment/issuance            -1.03         -0.50        -0.53   -1.71   -0.01   -1.75
                                Growth        Liquidity/limits               -0.16         -0.20       +0.04     0.07   -0.00   -0.07
                                Growth        Profitability/quality           2.08          0.88       +1.20     1.98    0.01    1.95
                                Growth        Safety/downside                -1.46         -0.78        -0.69   -0.93   -0.01   -1.16
                                Growth        Valuation                       1.60          0.91       +0.69     1.33    0.01    1.56
                                Inflation     Continuation                    2.14          2.55        -0.41   -0.59    0.01    0.76
                                Inflation     Correction                      0.12         -0.07       +0.19     0.34    0.01    0.57
                                Inflation     Expectations                    1.90          0.69       +1.21     2.37    0.02    2.62
25                              Inflation     Investment/issuance            -1.34         -0.68        -0.66   -2.17   -0.01   -2.37
                                Inflation     Liquidity/limits               -0.07         -0.21       +0.14     0.27    0.00    0.25
                                Inflation     Profitability/quality           2.85          1.03       +1.82     3.15    0.02    2.58
                                Inflation     Safety/downside                -2.79         -1.04        -1.74   -2.68   -0.03   -2.77
                                Inflation     Valuation                       1.84          0.50       +1.34     2.89    0.02    2.78
                                Liquidity     Continuation                    1.00          2.16        -1.15   -1.68   -0.02   -1.79
                                Liquidity     Correction                     -0.97          0.13        -1.10   -1.85   -0.01   -1.16
                                Liquidity     Expectations                    0.82          1.57        -0.75   -1.37   -0.01   -1.13
                                Liquidity     Investment/issuance            -0.81         -0.99       +0.18     0.58    0.00    0.29
                                Liquidity     Liquidity/limits               -0.17         -0.67       +0.50     1.04    0.01    0.61
                                Liquidity     Profitability/quality           1.56          1.85        -0.29   -0.52   -0.01   -1.23
                                Liquidity     Safety/downside                -1.60         -1.31        -0.29   -0.44   -0.01   -0.89
                                Liquidity     Valuation                       1.35          1.89        -0.54   -1.13   -0.02   -1.75

     Notes: The table reports the first half of the family-by-macro-block payoff surface.

===== PAGE 76 =====

     The second payoff table contains rates, risk, trend, and valuation states. The liquidity/limits × trend channel appears in this block and can
     be compared directly with other family-state combinations.
                                            Table IA.17B. Regime-Family Payoff Cells: Rates Through Valuation


                                Macro block Family                    High ret. (%) Low ret. (%) H-L ret. (%) Ret. t H-L IC     IC t
                                Rates         Continuation                    2.36          1.21       +1.15     1.65    0.02    1.92
                                Rates         Correction                      0.63         -1.06       +1.69     2.94    0.03    3.55
                                Rates         Expectations                    1.43          0.45       +0.98     1.94    0.02    2.09
                                Rates         Investment/issuance            -0.97         -0.66        -0.31   -1.07   -0.00   -0.81
                                Rates         Liquidity/limits                0.53         -0.88       +1.42     2.87    0.03    3.43
                                Rates         Profitability/quality           1.99          0.89       +1.10     1.92    0.02    2.62
                                Rates         Safety/downside                -2.09         -0.29        -1.80   -2.55   -0.03   -3.05
                                Rates         Valuation                       0.74          1.76        -1.02   -2.23   -0.01   -1.20
                                Risk          Continuation                    1.98          1.62       +0.35     0.50    0.00    0.03
                                Risk          Correction                     -1.51          0.19        -1.70   -2.78   -0.02   -2.11
                                Risk          Expectations                    0.74          1.09        -0.35   -0.67   -0.00   -0.34
                                Risk          Investment/issuance            -0.93         -0.58        -0.35   -1.20   -0.01   -1.35
                                Risk          Liquidity/limits               -1.14          0.07        -1.20   -2.45   -0.02   -2.53
                                Risk          Profitability/quality           1.09          1.46        -0.38   -0.64   -0.00   -0.64
                                Risk          Safety/downside                -0.67         -1.58       +0.91     1.28    0.01    0.96
                                Risk          Valuation                       1.64          0.86       +0.78     1.59    0.01    1.09
                                Trend         Continuation                    2.09          2.20        -0.11   -0.16   -0.01   -1.02
                                Trend         Correction                     -0.80          0.54        -1.35   -2.33   -0.02   -2.78
                                Trend         Expectations                    1.10          1.35        -0.25   -0.50   -0.01   -0.93
26                              Trend         Investment/issuance            -0.82         -0.99       +0.17     0.58    0.01    1.01
                                Trend         Liquidity/limits               -1.79          1.41        -3.20   -6.77   -0.06   -7.14
                                Trend         Profitability/quality           0.88          2.39        -1.51   -2.63   -0.02   -2.96
                                Trend         Safety/downside                -0.31         -2.69       +2.39     3.50    0.04    4.24
                                Trend         Valuation                       1.93          0.52       +1.41     2.87    0.02    2.51
                                Valuation     Continuation                   -0.03          3.07        -3.09   -4.76   -0.04   -4.82
                                Valuation     Correction                     -0.42         -0.46       +0.05     0.08    0.00    0.16
                                Valuation     Expectations                   -0.38          1.94        -2.32   -5.12   -0.04   -5.28
                                Valuation     Investment/issuance            -0.15         -1.29       +1.14     3.97    0.02    4.26
                                Valuation     Liquidity/limits               -0.02         -0.34       +0.32     0.69    0.00    0.32
                                Valuation     Profitability/quality           0.30          2.33        -2.03   -3.83   -0.03   -4.25
                                Valuation     Safety/downside                -0.45         -1.83       +1.38     2.20    0.02    2.34
                                Valuation     Valuation                       0.41          1.93        -1.52   -3.36   -0.04   -5.28

     Notes: The table reports the second half of the family-by-macro-block payoff surface.

===== PAGE 77 =====

     This table expands the lead liquidity/limits × trend mechanism. It shows the same economic channel across cross-sectional constructions and
     time-state partitions.
                                                      Table IA.18. Liquidity/Limits × Trend Across Controls


              Test group                     Construction       Low-high return (%) t-statistic High return (%) Low return (%) High months Low months
              Cross-sectional construction   Raw all firms                     3.13      7.41           -2.23           0.89         248         248
              Cross-sectional construction   Ex micro                          1.71      4.58           -1.45           0.25         248         248
              Cross-sectional construction   Large stocks                     -0.18     -0.53           -0.25          -0.43         248         248
              Cross-sectional construction   Liquid proxy                      1.71      4.58           -1.45           0.25         248         248
              Cross-sectional construction   Industry neutral                  2.76      7.06           -1.99           0.77         248         248
              Cross-sectional construction   Beta neutral                      3.00      7.24           -2.12           0.88         248         248
              Time-state construction        All months                        3.13      7.41           -2.23           0.89         248         248
              Time-state construction        Non crisis                        3.28      8.03           -2.35           0.93         201         201
              Time-state construction        Crisis                            3.27      2.45           -2.02           1.25          47          47
              Time-state construction        1960s                             3.54      3.22           -3.49           0.04          28          50
              Time-state construction        1970s                             2.54      1.77           -2.77          -0.23          40          40
              Time-state construction        1980s                             3.91      5.03           -1.93           1.97          40          40
              Time-state construction        1990s                             4.46      4.21           -2.26           2.20          40          40
              Time-state construction        2000s                             3.75      3.69           -2.90           0.86          40          40
              Time-state construction        2010s                             1.32      1.72           -0.91           0.41          40          40
              Time-state construction        2020s                             2.15      1.49           -1.11           1.04          20          20

     Notes: The table expands the lead mechanism across cross-sectional and time-state constructions. Positive low-high values indicate stronger
27   low-trend payoffs.

===== PAGE 78 =====

     This table places the lead mechanism beside the main comparison channel across the same constructions. It shows where the liquidity/limits
     channel is economically concentrated.
                                         Table IA.19. Mechanism Survival Across Cross-Sectional Constructions


                           Family-state pair          Construction       High-low return (%) t-statistic High return (%) Low return (%)
                           Continuation × Valuation   Raw all firms                    -1.18     -2.39             0.84            2.02
                           Continuation × Valuation   Ex micro                         -1.52     -2.94             0.48            2.00
                           Continuation × Valuation   Large stocks                     -0.88     -1.74             0.26            1.14
                           Continuation × Valuation   Liquid proxy                     -1.52     -2.94             0.48            2.00
                           Continuation × Valuation   Industry neutral                 -0.69     -2.02             0.56            1.24
                           Continuation × Valuation   Beta neutral                     -0.63     -1.76             1.13            1.76
                           Continuation × Valuation   All months                       -1.18     -2.39             0.84            2.02
                           Continuation × Valuation   Non crisis                       -0.89     -2.31             1.17            2.05
                           Continuation × Valuation   Crisis                           -4.21     -2.28            -2.06            2.15
                           Continuation × Valuation   1960s                            -0.64     -0.60             1.89            2.53
                           Continuation × Valuation   1970s                            -0.23     -0.21             2.17            2.41
                           Continuation × Valuation   1980s                           +1.41       1.84             2.75            1.35
                           Continuation × Valuation   1990s                           +2.16       2.19             4.63            2.47
                           Continuation × Valuation   2000s                            -4.17     -1.86            -1.19            2.99
                           Continuation × Valuation   2010s                            -1.53     -1.67             0.55            2.08
                           Continuation × Valuation   2020s                            -2.83     -1.63            -0.35            2.48
                           Liquidity/limits × Trend   Raw all firms                    -3.13     -7.41            -2.23            0.89
                           Liquidity/limits × Trend   Ex micro                         -1.71     -4.58            -1.45            0.25
                           Liquidity/limits × Trend   Large stocks                    +0.18       0.53            -0.25           -0.43
28                         Liquidity/limits × Trend   Liquid proxy                     -1.71     -4.58            -1.45            0.25
                           Liquidity/limits × Trend   Industry neutral                 -2.76     -7.06            -1.99            0.77
                           Liquidity/limits × Trend   Beta neutral                     -3.00     -7.24            -2.12            0.88
                           Liquidity/limits × Trend   All months                       -3.13     -7.41            -2.23            0.89
                           Liquidity/limits × Trend   Non crisis                       -3.28     -8.03            -2.35            0.93
                           Liquidity/limits × Trend   Crisis                           -3.27     -2.45            -2.02            1.25
                           Liquidity/limits × Trend   1960s                            -3.54     -3.22            -3.49            0.04
                           Liquidity/limits × Trend   1970s                            -2.54     -1.77            -2.77           -0.23
                           Liquidity/limits × Trend   1980s                            -3.91     -5.03            -1.93            1.97
                           Liquidity/limits × Trend   1990s                            -4.46     -4.21            -2.26            2.20
                           Liquidity/limits × Trend   2000s                            -3.75     -3.69            -2.90            0.86
                           Liquidity/limits × Trend   2010s                            -1.32     -1.72            -0.91            0.41
                           Liquidity/limits × Trend   2020s                            -2.15     -1.49            -1.11            1.04

     Notes: The table reports lead mechanism pairs across cross-sectional and time-state constructions using the original high-minus-low sign
     convention.

===== PAGE 79 =====

     Tables IA.20A and IA.20B evaluate how the allocation evidence changes when each family is omitted. The split reports every drop-one row
     while keeping the table readable.
                                        Table IA.20A. Family Drop-One Contribution Evidence: First Rule Group


                     Allocation rule    Omitted family          Full ret. (%) Full t Omit ret. (%) Omit t Contrib. (%) Contrib. t Weight (%)
                     Attention memory   Continuation                   1.48   6.56          0.86    4.34         0.62       3.78       36.08
                     Attention memory   Correction                     1.48   6.56          1.48    6.59        -0.00      -0.06        7.77
                     Attention memory   Expectations                   1.48   6.56          1.48    6.48        -0.00      -0.06        5.69
                     Attention memory   Investment/issuance            1.48   6.56          1.48    6.54        -0.01      -0.25        2.66
                     Attention memory   Liquidity/limits               1.48   6.56          1.57    6.83        -0.10      -1.52        6.86
                     Attention memory   Profitability/quality          1.48   6.56          1.41    6.25         0.06       1.15       16.06
                     Attention memory   Safety/downside                1.48   6.56          1.66    7.77        -0.18      -2.86        8.44
                     Attention memory   Valuation                      1.48   6.56          1.40    5.83         0.08       0.62       16.45
                     Ensemble           Continuation                   1.95   8.05          1.29    6.49         0.67       3.52       50.74
                     Ensemble           Correction                     1.95   8.05          1.93    7.88         0.02       0.90        3.11
                     Ensemble           Expectations                   1.95   8.05          1.98    8.12        -0.03      -2.32        4.16
                     Ensemble           Investment/issuance            1.95   8.05          1.92    7.87         0.03       1.53        1.27
                     Ensemble           Liquidity/limits               1.95   8.05          1.92    7.83         0.03       0.78        4.19
                     Ensemble           Profitability/quality          1.95   8.05          1.89    7.81         0.06       0.99       16.75
                     Ensemble           Safety/downside                1.95   8.05          2.04    8.82        -0.09      -1.84        2.07
                     Ensemble           Valuation                      1.95   8.05          1.94    7.70         0.01       0.13       17.72
                     Macro analog       Continuation                   1.62   6.91          1.02    4.97         0.60       3.54       39.58
                     Macro analog       Correction                     1.62   6.91          1.61    6.86         0.01       0.20        6.69
                     Macro analog       Expectations                   1.62   6.91          1.63    6.92        -0.01      -0.52        5.80
29                   Macro analog       Investment/issuance            1.62   6.91          1.63    6.97        -0.01      -0.65        2.15
                     Macro analog       Liquidity/limits               1.62   6.91          1.67    7.03        -0.05      -1.16        5.01
                     Macro analog       Profitability/quality          1.62   6.91          1.57    6.83         0.05       0.81       17.59
                     Macro analog       Safety/downside                1.62   6.91          1.72    7.73        -0.10      -2.09        5.34
                     Macro analog       Valuation                      1.62   6.91          1.56    6.46         0.06       0.52       17.84

     Notes: The table reports how allocation evidence changes when each family is omitted from the allocation set.

===== PAGE 80 =====

     The second drop-one table completes the family-contribution evidence. Together, the two tables distinguish broad family allocation from
     dependence on a single omitted sleeve.
                                       Table IA.20B. Family Drop-One Contribution Evidence: Second Rule Group


                     Allocation rule       Omitted family          Full ret. (%) Full t Omit ret. (%) Omit t Contrib. (%) Contrib. t Weight (%)
                     Macro ridge           Continuation                   1.82   7.60          1.32    6.79         0.50       3.50       42.16
                     Macro ridge           Correction                     1.82   7.60          1.84    7.61        -0.02      -1.14        3.77
                     Macro ridge           Expectations                   1.82   7.60          1.85    7.73        -0.03      -2.60        3.35
                     Macro ridge           Investment/issuance            1.82   7.60          1.82    7.59         0.00       0.04        1.39
                     Macro ridge           Liquidity/limits               1.82   7.60          1.73    6.92         0.09       1.32        9.50
                     Macro ridge           Profitability/quality          1.82   7.60          1.76    7.54         0.06       1.12       15.71
                     Macro ridge           Safety/downside                1.82   7.60          1.99    8.62        -0.17      -2.96        4.60
                     Macro ridge           Valuation                      1.82   7.60          1.80    6.89         0.01       0.12       19.52
                     Mixture of experts    Continuation                   2.13   9.21          1.49    7.65         0.64       3.05       60.74
                     Mixture of experts    Correction                     2.13   9.21          2.14    9.21        -0.01      -1.57        0.60
                     Mixture of experts    Expectations                   2.13   9.21          2.14    9.33        -0.02      -1.82        1.98
                     Mixture of experts    Investment/issuance            2.13   9.21          2.12    9.09         0.01       0.97        0.27
                     Mixture of experts    Liquidity/limits               2.13   9.21          2.09    9.07         0.04       1.28        3.64
                     Mixture of experts    Profitability/quality          2.13   9.21          2.10    9.30         0.03       0.53       14.40
                     Mixture of experts    Safety/downside                2.13   9.21          2.14    9.27        -0.01      -0.61        0.93
                     Mixture of experts    Valuation                      2.13   9.21          2.08    8.41         0.05       0.46       17.44
                     Validation ensemble   Continuation                   2.08   9.09          1.50    6.92         0.58       2.25       56.49
                     Validation ensemble   Correction                     2.08   9.09          2.05    8.91         0.02       0.75        2.71
                     Validation ensemble   Expectations                   2.08   9.09          2.09    9.13        -0.01      -1.03        2.64
30                   Validation ensemble   Investment/issuance            2.08   9.09          2.06    8.97         0.02       1.32        0.79
                     Validation ensemble   Liquidity/limits               2.08   9.09          2.01    8.71         0.07       1.41        3.57
                     Validation ensemble   Profitability/quality          2.08   9.09          2.08    9.08        -0.00      -0.10       15.85
                     Validation ensemble   Safety/downside                2.08   9.09          2.11    9.58        -0.03      -0.85        1.47
                     Validation ensemble   Valuation                      2.08   9.09          1.98    7.76         0.10       0.65       16.47

     Notes: The table reports how allocation evidence changes when each family is omitted from the allocation set.

===== PAGE 81 =====

           Valuation                                                                                                                 0.6




                                                                                                                                           Contribution to monthly return, percentage points
       Continuation                                                                                                                  0.4

          Correction
                                                                                                                                     0.2

 Profitability/quality
                                                                                                                                     0.0
Investment/issuance

                                                                                                                                      0.2
   Safety/downside


     Liquidity/limits                                                                                                                 0.4


       Expectations                                                                                                                   0.6

                               ory       mble           alog                 dge                      rts                      ble
                            mem      Ense          ro a
                                                       n               ro ri                of   expe                      nsem
                      ion                       Mac                 Mac                 ure                         ation
                                                                                                                          e
               Attent                                                              Mixt                      a li d
                                                                                                            V

Figure IA.5. Family drop-one contribution evidence. The heatmap reports how removing
each family changes allocation returns across model variants.




                                                               31

===== PAGE 82 =====

     This table reports regime-local benchmark evidence. It shows how stock-level models behave inside state-family regions, which helps locate
     where macro information changes cross-sectional ranking.
                                                          Table IA.21. Regime-Local Reliability


                     Macro block      Regime      Model                                 Mean IC   IC t Inc. IC Inc. t FMB t Months
                     Valuation        Low         Static 212 equal weight                   0.05 11.10   -0.05 -11.06    1.71   160
                     Risk             High        Static 212 equal weight                   0.02 4.37    -0.05 -9.69    -1.13   160
                     Liquidity        High        Static 212 equal weight                   0.02 3.59    -0.05 -8.30    -0.36   160
                     Inflation        High        Static 212 equal weight                   0.04 6.48    -0.05 -8.01     1.53   160
                     Credit           High        Static 212 equal weight                   0.03 4.95    -0.05 -9.21     1.09   160
                     Growth           Middle      Static 212 equal weight                   0.03 5.81    -0.05 -10.03   -0.09   159
                     Rates            Middle      Static 212 equal weight                   0.03 4.95    -0.05 -8.84    -0.02   159
                     Credit           Middle      Static 212 equal weight                   0.02 3.75    -0.04 -8.88    -0.42   159
                     Inflation        Low         Static 212 equal weight                   0.03 7.24    -0.04 -10.90    0.63   160
                     Trend            Low         Static 212 equal weight                   0.04 5.38    -0.04 -7.76     1.72   160
                     Growth           High        Static 212 equal weight                   0.04 7.47    -0.04 -9.36     2.71   160
                     Valuation        Low         Hierarchical macro ridge                  0.06 9.53    -0.04 -6.93     1.52   160
                     Valuation        Low         Hierarchical validation ensemble          0.06 9.44    -0.04 -7.38     1.56   160
                     Rates            Low         Static 212 equal weight                   0.02 4.31    -0.04 -7.29     0.63   160
                     Trend            High        Static 212 equal weight                   0.02 6.20    -0.04 -8.95     0.33   160
                     Trend            Middle      Static 212 equal weight                   0.03 6.02    -0.04 -7.75     0.38   159
                     Liquidity        Low         Static 212 equal weight                   0.04 9.52    -0.04 -7.49     2.29   160
                     Risk             Middle      Static 212 equal weight                   0.04 6.49    -0.04 -9.06     2.81   159
                     Valuation        Middle      Static 212 equal weight                   0.04 6.87    -0.04 -7.84     2.83   159
32                   Rates            High        Static 212 equal weight                   0.04 7.16    -0.04 -9.51     1.85   160
                     Liquidity        Middle      Static 212 equal weight                   0.03 6.12    -0.04 -9.83     1.60   159
                     Growth           Low         Static 212 equal weight                   0.02 4.48    -0.04 -5.84    -0.28   160
                     Risk             High        Hierarchical validation ensemble          0.04 5.28    -0.04 -4.34     0.39   160
                     Risk             Low         Static 212 equal weight                   0.03 5.82    -0.04 -6.94     1.20   160
                     Inflation        Middle      Static 212 equal weight                   0.02 4.29    -0.03 -7.12     0.54   159
                     Credit           Low         Static 212 equal weight                   0.04 7.74    -0.03 -7.21     2.96   160
                     Valuation        High        Static 212 equal weight                   0.01 1.34    -0.03 -6.43    -2.04   160
                     Risk             High        Hierarchical macro ridge                  0.04 5.33    -0.03 -5.16     0.98   160
                     Credit           High        Hierarchical macro ridge                  0.04 3.95    -0.03 -5.22     0.95   160
                     Inflation        High        Hierarchical validation ensemble          0.06 6.09    -0.03 -5.50     1.28   160
                     Credit           High        Hierarchical validation ensemble          0.04 4.82    -0.03 -5.84     1.19   160
                     Liquidity        Low         Hierarchical macro ridge                  0.05 10.02   -0.03 -6.66     2.95   160
                     Liquidity        Low         Hierarchical validation ensemble          0.05 7.22    -0.03 -6.07     2.09   160
                     Rates            Low         Hierarchical validation ensemble          0.04 3.92    -0.03 -5.29     1.08   160
                     Growth           Middle      Hierarchical validation ensemble          0.05 7.36    -0.03 -6.73     2.00   159
                     Trend            Middle      Hierarchical macro ridge                  0.04 5.37    -0.03 -4.91     0.82   159
                     Rates            Low         Neural network benchmark                  0.04 4.29    -0.03 -3.79     0.64   160
                     Rates            Low         Hierarchical macro ridge                  0.04 3.97    -0.03 -5.56     1.09   160
                     Growth           Middle      Hierarchical macro ridge                  0.05 6.78    -0.03 -5.92     3.06   159
                     Valuation        Low         Neural network benchmark                  0.07 8.48    -0.03 -4.62     1.69   160

     Notes: Rows with the largest absolute incremental IC are reported to summarize regime-local benchmark behavior.

===== PAGE 83 =====

            Pooled all-212 ridge                                                                                       0.03


                                                                                                                       0.02
      Ridge plus macro residual




                                                                                                                              Incremental IC vs pooled ridge
                                                                                                                       0.01


   Ridge plus validation residual                                                                                      0.00


                                                                                                                        0.01
       Hierarchical macro ridge
                                                                                                                        0.02


Hierarchical validation ensemble                                                                                        0.03


                                        it       th        tion       idity        s   Risk        d            tion
                                    Cred     Grow     Infla       Liqu        Rate            Tren
                                                                                                       Valu
                                                                                                            a

Figure IA.6. Regime-local stock-level reliability. Cells report incremental information coef-
ficients relative to pooled ridge within high-state macro regimes.




                                                                     33

===== PAGE 84 =====

     This table expands the capacity frontier. It shows return and IC evidence across market-capacity regions using the same low-trend-minus-
     high-trend interpretation.
                                                        Table IA.22. Capacity Region Monthly Evidence


                           Capacity region     Metric       Low-high value t-statistic High state Low state High months Low months
                           All firms           EW return              0.03      7.41      -0.02      0.01         248         248
                           All firms           VW return              0.03      6.16      -0.02      0.01         248         248
                           All firms           IC                     0.07      8.32      -0.04      0.03         248         248
                           Micro bottom 20     EW return              0.01      2.11      -0.02     -0.01         248         248
                           Micro bottom 20     VW return              0.01      1.98      -0.02     -0.01         248         248
                           Micro bottom 20     IC                     0.01      1.78      -0.04     -0.03         248         248
                           Outside microcaps   EW return              0.02      4.58      -0.01      0.00         248         248
                           Outside microcaps   VW return              0.01      3.73      -0.01      0.00         248         248
                           Outside microcaps   IC                     0.05      6.69      -0.04      0.01         248         248
                           Middle 60           EW return              0.01      3.67      -0.01      0.00         248         248
                           Middle 60           VW return              0.01      3.02      -0.01      0.00         248         248
                           Middle 60           IC                     0.04      4.90      -0.03      0.00         248         248
                           Upper half          EW return              0.01      1.58      -0.01     -0.00         248         248
                           Upper half          VW return              0.01      1.72      -0.01     -0.00         248         248
                           Upper half          IC                     0.02      3.38      -0.02     -0.00         248         248
                           Upper third         EW return              0.00      0.54      -0.01     -0.00         248         248
                           Upper third         VW return             -0.00     -0.03      -0.01     -0.01         248         248
                           Upper third         IC                     0.01      1.77      -0.02     -0.01         248         248
                           Large top 20        EW return             -0.00     -0.53      -0.00     -0.00         248         248
34                         Large top 20        VW return             -0.01     -1.29      -0.00     -0.01         248         248
                           Large top 20        IC                    -0.00     -0.11      -0.01     -0.01         248         248
                           Mega top 10         EW return             -0.01     -1.57      -0.00     -0.01         248         248
                           Mega top 10         VW return             -0.01     -2.09       0.00     -0.01         248         248
                           Mega top 10         IC                    -0.02     -1.54      -0.00     -0.02         248         248

     Notes: The table reports the capacity evidence by region and metric. Return rows are monthly returns; IC rows are monthly cross-sectional
     information coefficients.

===== PAGE 85 =====

     This table summarizes the capacity boundary. It is useful because the mechanism should be strongest where limits to arbitrage are economically
     meaningful and smaller where capacity is deepest.
                                                         Table IA.23. Capacity Boundary Evidence


            Economic screen               Sample            Metric        Estimate t-statistic Economic interpretation
            All firms state dependence      All firms         EW return      -0.03      -7.41 Full-universe state dependence is present
            Outside microcaps               Outside microcaps EW return      -0.02      -4.58 The mechanism extends beyond the bottom-size quintile
            Midcap limits to arbitrage zone Middle 60         EW return      -0.01      -3.67 The mechanism remains strong where limits to arbitrage are
                                                                                              plausible and capacity is greater than in microcaps
            Top half capacity             Upper half        EW return        -0.01      -1.58 Tests whether the effect reaches the top half of market capi-
                                                                                              talization
            Large top20 boundary          Large top 20      EW return         0.00       0.53 Tests whether the effect is safe for large-stock-exclusive
                                                                                              claims
            Mega top10 boundary           Mega top 10       EW return         0.01       1.57 Tests whether the effect is safe for mega-cap-exclusive claims
            Ex micro value weighted       Outside microcaps VW return        -0.01      -3.73 Tests whether the effect is solely equal-weighted
            Ex micro confirmation         Outside microcaps EW return        -0.00      -0.51 Tests whether the ex-micro effect survives the post-2005 hold-
                                                                                              out
            Overall capacity boundary     Summary                            -0.02      -4.58 The mechanism extends beyond microcaps and is shaped by
                                                                                              capacity

     Notes: The table summarizes how the capacity evidence changes across economically ordered market-cap regions.

35

===== PAGE 86 =====

                                   2




24-month average return, percent
                                   1


                                   0


                                   1


                                   2


                                   3


                                       1985   1990   1995   2000               2005       2010        2015   2020   2025


                                                                   All firms           Large top 20
                                                                   Outside microcaps   Middle 60

       Figure IA.7. Capacity-region time series for liquidity/limits. Lines report rolling average
       returns for the liquidity/limits by trend mechanism across market-capacity regions.




                                                                             36

===== PAGE 87 =====

Appendix E. State Specificity, Placebos, Timing, and
Model-Class Comparisons
Appendix E evaluates whether the macro-family links are tied to economically meaningful
states rather than calendar or relabeled patterns. The state-specificity tables compare the
full macro-state design with shuffled, random, calendar, and single-state alternatives; the
holdout and placebo tables evaluate the lead mechanism under relabeling and shifted-state
designs.
   The final exhibits in this section report frontier and compute-heavy stock-level model
comparisons. These benchmarks strengthen the paper’s interpretation by showing that the
economic contribution is not generic model complexity; it is the allocation value of macro-
conditioned anomaly-family information.




                                            37

===== PAGE 88 =====

     This table reports state-specificity comparisons that replace or perturb the macro-state information. The evidence shows that the macro-family
     link is economically meaningful.
                                                  Table IA.24. Calendar and Random-State Comparisons


                                 Comparison                                     Allocation rule    Estimate (%) t-statistic Months
                                 Macro shuffle minus full macro                 Macro analog              -0.28      -1.21    479
                                 Macro shuffle minus full macro                 Macro ridge               -0.29      -1.03    479
                                 Macro shuffle minus full macro                 Attention memory          -0.33      -1.36    479
                                 Macro shuffle minus full macro                 Ensemble                  -0.36      -1.53    479
                                 Single-risk-state benchmark minus full macro   Macro analog             +0.22        1.00    479
                                 Single-risk-state benchmark minus full macro   Macro ridge              +0.15        0.75    479
                                 Single-risk-state benchmark minus full macro   Attention memory         +0.19        0.78    479
                                 Single-risk-state benchmark minus full macro   Ensemble                 +0.01        0.04    479
                                 Calendar dummy minus full macro                Macro analog             +0.41        1.53    479
                                 Calendar dummy minus full macro                Macro ridge              +0.31        1.18    479
                                 Calendar dummy minus full macro                Attention memory         +0.65        2.41    479
                                 Calendar dummy minus full macro                Ensemble                 +0.11        0.44    479
                                 Random macro minus full macro                  Macro analog              -0.14      -0.66    479
                                 Random macro minus full macro                  Macro ridge               -0.17      -0.72    479
                                 Random macro minus full macro                  Attention memory          -0.21      -1.01    479
                                 Random macro minus full macro                  Ensemble                  -0.21      -0.95    479

     Notes: The table compares the full macro-state design to random, shuffled, calendar, and single-state alternatives.
38

===== PAGE 89 =====

     This table evaluates the contribution of macro-state blocks. It shows how the allocation evidence changes when each economic block is removed.
                                                           Table IA.25. Macro-Block Drop Tests


                                Block comparison                               Allocation rule    Estimate (%) t-statistic Months
                                Drop Inflation block minus full macro states   Macro analog              -0.08      -0.57    479
                                Drop Inflation block minus full macro states   Macro ridge              +0.12        0.91    479
                                Drop Inflation block minus full macro states   Attention memory          -0.13      -0.88    479
                                Drop Inflation block minus full macro states   Ensemble                 +0.04        0.33    479
                                Drop Growth block minus full macro states      Macro analog             +0.05        0.63    479
                                Drop Growth block minus full macro states      Macro ridge              +0.02        0.30    479
                                Drop Growth block minus full macro states      Attention memory          -0.05      -0.48    479
                                Drop Growth block minus full macro states      Ensemble                 +0.04        0.52    479
                                Drop Rates block minus full macro states       Macro analog             +0.00        0.05    479
                                Drop Rates block minus full macro states       Macro ridge              +0.14        1.97    479
                                Drop Rates block minus full macro states       Attention memory          -0.04      -0.51    479
                                Drop Rates block minus full macro states       Ensemble                 +0.05        1.19    479
                                Drop Credit block minus full macro states      Macro analog             +0.05        0.94    479
                                Drop Credit block minus full macro states      Macro ridge              +0.05        0.62    479
                                Drop Credit block minus full macro states      Attention memory          -0.06      -0.86    479
                                Drop Credit block minus full macro states      Ensemble                  -0.03      -0.57    479
                                Drop Liquidity block minus full macro states   Macro analog             +0.03        0.59    479
                                Drop Liquidity block minus full macro states   Macro ridge              +0.09        1.05    479
                                Drop Liquidity block minus full macro states   Attention memory         +0.10        1.91    479
                                Drop Liquidity block minus full macro states   Ensemble                 +0.03        0.87    479
39                              Drop Risk block minus full macro states        Macro analog             +0.02        0.16    479
                                Drop Risk block minus full macro states        Macro ridge               -0.02      -0.23    479
                                Drop Risk block minus full macro states        Attention memory          -0.06      -0.36    479
                                Drop Risk block minus full macro states        Ensemble                  -0.04      -0.27    479
                                Drop Valuation block minus full macro states   Macro analog             +0.00        0.31    479
                                Drop Valuation block minus full macro states   Macro ridge               -0.01      -1.42    479
                                Drop Valuation block minus full macro states   Attention memory         +0.01        0.46    479
                                Drop Valuation block minus full macro states   Ensemble                 +0.02        1.40    479
                                Drop Trend block minus full macro states       Macro analog              -0.00      -0.05    479
                                Drop Trend block minus full macro states       Macro ridge              +0.01        0.14    479
                                Drop Trend block minus full macro states       Attention memory          -0.03      -0.31    479
                                Drop Trend block minus full macro states       Ensemble                  -0.08      -1.23    479

     Notes: The table reports how performance changes when individual macro blocks are removed from the full macro-state design.

===== PAGE 90 =====

     This table reports additional timing and construction comparisons. It documents that the allocation evidence is aligned with the real-time
     design.
                                                   Table IA.26. Release-Lag and Timing Comparisons


                                   Timing or construction comparison Allocation rule          Estimate (%) t-statistic Months
                                   Market beta residualized sleeves   Valuation                     +1.28        7.12    742
                                   Market beta residualized sleeves   Continuation                  +1.18        7.15    742
                                   Market beta residualized sleeves   Correction                     -1.51      -9.35    742
                                   Market beta residualized sleeves   Profitability/quality         +0.74        5.27    742
                                   Market beta residualized sleeves   Investment/issuance            -0.64      -7.90    742
                                   Market beta residualized sleeves   Safety/downside                -0.57      -2.92    742
                                   Market beta residualized sleeves   Liquidity/limits               -0.97      -6.37    742
                                   Market beta residualized sleeves   Expectations                  +0.49        4.04    742
                                   Orthogonalized sleeves timed       Macro analog                  +0.08        0.49    479
                                   Orthogonalized sleeves timed       Macro ridge                   +0.05        0.32    479
                                   Orthogonalized sleeves timed       Attention memory              +0.10        0.66    479
                                   Orthogonalized sleeves timed       Ensemble                      +0.09        0.46    479
                                   Extra lag minus equal weight       Macro analog                  +1.23        5.90    479
                                   Extra lag minus equal weight       Macro ridge                   +1.45        7.08    479
                                   Extra lag minus equal weight       Attention memory              +1.08        5.39    479
                                   Extra lag minus equal weight       Ensemble                      +1.58        7.61    479

     Notes: The table reports additional timing and construction comparisons for the allocation evidence.
40

===== PAGE 91 =====

     This table reports the holdout evidence in its original high-minus-low sign convention. It shows the formation and confirmation periods for
     the lead channel and comparison channel.
                                               Table IA.27. Prespecified Holdout Evidence


              Family-state pair             Period                                H-L ret. (%) t-stat. High months Low months
              Liquidity/limits × Trend Formation period, 1985–2004                         -4.26   -5.69            80             80
              Liquidity/limits × Trend Confirmation period, 2005 onward                    -1.86   -3.11            62            107
              Continuation × Valuation Formation period, 1985–2004                        +0.05     0.05            80             80
              Continuation × Valuation Confirmation period, 2005 onward                   +0.00     0.00           223              2

     Notes: The table reports formation and confirmation estimates for the leading mechanism and comparison channel.




41

===== PAGE 92 =====

      This table reports the relabeling and shifted-state evidence. It shows that the main mechanism is tied to the economic macro-family link.
                                             Table IA.28. Placebo and Permutation Evidence

     Family-state pair           Comparison                        Actual t Comparison mean abs. t Comparison max abs. t Estimate (%)
     Liquidity/limits × Trend Actual macro-family pair                 -7.41                        0.00                       0.00           -3.13
     Liquidity/limits × Trend Circularly shifted macro state           -7.41                        0.56                       1.07           -3.13
     Liquidity/limits × Trend Calendar-month state                     -7.41                        1.10                       1.10          +0.43
     Liquidity/limits × Trend Family-label relabeling                  -7.41                        2.00                       4.61           -3.13
     Continuation × Valuation Actual macro-family pair                 -2.39                        0.00                       0.00           -1.18
     Continuation × Valuation Circularly shifted macro state           -2.39                        1.92                       3.27           -1.18
     Continuation × Valuation Calendar-month state                     -2.39                        0.53                       0.53          +0.25
     Continuation × Valuation Family-label relabeling                  -2.39                        2.28                       3.38           -1.18

      Notes: The table compares actual macro-family pairs with shifted, calendar, and relabeled alternatives.



42

===== PAGE 93 =====

       Family label placebo




     Calendar month state




Circular shifted macro state




          Actual frozen pair
                               0   1   2              3               4              5               6   7
                                                       Absolute actual t-statistic

                                           Liquidity/limits × Trend       Continuation × Valuation

Figure IA.8. Placebo and permutation comparisons. Points compare actual mechanism
t-statistics across placebo and relabeling designs for the lead and comparison family-state pairs.




                                                    43

===== PAGE 94 =====

     This table reports the broader model-class comparison. It places ridge, decay-aware, family-balanced, regularized, neural, and hierarchical
     models in a common benchmark frame.
                                                             Table IA.29. Frontier Model Benchmarks


           Model                              Role                                      Mean IC    IC t Incremental IC vs pooled ridge Incremental t Alpha t
           Ridge plus macro residual          Macro residual after full-panel ridge        0.07   15.63                          0.00          0.21    14.22
           Pooled all-212 ridge               Full-panel stock-level benchmark             0.07   15.93                          0.00          0.00    14.48
           Decay-weighted ridge               Decay-aware linear benchmark                 0.07   15.08                         -0.00         -0.13    13.08
           Ridge-decay blend                  Decay-aware linear benchmark                 0.07   15.18                         -0.00         -0.74    13.42
           Ridge plus validation residual     Macro residual after full-panel ridge        0.07   15.64                         -0.00         -0.67    13.62
           Ridge plus macro-analog residual   Macro residual after full-panel ridge        0.07   15.59                         -0.00         -0.90    13.16
           Ridge plus attention residual      Macro residual after full-panel ridge        0.07   15.71                         -0.00         -1.17    13.55
           Ridge plus ensemble residual       Macro residual after full-panel ridge        0.07   15.69                         -0.00         -0.94    13.76
           Family-balanced ridge              Family-balanced linear benchmark             0.07   16.32                         -0.00         -2.32    14.40
           SGD Huber                          Regularized stock-level benchmark            0.07   10.48                         -0.01         -1.77    12.62
           SGD elastic net                    Regularized stock-level benchmark            0.06   13.01                         -0.01         -4.25    11.41
           Neural network benchmark           Neural stock-level benchmark                 0.05    9.84                         -0.02         -5.15    10.41
           Hierarchical validation ensemble   Macro-regime hierarchical 212 benchmark      0.05   10.70                         -0.03         -7.39     5.92
           Hierarchical macro ridge           Macro-regime hierarchical 212 benchmark      0.05    9.83                         -0.03         -7.32     8.36
           Hierarchical ensemble              Macro-regime hierarchical 212 benchmark      0.05   10.20                         -0.03         -7.26     6.46
           Hierarchical macro analog          Macro-regime hierarchical 212 benchmark      0.04    8.79                         -0.03         -7.60     5.54
           Hierarchical attention memory      Macro-regime hierarchical 212 benchmark      0.04    8.24                         -0.03         -8.01     5.27
           Static 212 equal weight            Static 212-characteristic baseline           0.03    9.42                         -0.04        -13.69     6.52

44   Notes: The table reports frontier stock-level and hierarchical model benchmarks.

===== PAGE 95 =====

     This table reports compute-heavy benchmark models. It supports the main paper’s interpretation that the economic contribution is state-
     dependent family allocation rather than model complexity.
                                                        Table IA.30. Compute-Heavy Model Benchmarks


                   Model                            Mean IC    IC t Incremental IC vs pooled ridge Incremental t EW L-S (%) Alpha (%) Alpha t
                   Pooled all-212 ridge                0.07   15.93                         0.00         0.00         3.88       3.44   14.48
                   Ridge plus validation residual      0.07   15.64                        -0.00        -0.67         3.77       3.31   13.62
                   SGD Huber                           0.07   10.48                        -0.01        -1.77         3.24       2.53   12.62
                   SGD elastic net                     0.06   13.01                        -0.01        -4.25         3.30       2.97   11.41
                   Neural network benchmark            0.05    9.84                        -0.02        -5.15         2.83       2.42   10.41

     Notes: The table reports compute-heavy stock-level benchmarks evaluated on the same prediction sample.




45

===== PAGE 96 =====

       Ridge plus macro residual
            Pooled all-212 ridge
          Decay-weighted ridge
              Ridge-decay blend
   Ridge plus validation residual
Ridge plus macro-analog residual
    Ridge plus attention residual
   Ridge plus ensemble residual
          Family-balanced ridge
                     SGD Huber
                 SGD elastic net
     Neural network benchmark

                                0.00   0.01   0.02        0.03           0.04      0.05   0.06   0.07
                                                                 Mean monthly IC

Figure IA.9. Model-class benchmark evidence. Bars report mean monthly information
coefficients across frontier stock-level model classes.




                                                     46

===== PAGE 97 =====

              Pooled all-212 ridge



     Ridge plus validation residual



                       SGD Huber



                   SGD elastic net



       Neural network benchmark


                                  0.00   0.01   0.02    0.03          0.04       0.05   0.06   0.07
                                                               Mean monthly IC

Figure IA.10. Compute-heavy stock-level benchmark evidence. Bars report mean monthly
information coefficients for the compute-heavy stock-level benchmark set.




                                                       47

===== PAGE 98 =====

Appendix F. Evidence Map for the Main Result
Appendix F gives a compact map from the paper’s empirical blocks to the central inter-
pretation. The table connects construction, allocation value, full-panel breadth, the liq-
uidity/limits × trend mechanism, the capacity frontier, state specificity, and stock-level
benchmarks.
  The purpose is organizational rather than evidentiary duplication. It lets the reader see
how the main paper and appendix exhibits fit together as a single expected-return and
portfolio-choice argument.




                                            48

===== PAGE 99 =====

The final appendix table maps evidence blocks to interpretation. It gives the reader a compact guide to
how construction, allocation, full-panel, mechanism, capacity, state-specificity, and benchmark evidence
fit together.
                       Table IA.31. Evidence Map for the Main Result


  Evidence block      Where reported           Economic interpretation
  Allocation value   Main Tables 3–4;          Macro-regime memory changes how capital is
                     IA.6–IA.10                assigned across economic anomaly families.
  Full-panel breadth Main Table 5;             The allocation structure remains connected to the
                     IA.12–IA.16               full 212-characteristic panel.
  Lead mechanism     Main Tables 8–9;          Liquidity/limits × trend is the sharpest family-state
                     IA.17A–IA.19              channel.
  Capacity shape     Main Table 10;            The mechanism is strongest where limits to arbitrage
                     IA.22–IA.23               should matter most.
  State specificity  Main Tables 11–13;        Perturbed state definitions and relabeling exercises
                     IA.24–IA.28               produce materially smaller evidence.
  Model benchmarks Main Tables 6–7 and         The pooled all-212 ridge provides a demanding
                     12; IA.14–IA.16 and       stock-level benchmark.
                     IA.29–IA.30

Notes: The table maps empirical evidence blocks to the paper’s central economic interpretation.




                                                  49

===== PAGE 100 =====

Appendix G. Source Classification, Publication Cover-
age, and Episode Decomposition
Appendix G reports additional exhibits for the data-source, signal-coverage, and mechanism
discussions. These exhibits classify the macro information set, document publication-year
coverage of the signal universe, and report the leave-one-episode-out decomposition for the
Liquidity/Limits by trend reversal.




                                            50

===== PAGE 101 =====

     This table classifies the 23 macro-conditioning variables by economic content and vintage-source treatment. Market prices, rates, spreads,
     and panel-derived market states are observed at portfolio formation; real-activity and inflation variables enter with the conservative vintage
     discipline described in the data section.
                                                       Table IA.32. Macro Conditioning Variable Classification


     Classification                           Count Variables
     Market prices, rates, spreads, and          11 VIX; federal funds rate; three-month Treasury bill; two-year Treasury yield; ten-year Treasury yield; BAA-Treasury
     direct market states                           spread; corporate OAS; S&P 500; market return; 12-month market trend; 12-month market drawdown
     Panel-derived cross-sectional market         4 market volatility proxy; cross-sectional dispersion; aggregate valuation; aggregate liquidity
     states
     Government real-activity and inflation       7 CPIAUCSL; PCEPI; CPILFESL; INDPRO; UNRATE; PAYEMS; USREC
     states
     Fully covered ALFRED real-time               3 INDPRO; PAYEMS; UNRATE
     external series
     Mixed ALFRED and                             8 CPIAUCSL; CPILFESL; FEDFUNDS; GS10; GS2; PCEPI; TB3MS; USREC
     conservative-vintage external series
     Conservative external fallback series        5 BAA10Y; BAMLC0A0CM; SP500; STLFSI4; VIXCLS
     Panel-derived prior-return-state             7 market return; market volatility proxy; cross-sectional dispersion; aggregate valuation; aggregate liquidity; 12-month
     variables                                      market trend; 12-month market drawdown

     Notes: The upper rows classify the variables by economic content. The lower rows classify the same information set by source discipline.
     External macro variables are drawn from FRED/ALFRED series with conservative timing alignment; panel-derived variables are constructed
51
     from prior return-panel information and enter as market-state controls rather than revised government statistics.

===== PAGE 102 =====

This table documents the publication-year coverage of the 212 Chen–Zimmermann/OpenAP signals
used as inputs. The paper’s empirical contribution is the macro-regime allocation layer applied to a
broad signal set, not the discovery of the individual anomaly signals.
            Table IA.34. Publication-Year Coverage of the 212-Signal Universe

                    Panel A. Family coverage by first out-of-sample year
                    Family                  Available by 1985 Published after 1985
                    Continuation                           0                     27
                    Correction                             0                      4
                    Expectations                           3                     22
                    Investment/issuance                    0                     46
                    Liquidity/limits                       2                     19
                    Profitability/quality                  0                     27
                    Safety/downside                        1                     25
                    Valuation                              3                     33

                 Panel B. Published-signal availability over prediction years
       Prediction year Eligible signals Share of 212 Continuation Valuation Liquidity/limits
                 1985                9         4.25%              0          3                2
                 1990               13         6.13%              0          3                2
                 1995               24        11.32%              2          8                4
                 2000               49        23.11%              5         14                5
                 2005               85        40.09%              7         17                9
                 2010              165        77.83%             21         32               16
                 2015              206        97.17%             26         36               21
                 2020              212       100.00%             27         36               21
                 2024              212       100.00%             27         36               21

Notes: A signal is counted as available in prediction year Y when its publication year is no later than
Y − 1. The table is a publication-year coverage audit for the fixed 212-signal input set. The main
allocation tests evaluate whether macro-regime conditioning improves the organization of the signal set
relative to static aggregation.




                                                   52

===== PAGE 103 =====

Figure IA.11. Publication-year availability of the 212-signal universe. The figure plots the
number of Chen–Zimmermann/OpenAP signals whose publication year precedes each prediction
year. The figure documents the growth of the published anomaly universe while the main paper
evaluates the allocation value of macro-regime conditioning over the full signal set.




                                            53

===== PAGE 104 =====

     The table reports the Liquidity/Limits by trend-state reversal after excluding named market episodes one at a time. The high-minus-low
     spread remains economically stable across exclusions, showing that the reversal is not concentrated in a single crisis or recovery window.
                                    Table IA.33. Liquidity/Limits Trend Reversal by Episode Exclusion


          Sample                                      High-trend mean Low-trend mean High-minus-low Welch t-stat High / low months
          All months                                             -1.79%            1.41%           -3.20%         -6.77           160 / 160
          Excluding 1987 crash                                   -1.79%            1.35%           -3.15%         -6.69           160 / 158
          Excluding LTCM/Russia 1998                             -1.79%            1.40%           -3.20%         -6.76           160 / 157
          Excluding dot-com 2000–2002                            -1.65%            1.50%           -3.15%         -6.73           149 / 146
          Excluding GFC 2007–2009                                -1.74%            1.44%           -3.18%         -6.50           155 / 140
          Excluding eurozone/debt-ceiling 2011                   -1.82%            1.41%           -3.23%         -6.85           159 / 156
          Excluding Q4 2018                                      -1.79%            1.44%           -3.23%         -6.87           160 / 158
          Excluding COVID 2020                                   -1.78%            1.42%           -3.21%         -6.70           156 / 157
          Excluding reopening 2021                               -1.81%            1.42%           -3.23%         -6.70           150 / 159
          Excluding inflation/rate shock 2022                    -1.79%            1.48%           -3.27%         -6.84           160 / 149

     Notes: Means are monthly equal-weight Liquidity/Limits family returns by trend state. The sign convention is high-trend minus low-trend.
     Negative estimates indicate stronger low-trend payoffs and negative high-trend payoffs. The episode exclusions use named crisis and recovery
     windows while preserving the common prediction sample.
54

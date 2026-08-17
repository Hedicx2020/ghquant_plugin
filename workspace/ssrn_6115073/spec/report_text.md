===== PAGE 1 =====

                                                                                  iew
               Online Portfolio Selection Using Macroeconomic Pattern
                                       Matching
                                                                                     ed
                                           Seyed Mehrzad Asaad Sajadi1
                                                  Sasan Barak1,∗
                                                                        ev
                                                          er
                                                 Ali Fereydooni2




                                                             r
           1 Department of Decision Analytics and Risk, Southampton Business School, University of

                                                  Southampton, UK


                                               pe
                     2 Adelaide Business School, University of Adelaide, Adelaide, Australia




                                   * Corresponding Author: Sasan Barak
           Department of Decision Analytics and Risk, Southampton Business School, University of
                                             Southampton, UK
                                     ot
           Building 175, Boldrewood Innovation Campus, Burgess Rd, Southampton, UK. SO16 7QF
                                        Email: S.Barak@soton.ac.uk



                          tn
                rin
     ep
Pr
This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 2 =====

               Online Portfolio Selection Using Macroeconomic Pattern



       Abstract
                                       Matching

                                                                                  iew
                                                                                     ed
           This research proposes a theoretical framework for adaptive portfolio construction that dy-
       namically adjusts to changing macroeconomic conditions to improve both market forecasting and
       investment performance. The model leverages an online portfolio framework and follows a struc-
       tured three-step process. In the initial step, stocks are identified based on their responsiveness to
       major macroeconomic indicators, such as interest rates and the consumer price index, to enhance


                                                                        ev
       exposure to risks that are systematically priced by the market. In the subsequent step, these stocks
       are grouped according to their mutual relationships, with the aim of diversifying the portfolio and
       minimising the risk of asset-specific idiosyncratic. In the final step, a two-stage pattern matching
       technique is applied: the model first identifies historical periods with analogous macroeconomic
       environments to explore differential asset pricing dynamics, then evaluates stock-specific behavior

                                                          er
       within those periods to guide asset allocation. Empirical analysis reveals that this approach con-
       sistently outperforms traditional portfolio strategies, achieving superior probabilistic Sharpe ratios.


                                                             r
       Furthermore, portfolios constructed through this method demonstrate improved downside protec-
       tion (as captured by the negative β) and enhanced upside potential (reflected in the positive β).
       These results highlight the value of incorporating macroeconomic sensitivity and historical pattern
       analysis into portfolio design to increase returns and manage risk more effectively.

                                               pe
          Keywords: Finance, Pattern Matching, OnLine Portfolio Selection, Macroeconomic Factors,
       Clustering.
           JEL Classification: C38, C58, D40

       1. Introduction
                                     ot
           In economics, knowledge does not accumulate linearly. Our understanding can fluctuate, with
       lessons learned, forgotten, and re-embraced due to changing economic conditions. Concepts can go


                          tn
       in and out of prominence, driven by shifts in the economic landscape and trends. One such evolving
       concept is the financial cycle in macroeconomics, as economists and policymakers closely track
       macroeconomic indicators—particularly leading indicators—to anticipate upcoming expansions or
       contractions in the market Borio (2014). These cycles play a central role in shaping economic


                rin
       policy, guiding investment decisions, and influencing the design of investment strategies. Grounding
       investment approaches in such macroeconomic signals can offer considerable advantages to investors
       and fund managers Iyetomi et al. (2020), Bloomberg (2023), Forbes (2023).
           Given the importance of capturing the dynamic interactions between macroeconomic and fi-
       nancial variables, sudden shifts in key indicators can have substantial and varied effects on both


     epthe broader economy and financial market performance Kim and Kang (2022), Bodilsen (2024)
       Bouzgarrou et al. (2023). Since macroeconomic factors influence asset prices and investor behav-
       ior, incorporating macroeconomic analysis into financial decision-making can enhance the insights
       available to market practitioners Korobilis and Schröder (2024), Ma et al. (2022), Shu et al. (2024).
       Notably, this influence is not constant—it evolves over time and may differ across investment hori-

Pr     zons and market conditions Wang et al. (2023). As a result, identifying historical periods with sim-
       ilar macroeconomic characteristics can offer valuable context for portfolio managers. By examining


                                                           1

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 3 =====

       asset behavior during these analogous periods—often referred to as economic regimes—managers
       can uncover patterns that inform strategy development and risk management.


                                                                                  iew
           In recent years, the application of pattern-matching algorithms has gained prominence for their
       potential to enhance understanding of asset pricing dynamics Wang and Wang (2019), Guo et al.
       (2021), Fereydooni et al. (2024), Dong et al. (2025). However, most methodologies in this domain
       predominantly rely on past asset prices, revealing a significant gap in integrating economic factors to


                                                                                     ed
       refine asset pricing. One of the ways to consider such conditions is economic cycles. The economic
       cycle reflects the dynamic state of an economy. These shifts create recurring patterns in economic
       activity over time. To identify such patterns, this paper focuses on detecting economic cycles using
       key macroeconomic indicators. By applying pattern-matching techniques to these cycles, we aim to
       find historical periods that resemble the current economic environment and creating an advanced
       financial forecasting model.

                                                                        ev
           Pattern matching within OnLine Portfolio Selection (OLPS) involves the identification and uti-
       lization of historical trends or patterns in financial market data to inform real-time investment
       decisions. This strategy entails examining past price fluctuations, trading volume, and related data
       to pinpoint consistent patterns or associations that can aid in forecasting future market movements.


                                                          er
       The primary distinction between these models with traditional models, such as the Mean-Variance
       (MV) Markowitz (1952), is their approach to the time and data handling. Pattern-matching ap-
       proach can empowers OLPS to adapt swiftly to changing market conditions, identify profitable

                                                             r
       trading opportunities, and ultimately enhance portfolio performance, especially in environments
       characterized by high volatility and rapid price movements.
           Despite the demonstrated impact of macroeconomic variables on asset pricing, current OLPS


                                               pe
       models often neglect the role of regime-dependent macroeconomic dynamics and instead treat his-
       torical data uniformly, overlooking structural shifts such as economic cycles. This simplification can
       reduce model effectiveness, as it fails to capture the changing influence of macroeconomic indicators
       across different market states. Consequently, many existing models struggle to adapt to varying
       macro conditions, potentially leading to suboptimal asset selection and investment strategies. This
       paper addresses this gap by proposing an adaptive pattern-matching framework that integrates

                                     ot
       macroeconomic conditions into portfolio decision-making, aiming to enhance responsiveness to eco-
       nomic regime changes and improve the robustness of OLPS.
           However, constructing online portfolios using macro patterns needs selection of assets that are


                          tn
       responsive to macroeconomic indicators to enhance exposure to risks that are systematically priced
       by the market. To utilize asset selection, this study introduces Delta Beta (∆β) — a metric that
       captures the asymmetric sensitivity of stocks to macroeconomic variables by distinguishing between
       their reactions to upward and downward movements. By decomposing stock sensitivity into positive
       beta (β + ) and negative beta (β − ) components, ∆β identifies assets that are more responsive to

                rin
       macroeconomic shifts. This enables the selection of stocks with greater exposure to priced macro
       risk factors, potentially improving portfolio performance and the overall robustness of the strategy.
           This study comprises three key phases. Initially, to enhance portfolio diversity, after identifying
       the appropriate assets using Delta Beta, a clustering model, named agglomerative hierarchical clus-


     eptering, is utilized. To cluster assets, symmetric uncertainty (SU) is employed to measure the degree
       of interdependence between asset returns, allowing for the grouping of assets that share the most
       informational similarity Bäcklund et al. (2011), Chazal and Michel (2021). Once similar assets are
       grouped together, a two-stage pattern-matching technique is applied to identify historical periods
       resembling the current state of multiple macroeconomic factors. The first stage identifies distinct

Pr     economic cycle periods within asset history characterized by similar macroeconomic conditions.
       Subsequently, for each asset, second stage explores how these periods inform asset pricing sensitivi-
       ties across analogous macroeconomic environments. Following this step, ultimately, the forthcoming

                                                           2

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 4 =====

       returns for each asset and their corresponding macro signal strengths are calculated. To better cap-



                                                                                  iew
       ture the complexity of macroeconomic influence, these individual signals are aggregated to reflect
       the joint effect of all considered macroeconomic variables on each asset. This integration provides
       a more comprehensive assessment of macro-financial conditions, enhancing the selection process.
       From each cluster, the asset with the strongest signal, based on macroeconomic factors, is selected
       for inclusion in the portfolio. In the final phase, two portfolios are formed based on the equally


                                                                                     ed
       weighted model and the MV model, using the assets selected in the previous step.
           The proposed adaptive methodology selects the most influential macroeconomic factors—those
       with the strongest and most consistent impact on financial markets—within clearly defined eco-
       nomic regimes. The model then dynamically adjusts the importance of each factor in the portfolio
       construction process by incorporating spillover effects, which quantify how shocks to one factor
       influence asset returns across the market. By integrating regime detection, factor relevance, and

                                                                        ev
       spillover-weighted decision-making, the approach more accurately aligns portfolio choices with cur-
       rent macroeconomic conditions. Employing this approach can empower investors to focus on anal-
       ogous past economic cycles when making decisions within specific relevant timeframes instead of
       analyzing the entire historical record of assets.


                                                          er
           The primary contributions presented in this paper can be listed as follows:

           • Proposing Delta Beta (∆β) method for macro responsive asset selection


                                                             r
           • Finding economic cycles via a pattern matching approach.

           • Developing an OLPS approach based on macroeconomic data.


                                               pe
           • Introducing a two-stage pattern matching method for finding similar windows in assets’ his-
             tory.

           • Finding the most effective macroeconomic factors on the stock markets.

           • Considering economic cycles and combining and using macroeconomic factors to predict the
             future price of assets.
                                     ot
           The remainder of this paper is as follows: Section 2 provides a concise overview of existing
       literature on macroeconomic factors and OLPS models. Section 3 describes the functioning of OLPS

                          tn
       models, while section 4 details the methodology of the proposed approach. Section 5 presents the
       data utilized in this research and evaluates and discusses the performance of the proposed approach.
       Section 6 discusses more about macroeconomic factors and how they can affect different financial
       markets. The final section, section 7, summarizes the entire study and discusses potential avenues


                rin
       for expanding this work in future research. H

       2. Literature Review

       2.1. Online portfolio selection (OLPS)

     ep    The literature on OLPS models can be categorized into several key approaches. The benchmark
       models include strategies such as Buy-and-Hold and Best-Stock, which either distribute capital
       evenly at the start or invest entirely in the best-performing asset Li and Hoi (2014). The Constant
       Rebalanced Portfolio (CRP) framework maintains fixed asset proportions throughout the investment

Pr     horizon, with its two popular variants—Uniform CRP (UCRP) and Best CRP (BCRP)—offering
       either equal distribution or an offline optimization for maximizing cumulative returns Cover (1991),
       Li et al. (2015). Another category is the Follow-the-Winner models, which rely on momentum.


                                                           3

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 5 =====

       These include the Universal Portfolio (UP) strategy Cover (1991), the Exponential Gradient (EG)



                                                                                  iew
       method Helmbold et al. (1998), and the Adaptable Portfolio Selection (APS) model Gaivoronski
       and Stella (2003b), all of which attempt to allocate weights based on recent performance to capi-
       talize on continuing trends. Conversely, Follow-the-Loser models are built on the principle of mean
       reversion, encouraging investment in underperforming assets with the expectation of a rebound. No-
       table examples include the Anticor algorithm, which reallocates based on cross-asset anti-correlation


                                                                                     ed
       Borodin et al. (2003), and the Passive-Aggressive Mean Reversion (PAMR) model, which uses loss
       functions to capture reversion patterns Li et al. (2012). However, due to PAMR’s risk management
       limitations, the Online Moving Average Revision (OLMAR) method was proposed to improve pre-
       diction stability through averaging techniques Li et al. (2015). Moreover, meta-learning approaches
       leverage ensembles of base strategies. Algorithms such as Follow the Leading History (FLH) Hazan
       and Seshadhri (2009), Online Gradient/Online Newton Updates (OGU/ONU) Das and Banerjee

                                                                        ev
       (2011), and Boosting Moving Average Reversion (BMAR). Lin et al. (2017) combined diverse models
       to generate more robust portfolios, with empirical results showing superior performance compared
       to single-strategy methods. Modern portfolio models have evolved to integrate uncertainty, moving
       beyond traditional volatility-focused approaches. Aı̈t-Sahalia et al. (2025) model underscores the


                                                          er
       critical role of portfolio management by illustrating how accounting for the disconnect between
       stochastic equity market uncertainty and volatility markedly improves portfolio performance. By
       treating volatility and model uncertainty as separate factors, their framework optimizes consump-

                                                             r
       tion and portfolio policies, enabling superior asset allocation decisions and enhanced risk-adjusted
       returns compared to conventional models that solely emphasize volatility.
            The Final category, pattern-matching, identifies market windows with similar performance in


                                               pe
       order to make predictions for the future based on similarities. This is an integrated approach
       to follow-the-winner and follow-the-loser and ensures universal consistency. Györfi et al. (2006)
       proposed a method consisting of two phases: sample selection and portfolio optimization. The
       first stage compared the distances between price patterns using a non-parametric kernel-based
       sample selection method in order to identify patterns that were similar. Then, according to the
       capital growth theory, a portfolio is built in the second stage of the proposed algorithm. Also, by

                                     ot
       combining correlation-driven sampling selection with a log-optimal utility function, Li et al. (2011)
       developed CORrelation-driven non-parametric learning (CORN). Additionally, Wang and Wang
       (2019) suggested that the Pearson correlation between market status and the optimal portfolio


                          tn
       could provide an explanation for the pattern matching. They proposed CORN-K, which combines
       only the top K best experts to form the final portfolio, and devised a novel approach aimed at
       constructing a portfolio that has maximum returns over a similar period and minimum returns
       over a different period. In addition, the proposed algorithm was used as an inspiration for the
       development of another algorithm ”functional CORN-K” that utilized the symmetric property in a

                rin
       principled manner.
            Recent advances further highlight the potential of pattern matching in financial forecasting.
       Mustafa et al. (2022) employed an artificial neural network to detect shifts in market regimes,
       identifying five major transitions aligned with significant economic events. Dyer et al. (2024) showed


     epthat similarities in corporate disclosures can predict future return co-movement, enhancing market
       beta estimations. Fereydooni et al. (2024) proposed an OLPS model based on ESG factors. Using
       a pattern-matching approach, the investment portfolio for the current period was determined by
       identifying previously observed patterns that are similar to the current one. This method forecasts
       the future price based on these past patterns and uses the predicted prices to optimize the portfolio

Pr     selection. Moreover, Dong et al. (2025) proposed a multi-series pattern-based forecasting model
       that improves accuracy and timeliness by leveraging production data across multiple sources—an
       approach with strong parallels to financial time series forecasting.

                                                           4

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 6 =====

           While OLPS methods, particularly pattern-matching, have achieved significant successes, re-



                                                                                  iew
       search papers indicate that solely depending on such approaches may not yield satisfactory out-
       comes. Additionally, most studies in this field treat the entire time series with a similar importance,
       disregarding its dynamics. Therefore, since it has been demonstrated that various regimes within
       financial time series exhibit distinct behaviors and characteristics, incorporating additional tech-
       niques such as regime separation can improve the effectiveness of OLPS methods Fereydooni and
       Mahootchi (2023).

                                                                                     ed
           It is true that online portfolio selection strategies may show positive returns in the market;
       however, combining the information they gather can be challenging and novel techniques are required
       to solve these challenges. In one research, authors show that adaptive and threshold-based policies
       can effectively rebalance portfolios using past data and market conditions, achieving asymptotically
       the same performance as the best hindsight portfolio, even in the presence of transaction costs and

                                                                        ev
       without relying on probabilistic or stationary assumptionsGaivoronski and Stella (2003a).
           One of the features that can be considered in such approaches is macroeconomic factors. There is
       a compelling need for the development of a pattern-matching approach grounded in macroeconomic
       factors. Such an approach has the potential not only to introduce a lucrative OLPS strategy but


                                                          er
       also to identify the most influential macroeconomic factors within an OLPS framework. Therefore,
       macroeconomic factors can be used to identify similar periods and cycles in history, and to introduce
       specific intervals for implementing pattern-matching models that guide a suitable strategy.

       2.2. Macroeconomic importance
                                                             r
           Numerous studies have demonstrated the significance of macroeconomic factors in influencing


                                               pe
       financial markets and their dynamics. Narayan et al. (2014) investigated the predictability of excess
       stock returns in 18 emerging markets. Utilizing a principal component analysis, they analyzed a
       range of macroeconomic and institutional factors and found evidence of in-sample predictability
       for 15 countries. They showed the influence of macroeconomic factors on the stock markets and
       how they can be effective in price forecasting. Several studies examined the relationship between
       macroeconomic factors and financial markets’ prices. In more detail, multiple studies reported an

                                     ot
       inverse correlation between interest rates and stock prices, albeit with variations in the countries
       examined and research methodologies Sensoy and Sobaci (2014), Jayashankar and Rath (2017),
       Conrad (2021). Taveeapiradeecharoen and Aunsri (2020) examined the connection between sec-


                          tn
       toral stock indices and different monetary policy tools such as the deposit rate, lending rate, and
       long-term government bond yield. The findings exhibited that the relationship varies over time and
       cannot be definitively identified as either positively or negatively correlated with stock price returns
       for each sector of Stock Exchange of Thailand (SET) and macroeconomic factors such as interest
       rates. Also, using a variational mode decomposition and quantile model, Wang et al. (2023) ana-

                rin
       lyzed the impacts of macroeconomic variables on stock values within BRICS nations.The impact of
       macroeconomic variables can manifest through various transmission channels that ultimately affect
       financial markets.Phillot (2025) demonstrated that surprise increases in U.S. Treasury supply exert
       significant causal effects on financial markets, leading to shifts in the yield curve, stock prices, cor-


     epporate bond yields, inflation expectations, and risk premia. The effect of macroeconomic variables
       is not limited to stock markets, as one study on bitcoin showed that while most scheduled U.S.
       macroeconomic news does not influence its volatility, forward-looking indicators such as consumer
       confidence, together with regulatory news, investor sentiment, and hacking attacks on exchanges,
       play a crucial role in driving bitcoin’s realized variance and jump dynamicsŠtefan Lyócsa et al.

Pr     (2020).The outcomes revealed that the impact of each factor is intricate and variable across coun-
       tries and market conditions. Hence, emphasizing the investment horizon and market conditions
       hold considerable importance for diverse market participants.

                                                           5

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 7 =====

           In a study by Salisu et al. (2019), the authors proposed a multi-factor predictive model for



                                                                                  iew
       the oil-stock nexus based on macroeconomic factors, and they showed that the model considering
       macroeconomic factors had a better performance in prediction than the ones which did not consider
       such factors. This finding shows how macroeconomic factors can be influential on stock markets.
       In addition, de Mendonça and Dı́az (2023) found a negative association between increased uncer-
       tainty among private actors regarding the monetary policy interest rate and stock market returns.


                                                                                     ed
       Furthermore, unanticipated macroeconomic developments exert a demonstrable influence on stock
       market performance. Liu and Garrett (2023) demonstrated a mechanism through which macroe-
       conomic uncertainty drives stock market volatility and, subsequently, transmits its effects to real
       economic activity. Also,Studies have emphasized the role of macroeconomic variables in predicting
       stock market returns. For instance, Deng et al. (2024) construct a macro condition index using
       professional forecasts of output, inflation, and labor and housing market conditions, which predicts

                                                                        ev
       stock returns counter-cyclically. Additionally, Baz et al. (2025) has proposed a methodology to as-
       sess the influence of macroeconomic factors, such as inflation and economic growth, on asset prices.
       They construct inflation and growth shocks using survey-based expectations alongside realized CPI
       inflation and GDP growth, estimating the sensitivity (betas) of various assets and risk factors to


                                                          er
       these shocks. Their findings demonstrate how macroeconomic betas can be effectively integrated
       into portfolio construction to enhance resilience under different macroeconomic conditions.The im-
       portance of macroeconomic variables has captured the attention of many researchers as they have

                                                             r
       tried to find causes that affect macroeconomic variables and the whole market. Chavleishvili and
       Moench (2025) underscore the critical role of macroeconomic variables like output growth and in-
       flation in assessing the impact of climate-related natural disasters. They show that such shocks


                                               pe
       significantly alter the distribution, volatility, and skewness of these key aggregates—insights that
       standard linear models fail to capture.
           Overall, the aforementioned studies underscore the undeniable importance of macroeconomic
       factors and their profound impact on financial markets, particularly stock markets. These factors
       have been extensively studied and shown to influence market behavior significantly. However, there
       is a conspicuous gap in research when it comes to integrating macroeconomic considerations into the

                                     ot
       context of OLPS and pattern-matching approaches. Moreover, while macroeconomic factors provide
       valuable insights, they alone may not capture the full complexity of financial markets, which often
       operate under different regimes or phases. By recognizing and adapting to these regimes, OLPS


                          tn
       and pattern-matching approaches could potentially achieve better performance, offering more robust
       and adaptive strategies in the face of changing market environments.

       3. Problem formulation


                rin
       3.1. Online portfolio selection formulation
           Let’s consider a scenario where we intend to allocate a specific sum of capital over a defined
       time horizon consisting of n trading periods involving m different assets. The change in asset prices
       is denoted by a vector known as Vt , representing the relative price changes. In this vector, each


     epelement corresponds to the ratio of the closing price at time t to the closing price in the preceding
       period, and it is calculated as follows:

                                                     vt,i =
                                                               pt,i
                                                              pt−1,i
                                                                                                             (1)


Pr     where pt,i , t=1,...,n & i=1,...,m, shows the closing price of ith asset at the period of t. Hence,
       an investment in asset i during period t grows by a factor of vt,i . Assume V1n = {V1 , ..., Vn }
       represented as a sequence of vectors denoting price changes over n periods, and the market window

                                                           6

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 8 =====

       of price vectors, denoted as Vse = {Vs , ..., Ve }, where 1 ≤ s ≤ e ≤ n, represents a period range from
       s to e.


                                                                                  iew
           The investment made in the market during the t-th period denoted as bt = (bt1 , ..., btm )⊺ , where
       bti for i=1,. . . ,m indicates the proportion of the investment Pmallocated to asset i. The vector bt
       belongs to ∆m , which is a set defined as ∆m = {bt : bt ≥ 0, i=1 bti = 1}. The investment process
       is represented by a portfolio strategy represented by b1 = ( m    1       1
                                                                           ,..., m ), and subsequent steps are
       determined by the following sequence of mappings.

                                           bt = R+
                                                  m(t−1)
                                                           → ∆m , t = 2, 3, ...
                                                           −                         ed
       where bt = bt (V1t−1 ) is the portfolio constructed at the beginning of the t-th period. Thus, the
       output of the OLPS for n periods is presented as bn
                                                                                                             (2)


                                                             1 = (b1 , ..., bn ).


                                                                                ev
          Therefore, at time t, the portfolio’s return is altered by the following factor:

                                                st = b⊺t Vt =
                                                                m
                                                                X

                                                                i=1
                                                                      bti vti                                (3)



                                                            er
          Since reinvestment is employed and relative prices are adopted, wealth is expected to grow
                                                                     bn
       multiplicatively. Thus, after n periods, a portfolio strategy Q1 will generate a cumulative portfolio
       wealth Sn , which increases the initial wealth by a factor of nt=1 b⊺t Vt , which means:

                                                               r
                                               Sn (bn1 V1n ) = S0
                                                                    n
                                                                    Y
                                                                      b⊺t Vt
                                                                    t=1
                                                                                                             (4)


                                               pe
           where S0 is the initial capital investment.
           In this regard, a portfolio manager aims to develop a portfolio strategy bn
                         n
                                                                                       1 based on the market
       price relatives V1 to achieve specific objectives. The manager calculates portfolios sequentially,
       using the historical sequence of price relative vectors V1t−1 available up to each period t. At each
       period, a new portfolio bt is determined for the next price relative vector Vt , with the decision

                                     ot
       criteria varying among different managers. Traders then adjust their holdings to align with the new
       portfolio by buying or selling the underlying stocks. At the end of each trading day, the market
       reveals Vt , and the resulting portfolio bt is evaluated based on the portfolio period return st . This
       process is repeated until the final period, at which point the portfolio strategy is assessed by its

                          tn
       cumulative wealth Sn .
           Additionally, two assumptions are made for the OLPS problem:
          1. Market liquidity: It is assumed that at the last close price of any trading period, one can buy
             or sell any amount.

                rin
          2. Market impact: The portfolio selection strategy we employ does not influence the market.
           Algorithm 1 illustrates the OLPS strategy.




     ep
Pr
                                                            7

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 9 =====

       Algorithm 1 Algorithm of Online Portfolio Selection
       Require: Historical price vector (V1n )
       Ensure: Final cumulative investment
                                 1
        Start with S0 and b1 = ( m
        for t=1,...,n do:
                                         1
                                   ,..., m );                                     iew
                                                                                     ed
           Investor recognizes the bt ;
           Market expose price relative vector (Vt );
           St = St−1 × b⊺t Vt ;
           Investors update their decisions;
        end for


       4. Methodology
                                                                        ev
           Our methodology, which is shown in Algorithm 2, consists of four key steps: (1) selecting
       assets based on return dependencies, (2) clustering assets based on the relationships among them,
       (3) identifying macroeconomic analogues using pattern matching, and (4) aggregating directional

                                                          er
       signals into a portfolio strategy. Each step builds on the previous to dynamically adapt to shifting
       in economic regimes.

       Algorithm 2 Algorithm of the whole proposed system
       Require: Assets’ prices
       Require: Macroeconomic factors’ values
                                                             r
                                               pe
       Ensure: A constructed portfolio based on selected assets through the methodology
        for Assets in each market do
            Select assets that exhibit sensitivity to macroeconomic factors, and subsequently evaluate
        the performance of various clustering techniques—such as hierarchical clustering—using different
        relationship metrics, including SU

                                     ot
            Select the best combination of clustering models and relationship metric for clustering the
        assets
            for Macroeconomic factors’ values do
                Identify similar historical periods for each macroeconomic factor and extract the corre-

                          tn
        sponding economic cycles
                Consider the current and the similar pattern
                for Assets’ prices and economic cycles do
                   Implement a pattern-matching to identify similar patterns in the extracted economic
        cycles

                rinPredict the future return of assets in each cluster
                   Calculate the strength of each signal
                   Pick the assets with the highest strength in each cluster
                   Construct the portfolio based on the selected assets and their corresponded weights

     ep         end for
            end for
        end for



Pr     4.1. First step: Asset Selection
          Obtaining more meaningful signals from macroeconomic variables requires identifying stocks
       with greater exposure to priced macro risk factors, which can enhance the return of the final port-

                                                           8

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 10 =====

       folio. To support this, we introduce Delta Beta (∆β) as a key tool for detecting stocks that are



                                                                                  iew
       more sensitive to movements in macroeconomic indicators. In traditional asset pricing models, such
       as the Capital Asset Pricing Model (CAPM) Sharpe (1964), the movement of an asset is typically
       modeled as a linear function of a single systematic risk factor—namely, the return on the market
       portfolio. This relationship is captured by the asset’s beta (β), which quantifies its sensitivity to
       market movements. However, a critical limitation of this approach lies in its assumption of symme-


                                                                                     ed
       try: it presumes that the magnitude of the asset’s response to positive market shocks is identical
       to that of negative shocks, differing only in direction. This assumption overlooks the possibility
       of asymmetric behavior, where asset returns may exhibit different sensitivities to upward versus
       downward movements in the underlying macroeconomic variable. ∆β addresses this limitation
       by capturing asymmetric sensitivity, distinguishing between upward and downward movements in
       macroeconomic variables, and thus providing a more nuanced measure of exposure.
           In the standard model, stock return (y) is expressed as:

                                                   y = α + βX + ϵ,
                                                                        ev                                   (5)



                                                          er
       where β represents the stock’s overall sensitivity to a macroeconomic variable, and α captures
       the portion of return unexplained by the macroeconomic variable. To refine this model, the data
       is separated into two distinct regimes, differentiating between stock behavior during positive and


                                                             r
       negative macroeconomic movements. This separation is achieved by decomposing the data into
       periods where the macroeconomic variable (X) movement is positive (X > 0) and negative (X < 0),
       respectively.
           For positive macroeconomic movements (x > 0), the stock return is estimated as:

                                               pe y = α + β + x + ϵ.

       Conversely, for negative macroeconomic movements (x < 0), the regression model is:
                                                                                                             (6)



                                                  y = α + β − x + ϵ.                                         (7)

                                     ot
       A higher β + indicates greater sensitivity to upward movements of a specific independent macroe-
       conomic variable, while a higher absolute value of β − reflects stronger sensitivity to downward
       movements of that same variable.

                          tn
          Delta Beta is then calculated as the difference between these two coefficients:

                                                   ∆β = β + − β − .

       By computing ∆β in this manner, stocks with the highest absolute values of ∆β can be identi-
                                                                                                             (8)



                rin
       fied, thereby increasing exposure to macroeconomic variables. This identification not only enables
       the selection of stocks that are more responsive to macro shifts, but also lays the foundation for
       constructing portfolios aligned with specific investment strategies based on macro sensitivity. More-
       over, the use of a threshold for ∆β values can filter out stocks with negligible asymmetric sensitivity,


     epfocusing the selection process on the most responsive assets.

       Remark 1. Macroeconomic Variables
           We study 18 macroeconomic variables—commonly regarded as relevant indicators of market
       conditions Ferrara and Guérin (2018)—which are listed in Appendix A, and employ a feature

Pr     selection method named BorutaShap Keany (2020). This model helps us select features based
       on their importance, and more information about it can be found in Appendix B. It selects seven
       features as the most impactful ones, including: Interest Rate (IR), Unemployment Rate (UR),

                                                           9

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 11 =====

       Gross Domestic Product (GDP), Industrial Production (IP), Debt-to-GDP (DGDP), Consumer
       Price Index (CPI), and Producer Price Index (PPI).


                                                                                       iew
           The main goal of the feature selection process is to identify macroeconomic variables that have
       the greatest impact on financial market movements, thereby reducing complexity in the pattern-
       matching method. This enables the extraction of meaningful signals while minimizing the influence
       of noise. Refer to Section 6 for a more in-depth discussion.

       4.2. Second step: Assets Clustering
                                                                                          ed
           In this step, to improve portfolio diversification, we first group assets based on their relation-
       ships. Clustering allows us to reduce redundancy and improve signal clarity in later stages. Various
       metrics are available to quantify the connections between diverse assets, including measures such
       as correlation and Mutual Information (MI). Although correlation is one of the most well-known

                                                                            ev
       techniques in this domain, it has three principal limitations. First, it quantifies linear interdepen-
       dence and cannot account for nonlinear associations. Second, it is susceptible to the influence of
       outliers. Third, in the absence of a normal bivariate distribution, correlation outcomes lack sig-
       nificance López de Prado (2020). MI, as introduced by Cover et al. (1994), is a common method


                                                            er
       used for assessing the relevance between two random variables. Figure 1 demonstrates MI, other
       information metrics, and how they are related to each other.



                                                               r
                                                pe
                                     ot
                          tn    Figure 1: An illustration of MI and other information metric


           According to Figure 1, H[X, Y ] represents the joint entropy, while H[X|Y ] and V I[X, Y ] denote


                rin
       the conditional entropy and variation of information, respectively. Additionally, M I[X, Y ] signifies
       the MI shared between the two variables. Therefore, the MI can be calculated as follows:

                                        M I[X, Y ] = H[X] + H[Y ] − H[X, Y ]                                 (9)



     epIn Equation 9, H[X] pertains to the entropy of the continuous variable X, while H[Y ] pertains to
       the entropy of the continuous variable Y. Also, H[X, Y ] is a measure of the overall variability of X
       and Y. Then, H[X, Y ] for continuous variables is defined as follows:
                                                   Z
                                          H(X) = p(x) log
                                                                 1
                                                                    dx                                  (10)

Pr                                                 Z
                                                     x


                                          H(Y ) = p(y) log
                                                     y
                                                               p(x)
                                                                1
                                                               p(y)
                                                                    dy                                  (11)


                                                            10

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 12 =====

                                                   Z Z
                                                                             1
                                      H(X, Y ) =             p(x, y) log           dydx                     (12)



                                                                                          iew
                                                    x   y                  p(x, y)
       where p(x) and p(y) are marginal probability distributions of the joint probability distribution,
       (p(x, y). Therefore, regarding the Equations 9 to 12, the MI between continuous assets of X and Y
       is calculated as follows:



                                                                                             ed
                           Z                   Z                    Z Z
                                       1                    1                          1
             M I[X, Y ] = p(x) log        dx + p(y) log        dy −      p(x, y) log         dydx    (13)
                            x        p(x)       y         p(y)       x y             p(x, y)
       However, according to Equation 9, MI tends to favor variables with many distinct values and lacks
       normalization, making it hard to compare across different variable pairs and difficult to interpret.
       SU, by normalizing MI and scaling its range to [0,1], effectively addresses these shortcomings,
       providing a more balanced and interpretable measure Witten and Frank (2002) and Lin et al.

                                                                               ev
       (2019). Therefore, in order to calculate the SU (SU [X, Y ]), we need to normalize the MI based on
       the following equation:
                                          SU [X, Y ] = 2 ×
                                                            M I[X, Y ]
                                                           H[X] + H[Y ]
                                                                                                       (14)


                                                              er
           In this phase, four distinct clustering models are applied using different metrics. The most
       suitable combination—hierarchical clustering with SU—is selected as the final model based on


                                                                 r
       multiple evaluation criteria (see Section 5.2.1). As a result, assets with similar SU values are
       grouped within the same cluster. Subsequently, the model selects one asset from each cluster,
       aiming to enhance the diversity of stock selection. In this study, the evaluation of MI and SU is
       conducted using in-sample data to ensure consistency in measuring relationships between variables.

                                               pe
       Remark 2. Optimal look back period (length of windows)
           To make accurate predictions based on past patterns, we must define how far back we look
       into historical returns. This is done using rolling windows—segments of fixed length that slide
       through time to capture sequences of returns. The length of these windows is a key parameter, as it
       influences both the pattern comparison and the reliability of forecasts. Let’s suppose we define the

                                     ot
       parameters for the length of rolling window, for example, setting them to 2 (w = 2). We move the
       window through the return series until we reach the end of the training set, ensuring that the last
                                                                                       ′   th
       window (Wm−1 ) includes the two most recent values from the training data (n − 1 and n ). By
                                                                                                   ′ th




                          tn
       considering such windows, we can determine the cluster to which these windows belong and make
                            ′   th
       predictions for the n + 1 value using the following approach:
          1. Determine the Pearson correlation by comparing the returns of the final window with the
             returns of every other window within the identical cluster. It should be noted that, as assets

                rin
             are clustered according to SU, and the SU values between assets within each cluster are in
             close proximity, the calculation of SU may not effectively emphasize distinctions. Therefore,
             we opt for using correlation in this context.
          2. After computing the correlations between the final window and all preceding windows, we


     ep      rescale these correlations to fall within the range of [0,1]. Then, we predict the next period’s
             return for asset j, denoted as (brn′ +1,j ), using Equation 15:

                                               rbn′ +1,j =
                                                             X

                                                             ι=1
                                                                   (rWι ,j × Cm−1,ι )                       (15)


Pr           where ι represents the index for previous windows, and rWι ,j represents the mean return of
             window ι for asset j. Additionally, the previous window indexed as ι, and Cm−1,ι stands for
             the correlation with the last window (Wm−1 ).

                                                              11

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 13 =====

          3. Compute the Mean Squared Error (MSE) by comparing each predicted value to its corre-
             sponding actual value.

                                 M SE r ′
                                        n +1,j
                                                 =
                                                     1X
                                                     w                                    iew
                                                        (rn′ +1,j − rbn′ +1,j )2 , j ∈ {1, . . . , J}       (16)




                                                                                             ed
             here, w signifies the count of windows, and J denotes the quantity of assets.
                                                                                    ′
          4. Proceed with steps 1 to 3 for the remaining test data, spanning from n + 1 to n.
          5. Calculate the average of MSEs (M SE).
                                                       Pn
                                                             ′   M SE rt,j
                                               M SE = t=n +1   ′                                            (17)
                                                        n − (n + 1) + 1


                                                                               ev
          Finally, steps 1 to 5 are implemented for other values of w ∈ {2, . . . , 10}, and the repetition with
       the least M SE indicates the optimal value of w. Algorithm 3 provides a concise summary of this
       procedure.

       Algorithm 3 Algorithm to find the optimal length of the window and number of sub-clusters
       Require: rtj
                                                               er
       Ensure: the minimum value of MSE which indicates the optimal value of w and nc
        for w → 2 to 10 do
           roll the window from day 1 to day n
           for Wm−1 → Wn′ −w+1 to Wn−w+1 do                       r
                                                 pe
               cluster windows in train part (W1 to Wm−1 )
               find the cluster of Wm−1
               calculate the Pearson correlation between Wm−1 and any window in the same clusters
               rescale all the correlations
               estimate return of the next period by Equation 15
               calculate MSE between the estimated window and its corresponding actual value
           end for
        end for                      ot
                          tn
           In order to encompass various types of clustering models, we carefully select them based on
       different fundamental criteria. As proposed in Barak and Mokfi (2019) and López de Prado (2020),
       clustering algorithms can be distinguished by their specific characteristics, such as connectivity,
       centroids, distribution, and density. Consequently, from different categories, we choose the clustering
       models, including agglomerative hierarchical clustering, K-means, Gaussian Mixture Model (GMM),


                rin
       and DBSCAN. In order to find the best clustering approach for this study, the clustering models
       are compared regarding several metrics such as Sharpe Ratio (SR), Maximum Drawdown (MDD),
       Value at Risk (VaR), and the diversification index.
           SR is defined as follows:
                                                         R − rf

     ep                                            SR =
                                                             σ
                                                                                                          (18)

       here, R represents the portfolio’s mean return, rf signifies the risk-free return within the market,
       and σ indicates the returns’ standard deviation.
           MDD, a metric measuring downside risk over a specific duration, represents the highest loss

Pr     experienced from a portfolio’s peak to its trough before a new peak is reached:

                                                     M DD =
                                                                TV − PV
                                                                  PV
                                                                                                            (19)

                                                               12

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 14 =====

       where TV is the trough value, and PV is the peak value.



                                                                                    iew
           VaR is a statistical technique used to assess and quantify the financial risk present in an invest-
       ment portfolio over a particular time period. It is computed through three approaches: variance-
       covariance, Monte Carlo simulation, and historical simulation, with the latter being used in this
       research. In the historical simulation method, VaR is determined by analyzing the portfolio’s past
       returns over a specified number of observations and assuming that future returns follow a similar


                                                                                       ed
       pattern Khindanova and Rachev (2019). The VaR value is then derived by considering the lowest
       5% of these historical returns.
           The diversification index assesses the degree of diversification in a portfolio by examining the
       correlation matrix CM. In an ideally well-diversified portfolio, the correlation matrix should closely
       resemble the identity matrix IM, indicating little correlation among the assets. The difference
       between CM and IM is measured using the Frobenius norm, denoted as ∥CM − IM∥. A smaller

                                                                          ev
       value of this norm implies a more diversified portfolio. Further details can be found in the provided
       Appendix C.
           To identify the best clustering model, we adopt a simple approach. First, assets are clustered
       using the four previously mentioned models. Then, within each cluster, the asset nearest to the


                                                           er
       cluster’s center is chosen, and an equally weighted portfolio is constructed with these selected assets.
       Subsequently, the four metrics are calculated for the final portfolios, enabling us to determine the
       best clustering models based on each metric.

                                                              r
       Remark 3. Regarding the optimal number of clusters, in this study, we adopt the Silhouette
       approach, introduced by Rousseeuw (1987), to identify the most suitable number of clusters. More


                                                pe
       detail of Silhouette score (SS) is explained in Appendix D.

       4.3. Third step: Return prediction
           After grouping assets, the next step is to identify historical periods that closely resemble the
       current macroeconomic environment. This enables us to forecast potential asset behavior by draw-
       ing insights from similar past scenarios. To facilitate this, we develop a two-stage pattern-matching

                                     ot
       framework. In the first stage, we analyze macroeconomic variables to identify periods with com-
       parable economic conditions. In the second stage, we examine asset price patterns within these
       selected environments to detect historical analogues.


                          tn
           More specifically, within each cluster, we apply a pattern-matching technique to seven key
       macroeconomic variables which are presented the Remark1. The goal is to detect recurring eco-
       nomic cycles and locate time windows in history that most closely resemble the current macroe-
       conomic state. We deploy the matrix profile method to identify these similar periods. Once these
       macroeconomic analogues are determined, we assess asset performance during those specific win-

                rin
       dows. For each asset, a second matrix profile is generated to find the most similar historical price
       pattern within the matched economic regime. The forecast is then produced by analyzing the
       returns that followed the most analogous historical window. A more detailed explanation of the
       employed methodology is provided as follow:


     epMatrix profile. In the time series T with the length of n, Ti,m = {Ti , Ti+1 , ..., Ti+m−1 } where 1 ≤
       i ≤ n − m + 1, is the subset of continuous values of length m with the ith subsequence. After
       finding the Z-normalized Euclidean distances between each Ti,m and all other subsequences within
       the same time series, a distance profile (Di ) can be calculated for each Ti,m . To be more precise,

Pr     the vector Di consists of distances between a certain subsequence Ti,m and all other subsequences
       in time series T, represented as Di = [di,1 , di,2 , ..., di,n−m+1 ] where di,j is the distance between Ti,m
       and Tj,m and 1 ≤ i, j ≤ n − m + 1. The matrix profile, denoted as M, can be expressed in a formal


                                                           13

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 15 =====

       manner as M = [min(D1 ), min(D2 ), . . . , min(Dn−m+1 )], with each min(Di ) indicating the smallest
       Z-normalized Euclidean distance within Di .


                                                                                     iew
           To keep track of the location of the nearest neighbor or closest match, a supplementary data
       structure known as the matrix profile index, denoted as I, is employed. This is represented by the
       I = [I1 , I2 , ..., In−m+1 ] where Ii = j if di,j = min(Di ), is employed to save the position of the nearest
       neighbor or the most similar match. By accessing the ith element of the matrix profile index, it
       becomes possible to retrieve the nearest neighbor for each Ti,m period.

                                                                                        ed
       Motifs. Time-series chains are commonly viewed as patterns that gradually change or move in a
       certain direction over time, which are also known as motifs. In order to gain a deeper comprehension
       of how time-series chains work, it is necessary to examine several related terminologies Chiu et al.
       (2003) and Zhu et al. (2017).

                                                                          ev
            For a given time series T, the ith left distance profile DLi and ith right distance profile DRi
       are sets of Euclidean distances between a specific subsequence Ti,m and all the preceding and
       subsequent subsequences of Ti,m , respectively. The left nearest neighbor (LNN) and the right
       nearest neighbor (RNN) of Ti,m , which are represented as LN N (T(i,m) ) = Tj,m if di,j = min(DLi )


                                                           er
       and RN N (T(i,m) ) = Tj,m if di,j = min(DRi ), are the subsequences that occur before and after
       it, respectively. Left matrix profile (ML) and right matrix profile (MR) are vectors that represent
       the Z-normalized Euclidean distances between all subsequences and their left and right nearest


                                                              r
       neighbors, respectively. ML and MR are calculated as follows:

                                 M L = [min(DL1 ), min(DL2 ), ..., min(DLn−m+1 )]                              (20)


                                                pe
                                 M R = [min(DR1 ), min(DR2 ), ..., min(DRn−m+1 )]
       where DLi and DRi (1 ≤ i ≤ n − m + 1).
           By providing a time series T and subsequence length m as input, the proposed approach gen-
       erates a modified matrix profile Mmod = [Υ1 , Υ2 , ..., Υn−m+1 ], where each Υi value belongs to the
                                                                                                               (21)




       set [1, 2, . . . , n − m + 1] and can be either the minimum value of min(Di ), Ii , ILi , or IRi , which are

                                     ot
       explained in Equations 22 and 23.

       Remark 4. Corresponding to ML and MR, two additional vectors called left matrix profile index
       (IL) and right matrix profile index (IR) respectively, are used to store the position of the left and

                          tn
       right nearest neighbors for each element i. IL and IR can be written as:

                                             IL = [IL1 , IL2 , ..., ILn−m+1 ]
                                             IR = [IR1 , IR2 , ..., IRn−m+1 ]
                                                                                                               (22)
                                                                                                               (23)

                rin
       where ILi = j and IRi = j if LN N (Ti,m ) = Tj,m and RN N (Ti,m ) = Tj,m . A time-series chain,
       T SC, in a time series T is a sequence of ordered subsequences T SC = {TC1,m , TC2,m , ..., TCω,m }
       with indices C1 ≤ C2 ≤ ... ≤ Cω, where ω is the length of time series. For any 1 ≤ k ≤ ω − l,
       LN N (TC(k+1),m ) = TCk,m and RN N (TC(k+1),m ) = TC(k+1),m .

     ep    The two-level procedure of this approach is explained as follows:
          1. The recent year of each macroeconomic factor is compared to its previous data, and the most
             similar year in the past to the current year is found based on the presented pattern-matching

Pr           approach.
          2. In order to find the most similar pattern to the current status of each asset, we employ another
             pattern-matching process for each asset on the times which are found in the previous step.

                                                            14

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 16 =====

       Figure 2 demonstrates a simple process of the aforementioned steps. According to Figure 2, first,



                                                                                      iew
       similar periods to the Current Period (CP) of each macroeconomic factor are found, and the period
       which is the Most Similar Period (MSP) to the CP, is equal to the minimum of the matrix profile,
       and is found as follows:
                                                  ′
                                             M SPCP j
                                                      = min[SPCPj ]                                 (24)



                                                                                         ed
       where the SPCPj shows similar period to the current period on macroeconomic j, and the CPj is
       the current period on macroeconomic j. Then, these two periods are the periods which are selected
       for the following steps and can be written as follows:
                                                            ′
                                                EPi,j = M SPCPj
                                                                , CPj                                       (25)

       where EPi,j is the examined period on asset i and macroeconomic j.

                                                                           ev
          Once MSPs of each macroeconomic factor are found, the second step of the pattern-matching is
       implemented. In this step, first, the most similar window to the current window is found based on
       Section 4.2, in which the length of optimal windows are calculated regarding the Remark 2; then,
       the next return of the current window is calculated based on the following process:


                                                           er
                                                   r̂n+1,i,j = rn+1,i,j                                     (26)



                                                              r
       where r̂n+1,i,j is the predicted return of the next period, if the length of the optimal window is n,
       based on macroeconomic factor j and asset i during the CP. Also, rn+1,i,j shows the actual return of
       the period after the similar window in MSP regarding the macroeconomic j and asset i. Assuming


                                                pe
       a window length of n, we extract a signal for day n+1. The predicted return of the day n+1 for
       the current windows is the amount of the day n+1 for the most similar window in the past based
       on the correlation. Figure 3 shows how the return of the day after the current window is computed.
       Having implemented the second pattern-matching, a specific signal for each asset based on each
       macroeconomic factor is extracted.


                                     ot
                          tn
                rin
     ep                         Figure 2: A general schematic of the pattern-matching steps


       4.4. Fourth step: Joint effect of signals and portfolio construction
           In the last step, the future returns for each asset and their respective signal strengths are
       computed. Within each cluster, the asset with the highest signal strength is chosen to be included

Pr     in the portfolio. In more detail, Having found similar patterns in each asset’s history, the return of
       the next period after the last window is predicted based on the most similar window to the current
       window in history. Once the signal for a particular asset is extracted, it turns into a binary form.

                                                            15

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 17 =====

       If the predicted return is positive, then the signal is be +1, and in the case that the predicted



                                                                                             iew
       return is negative, the corresponding signal is be -1. Equation 27 presents how the final signals are
       extracted.
                                       signali,j =
                                                   (
                                                    1,     if r̂n+1,i,j |wi,j > 0
                                                    −1, if r̂n+1,i,j |wi,j ≤ 0
                                                                                                        (27)




                                                                                                ed
                           Figure 3: Signal extraction based on asset i and macroeconomic factor j


                                                                                ev
           Once the asset-level signals based on individual macroeconomic factors are extracted, these
       signals are aggregated to form a unique, combined signal. This aggregated signal captures the
       joint effect of all the considered macroeconomic variables, thereby reflecting their collective impact


                                                               er
       on each asset. To this aim, a matrix based on the mutual influence, which is determined by
       volatility spillover, between different assets and macroeconomic factors is built. Finally, the asset
       with the highest final signal score from each cluster is chosen for inclusion in the portfolio. In this


                                                                  r
       regard, the study employs a weighted average spillover approach to assess the contribution of each
       macroeconomic factor to the joint final signal, which reflects the collective influence of all considered
       macroeconomic variables. This index is explained in Remark 5:


                                                 pe
       Remark 5. The spillover index evaluates interdependence among variables by quantifying volatility
       transmission between markets. This research utilizes the spillover index to analyze the effect of
       macroeconomic factors on various indexes, with further details in Diebold’s work Diebold and
       Yilmaz (2012).
           The calculation of the Vector AutoRegressive (VAR)(p) model with N variables is performed as
       follows:
                                      ot      κt =
                                                   Xp
                                                       Φi κt−i + εt
                                                         t=1
                                                                                                    (28)



                           tn
       where ε follows an independent and identically distributed (i.i.d.) disturbance vector with mean
       zero and covariance matrix Σ. Considering covariance stationarity, Equation 28 can be written as:

                                                     κt =
                                                            ∞
                                                            X
                                                                    Ai εt−i                                     (29)


                rin                                         t=1

            where Ai = Φ1 Ai−1 + Φ2 Ai−2 + . . . + Φp Ai−p , with A0 an N × N identity matrix and Ai = 0
       for i < 0. Variance decompositions allow for the assessment of the portions of error variance in
       forecasting κi , resulting from shocks to κj , for all i ̸= j, for each i. Cross-variance spillovers


     eprefer to the proportions of the error variance in forecasting κi resulting from shocks to κj , where
       i, j = 1, 2, . . . , N , and i ̸= j. On the other hand, own variance spillovers represent the proportions
       of the error variance in forecasting κi attributed to shocks in κi , where i = 1, 2, . . . , N . The error
       variance decompositions for U -step-ahead forecasts, denoted as θij
       as follows:
                                                                              g
                                                                                (U ) for U = 1, 2, . . ., are defined


Pr                               g
                                               P −1 ′
                                          σii−1 Uu=0 (ej Au
                                θij (U ) = PU −1 ′ ′ P
                                               u=0 (ej A u
                                                            P 2

                                                             e
                                                               ei )
                                                               j )
                                                                    ,         i, j = 1, 2, . . . , N            (30)


                                                               16

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 18 =====

       In this context, Σ represents the covariance matrix for the error vector ε, σii denotes the standard



                                                                                             iew
       deviation (Std) of the error term in the i-th equation, and ei is the selection vector, with a value of
       one in the i-th position and zeros elsewhere. Consequently, each row in the variance decomposition
       table is adjusted so that the sum of its elements equals:

                                       g
                                                    g
                                                   θij (U )



                                                                                                ed
                                      θij (U ) = PN g
                                      e                        ,       i = 1, 2, . . . , N                  (31)
                                                  j=1 θij (U )

                               eg                 PN eg
       By construction, N
                        P
                           j=1 θij (U ) = 1 and     i,j=1 θij (U ) = N .
          With regards to the overall spillover effect, which assesses the influence of shocks originating
       from various variables on the total forecast error variance, it can be described as follows:
                                                         PN eg

                                             S g (U ) = PN
                                                            i,j=1 θij (U )
                                                               i ̸= j
                                                                   θeg (U )
                                                            i,j=1 ij
                                                                               ev
                                                                            .100                      (32)




                                                             er
       The transmission of directional spillover from all other variables j to variable i is measured by:
                                              PN eg
                                               j=1 θij (U )
                                                i ̸= j
                                  Si.g (U ) = PN g
                                                    θe (U )
                                                 j=1 ij         r
                                                            .100, i = 1, 2, . . . , N                   (33)




                                                pe
       Hence, the directional influence from time series i to all other time series j is computed as follows:
                                               PN eg
                                                j=1 θji (U )
                                                 i ̸= j
                                   S.ig (U ) = PN g
                                                     θe (U )
                                                 j=1 ji
                                                             .100, i = 1, 2, . . . , N                   (34)



                                     ot
       Equation 34 illustrates the directional volatility spillovers that each index experiences from different
       macroeconomic factors. Specifically, in Equation 34, time series i represents macroeconomic factors,
       while j denotes the three indexes of different financial markets investigated in this paper. In this
       phase, the spillover index from the macroeconomic factors to each stock’s index is determined.

                          tn
           As a consequence of these directional spillovers, the net volatility spillovers from time series j
       to time series i can be ascertained by calculating the disparity between the gross volatility shocks
       received by all other variables and the gross volatility shocks conveyed to all other variables:

                                               Sig (U ) = S.ig (U ) − Si.g (U )                             (35)

                rin
       Once the net spillover among different macroeconomic factors and assets are calculated, we employ
       those influences in signal aggregation in this study. Having constructed a matrix of net spillover,
       see Equation 35, between assets and macroeconomic factors, the matrix is turned into a normalized


     epmatrix as follows:




       Here, γ
                                              γ
                                              ei,j =
                                                        γi,j − min(γj )
                                                       max(γj ) − min(γj )
              ei,j represents the standardized measure of the relationship between asset j and macroeco-
                                                                                                            (36)



Pr     nomic factor i, while γi,j = Sig (U ) denotes the net spillover value between asset j and macroeconomic
       factor i. This consideration between assets and macroeconomic factors can also incorporate firm-
       specific responses, such as variations in leverage and size.

                                                             17

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 19 =====

           For signal aggregation on each asset, the extracted signals for each asset and macroeconomic
       factor, that are detected from the pattern-matching step, are multiplied to γ


                                    F Sj =
                                             n
                                             X

                                             i=1
                                                   ei,j × signali,j ,
                                                   γ                                      iew
                                                                                   ei,j as follows:


                                                                        j = 1, 2, . . . , N                 (37)




                                                                                             ed
       where the F Sj is the final signal of asset j. Eventually, one asset with the highest value of F S from
       each cluster is picked for the final portfolio construction.
           The chosen assets are combined for portfolio construction using two methods: the Mean-Variance
       (MV) model Markowitz (1952) and an Equally Weighted (EW) approach, where each asset carries
       an equal weight in the portfolio. These steps form an adaptive framework that selects assets based
       on both their historical behavior and current macroeconomic signals, ultimately enhancing the
       relevance and robustness of portfolio construction.

       5. Data explanation and experimental results
                                                                              ev
       5.1. Data

                                                              er
           This study gathers data from three stock indices: the S&P 500, Nikkei 225 (N225), and Dow
       Jones Industrial Average (DJI), for the purpose of evaluating the proposed methodology, with

                                                                 r
       market data obtained from Refinitiv and macroeconomic indicators sourced from the Federal Reserve
       Economic Data (FRED) database. The study’s findings are presented in two distinct sections. First,
       a comprehensive analysis is conducted on the S&P 500 index, showcasing the various dimensions and


                                                   pe
       advantages of the proposed system. Subsequently, to enhance our understanding of the proposed
       approach’s performance, the system is also applied to the N225 and DJI indices.
           The data used in this study is collected on a daily basis, spanning from 1/1/1995 to 2/1/2023. It
       is worth mentioning that the period from 1/1/1995 to 31/12/2018 is designated for training to find
       the optimal length of windows in the pattern-matching part. This long period allows us to cover
       several significant financial market events, including the dot-com bubble, the 2007 financial crisis,
                                     ot
       and the COVID-19 pandemic, all of which had major impacts on financial markets. Additionally,
       based on the Remark 1, seven distinct macroeconomic factors are utilized for the pattern-matching
       component.


                          tn
       5.2. Experimental results
       5.2.1. Scenarios analysis
           Our analysis aims to identify assets that exhibit greater sensitivity to macro risk factors, en-
       hancing portfolio returns by selecting stocks based on macroeconomic signals. The separation into

                rin
       regimes (β + and β − ) involves a two-step regression approach applied to the time series data. First,
       the dataset is segmented based on the sign of the macroeconomic variable (X), where X > 0 defines
       the positive regime and X < 0 defines the negative regime. This segmentation ensures that the
       regression models capture distinct behavioral patterns. For each regime, Ordinary Least Squares


     ep(OLS) regression is conducted to estimate β + and β − , respectively. To ensure robustness, only
       assets with statistically significant coefficients in the OLS method are selected. This criterion helps
       eliminate noise and focuses the analysis on meaningful asset responses. This methodical separation
       allows for a clear delineation of how stocks respond differently to inflationary pressures versus de-
       flationary pressures, as evidenced by the scatter plot in Figure 4, where β + values range from −1.0

Pr     to 1.0 and β − values show a similar spread, with ∆β values color-coded to indicate the degree of
       asymmetry.


                                                              18

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 20 =====

           Figure 4 provides empirical support for the utility of ∆β. The scatter plot reveals a signifi-



                                                                                     iew
       cant number of stocks with non-zero ∆β values, indicating asymmetric sensitivity. For instance,
       stocks in the upper-right quadrant (high β + , low β − ) exhibit strong positive responses to rising CPI
       but limited reaction to falling CPI, suggesting potential hedge assets during inflationary periods.
       Conversely, stocks in the lower-left quadrant (low β + , high β − ) are more sensitive to deflationary
       pressures, offering diversification benefits during economic downturns. The color gradient, rang-


                                                                                        ed
       ing from −1.5 to 1.0, underscores that ∆β values are not uniformly distributed, with a notable
       concentration around zero (symmetric behavior) but with tails indicating significant asymmetry,
       supporting the need for regime-specific analysis. Details about ∆β analysis for other macroeco-
       nomic factors are available in Appendix E. By utilizing ∆β, we are able to identify stocks that
       exhibit high sensitivity to macroeconomic factors, regardless of the direction of their movements.
       The analysis considers only those assets for which both β + and β − are statistically significant in

                                                                          ev
       the OLS regressions.A detailed discussion of how many assets are significantly affected in upward
       or downward regime movements by each macroeconomic variable is provided in Section 6.




                                                           er
                                                              r
                                               pe
                                     ot
                          tn      Figure 4: Regression of S&P 500 stocks’ return on CPI.


           Next, in our search to identify the most effective clustering model, we adopt a straightforward

                rin
       methodology. After clustering assets using the four clustering models mentioned in section 4.2, we
       pinpoint the asset with the highest predicted return among the assets in each cluster. Subsequently,
       we construct a portfolio employing these chosen assets, adhering to an equal-weight allocation
       strategy. Finally, we compute the four metrics of SR, MDD, VaR, and the diversification index


     ep(Frobenius Norm) for these resultant portfolios to determine the optimal clustering models for each
       metric. Table 1 illustrates a comparison between the aforementioned models regarding SU and
       correlation.




Pr
                                                           19

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 21 =====

       Table 1: A comparison of different clustering models’ performance based on SU and correlation regarding four metrics.




                                                                                           iew
                                               SU                                               Correlation
          Metrics         SR       MDD        VaR       Frobenius Norm         SR       MDD       VaR Frobenius Norm
         K-Means         1.393     0.369     0.449           2.124            1.463     0.453    0.344      1.684
        Hierarchical     1.461     0.438     0.601          1.729             2.033     0.246    0.347      1.258
           GMM           1.234     0.445     0.493           2.233            1.345     0.344    0.465      1.945
         DBSCAN          1.297     0.471     0.463           2.233            1.464     0.567

                                                                                              ed 0.365

           As can be seen in Table 1, K-Means and Hierarchical clustering methods have the highest SR
       and the lowest MDD, VaR, and Frobenius Norm. Thus, these models can be considered as selected
       models. However, in order to select one clustering model and one metric between SU and correlation,
                                                                                                            1.744




       we implement another evaluation to find the most appropriate combination. The metrics employed

                                                                               ev
       for this objective encompass the Hopkins score, Silhouette, Calinski Harabasz, Davies Bouldin, and
       Dunn index. Detailed explanations of these metrics can be found in the Appendix D. Figure 5
       shows the performance of K-Means and Hierarchical model based on SU and correlation.



                                                               er
                                                                  r
                                                    pe
                                        ot
               Figure 5: A comparison between K-Means and Hierarchical clustering based on SU and correlation.




                            tn
           According to Figure 5, when assets are grouped according to SU relationships using the Hierar-
       chical clustering method, they exhibit the highest scores for Hopkins, Silhouette, Calinski-Harabasz,
       and Dunn Index, while having the lowest Davies-Bouldin score. This suggests that the combination
       of SU and the Hierarchical clustering method is the most appropriate choice for this study, and the


                rin
       analysis is conducted using this pairing.
           To gain a more in-depth understanding of how the Hierarchical clustering and K-Means methods
       perform, we illustrate how assets from various industries are distributed across different clusters.
       Figure 6 visualizes this distribution using SU (right half of the circles) and correlation (left half of
       the circles) as the criteria.


     ep
Pr
                                                                20

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 22 =====

                                                                                           iew
                                                                                              ed
                                                                                ev
                                                               er
                                                                  r
                                                   pe
                                       ot
             Figure 6: The distribution of the industries’ assets into different clusters based on SU and correlation.




                           tn
           This figure demonstrates that when assets are categorized based on correlation, they are spread
       among clusters representing various industries. This suggests that relying solely on correlation-
       based clustering may not achieve the desired outcomes, as this approach fails to distinguish assets
       belonging to particular industries. Furthermore, when comparing Hierarchical clustering (the upper


                rin
       circle) and K-Means methods (the lower circle), it becomes evident that Hierarchical clustering has
       the capability to place assets from the same industries within the same clusters. Consequently, for
       the scope of this study, clustering assets using the Hierarchical clustering method with SU as the
       criterion appears to be the most suitable approach. According to Figure 6, the clusters formed
       by SU and Hierarchical clustering exhibit a smaller variety of industries compared to alternative


     epconfigurations. In more detail, clusters 2, 3 and 5 predominantly consist of fewer and more distinct
       industries. For example, cluster 2 primarily includes stocks from the financial, utilities, and con-
       sumer staples sectors and cluster 3 is mainly composed of stocks from the healthcare and real estate
       sectors. Also, cluster 5 generally consists of stocks from four industries: energy, communication
       services, consumer discretionary, and utilities.

Pr
                                                                21

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 23 =====

       5.2.2. Return prediction and economic cycles extraction



                                                                                           iew
           This research employs a pattern-matching approach based on economic cycles applied to both
       macroeconomic factors and assets. To illustrate the functioning of the pattern matching procedure
       on macroeconomic factors, Figure 7 demonstrates the process of identifying similar patterns in each
       macroeconomic factor concerning the current period.



                                                                                              ed
                                                                               ev
                                                               er
                                                                  r
                                                   pe
            Figure 7: Similar patterns in seven different macroeconomic factors to their current windows (black lines).


           As shown in Figure 7, the proposed method, during the pattern-matching process in economic
                                        ot
       cycles, scans the current period (depicted in black) to locate the most akin period that exhibits
       minimal dissimilarity with the current window. Subsequently, the model searches exclusively within
       the present time-frame the one with the highest resemblance to the current window. This approach


                            tn
       enhances the likelihood of discovering similar patterns within the same cycles. For further explana-
       tion and based on Figure 7, the implementation of similar patterns on S&P 500 index is depicted
       in Figure 8. As can be seen, for each macroeconomic factor, a period is assigned on S&P 500 time
       series, and seven different signals are extracted based on the seven periods found. Each color rep-


                rin
       resents a candidate timeframe closely resembling the present, pertaining to every macroeconomic
       aspect. Following the description in Section 4.4, the gathered signals are then consolidated based
       on macroeconomic factors and their relative importance.




     ep
Pr
                                                                22

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 24 =====

                                                                                        iew
                                                                                           ed
                                                                             ev
                                                             er
                      Figure 8: A sample of finding similar periods to the current one on S&P 500 index.


          To demonstrate the advantages of the proposed approach and verify that each component of

                                                                r
       the model functions effectively, we compare it with several scenarios. In more detail, the two main
       models and those compared with them are as follows:



                                                 pe
           • Clustered pattern-matching approach based on macroeconomic factors with equal weighting
             portfolio construction (CPMM-EW)

           • Clustered pattern-matching approach based on macroeconomic factors with MV portfolio
             construction (CPMM-MV)

           • A model without considering macroeconomic data, namely clustered pattern-matching ap-
                                      ot
             proach with equal weighting portfolio construction (CPM-EW)

           • A model without considering macroeconomic data, namely clustered pattern-matching ap-


                          tn
             proach with MV portfolio construction (CPM-MV)

           • An approach that only considers the pattern-matching procedure on the extracted economic
             cycles treats the data as a single cluster, without involving any clustering. This is called the
             pattern-matching approach based on macroeconomic factors (PMM)


                rin
           • A model with equal weights for macroeconomic factors, without considering joint effects. This
             model names equally weighted macroeconomic factor model (EWMFM).

           Figure 9 illustrates the cumulative return of the proposed approach and its sub-models with


     epdifferent settings and some famous benchmarks- namely hierarchical risk parity (HRP) Lopez de
       Prado (2016), hierarchical equal risk contribution (HERC) Raffinot (2018), online moving average
       reversion (OLMAR) Li et al. (2015), and nested clustered optimization (NCO) López de Prado
       (2020). This comparison enables an evaluation of the effectiveness and specific contributions of
       each component in the proposed model. According to the Figure 9, which is pertinent to the

Pr     S&P 500 market, CPMM-EW and CPMM-MV had earned the highest amount of return, and they
       gained around 110% and 75%, respectively. These amounts are almost twice and one-and-a-half
       times more profitable than the third best approach, which is the index of the S&P 500. Additionally,

                                                             23

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 25 =====

       PMM was almost as effective as the third-best approach, demonstrating that pattern-matching on



                                                                                  iew
       economic cycles is profitable. Also, it is evident that EWMFM’s assumption of equal weights for
       macroeconomic factors and disregard for economic cycles can significantly limit its profitability.
       This underscores the importance of considering interdependencies between factors and adjusting
       their weights over time. It is worth mentioning that removing the part that was related to the
       macroeconomic factors can significantly decrease the amount of cumulative return. In more detail,


                                                                                     ed
       CPM-EW and CPM-MV exhibit the lowest profitability compared to other models, at around 25%
       and 5%, respectively. This demonstrates the insufficiency of clustering alone and highlights the
       critical role of macroeconomic factors in S&P 500 investment strategies. Consequently, clustering
       enhances pattern-matching effectiveness when complemented by features such as macroeconomic
       indicators.
           To have a comprehensive vision of the proposed approaches’ performance, we examine the models

                                                                        ev
       and the aforementioned benchmarks on Dow Jones and Nikkei 225 markets, as well. According to
       Figure 10, similarly, CPMM-EW has the best performance regarding the return earnings with almost
       105% and 110% on Dow Jones and Nikkei 225, respectively. Likewise, akin to the S&P 500 market,
       neglecting macroeconomic factors or considering various weights regarding spillovers, resulted in


                                                          er
       diminished gains, evidenced by the comparatively lower profits of CPM-EW and EWMFM among
       the models under examination. In addition to cumulative return, the proposed approaches and
       benchmarks are compared using several financial metrics. Table 2 compares the approaches based on

                                                             r
       annualized return (AR), annualized standard deviation (AStd), SR (see Equation 18), Probabilistic
       Sharpe ratio (PSR), Sortino ratio (SOR), and Modigliani ratio (MR), that the details of which
       are explained in Appendix F. Based on the performance metrics presented in the table, CPMM-


                                               pe
       EW and CPMM-MV emerge as the top-performing models across multiple factors. These models
       consistently exhibit the highest values for AR, SR, DSR, SOR, and MR across the S&P 500, Dow
       Jones, and Nikkei 225 markets. Additionally, they demonstrate a lower AStd compared to other
       models, further solidifying their superiority. This robust performance underscores the effectiveness
       of the CPMM-EW and CPMM-MV models in optimizing investment strategies, suggesting that their
       incorporation of additional settings, particularly macroeconomic factors, significantly enhances their

                                     ot
       performance across diverse market environments.
           To gain a deeper understanding of the importance of considering the most similar pattern in
       macroeconomic variables to capture their joint effects, we have extended our analysis by focusing


                          tn
       on the second most similar patterns among these variables. To demonstrate the benefits of incor-
       porating this step, as well as the value of considering the most similar pattern, we compare the
       primary models of this study—which rely on the most similar pattern—with models that analyze
       the second most similar pattern. This approach is referred to as Extended Similarity (ES), and the
       results of the comparison with the main models are presented in Appendix G. The results show that

                rin
       while secondary similarity patterns still hold predictive power, their response for shifting dynamics
       of economic conditions exhibits higher variability and decreases the cumulative return in general.
       Understanding these differences provides deeper insights into how macroeconomic forces interact to
       shape portfolio outcomes across varying economic scenarios.


     ep
Pr
                                                          24

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 26 =====

                                                                                     iew
                                                                                        ed
                                                                          ev
                                                           er
                                                              r
                                                pe
                   Figure 9: The cumulative return of the proposed approaches and benchmarks on S&P 500.




                                     ot
                          tn
                rin
     ep   Figure 10: The cumulative return of the proposed approaches and benchmarks on Dow Jones and Nikkei 225.



Pr
                                                            25

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 27 =====

       Table 2: Six different ratios for eleven approaches on several markets. (The bold numbers show the highest value of




                                                                                         iew
       each ratio related to the performance of each approach on the mentioned markets.)
        Metric    Market                                 Approaches
                              CPMM-EW   CPMM-MV   CPM-EW CPM-MV       PMM     EWMFM    Index   HRP     HERC    OLMAR    NCO
                  S&P 500       0.269     0.203    0.072     0.011    0.129    0.117   0.134   0.091   0.119    0.039   0.080
         AR      Dow Jones      0.262     0.142    0.024     0.066    0.090    0.079   0.123   0.083   0.051    0.108   0.037
                 Nikkei 225     0.300     0.224    0.032     0.131    0.180    0.129   0.099   0.048   0.065    0.173   0.154


        AStd



         SR
                  S&P 500
                 Dow Jones
                 Nikkei 225

                  S&P 500
                 Dow Jones
                 Nikkei 225

                  S&P 500
                               0.205
                               0.241
                               0.160

                               1.317
                               1.091
                               1.875

                               0.836
                                         0.208
                                         0.254
                                         0.153

                                         0.976
                                         0.562
                                         1.464

                                         0.523
                                                    0.137
                                                    0.114
                                                    0.134

                                                    0.528
                                                    0.215
                                                    0.237

                                                    0.752
                                                             0.219
                                                             0.119
                                                             0.135

                                                              0.051
                                                              0.560
                                                              0.972

                                                              0.491
                                                                      0.165
                                                                      0.096
                                                                      0.113

                                                                      0.786
                                                                      0.941
                                                                      1.584

                                                                      0.657
                                                                               0.089
                                                                               0.079
                                                                               0.140

                                                                               1.315
                                                                               0.802
                                                                               1.136

                                                                               0.636
                                                                                       0.163
                                                                                       0.218
                                                                                       0.216

                                                                                       0.824
                                                                                       0.566
                                                                                       0.459

                                                                                       0.532
                                                                                            ed 0.131
                                                                                               0.097
                                                                                               0.133

                                                                                               0.695
                                                                                               0.863
                                                                                               0.364

                                                                                               0.519
                                                                                                       0.146
                                                                                                       0.132
                                                                                                       0.134

                                                                                                       0.818
                                                                                                       0.385
                                                                                                       0.492

                                                                                                       0.530
                                                                                                                0.123
                                                                                                                0.112
                                                                                                                0.096

                                                                                                                0.760
                                                                                                                0.964
                                                                                                                1.801

                                                                                                                0.608
                                                                                                                        0.164
                                                                                                                        0.132
                                                                                                                        0.141

                                                                                                                        0.492
                                                                                                                        0.284
                                                                                                                        1.094

                                                                                                                        0.636
         PSR



         SOR
                 Dow Jones
                 Nikkei 225

                  S&P 500
                 Dow Jones
                 Nikkei 225
                               0.723
                               0.715

                               1.306
                               0.821
                               1.002
                                         0.522
                                         0.643

                                         0.765
                                         0.357
                                         1.751
                                                    0.505
                                                    0.393

                                                    0.324
                                                    0.118
                                                    0.156
                                                              0.587
                                                              0.394

                                                              0.040
                                                              0.322
                                                              0.713
                                                                      0.516
                                                                      0.397

                                                                      0.544
                                                                      0.438
                                                                      1.362
                                                                               ev
                                                                               0.521
                                                                               0.400

                                                                               1.204
                                                                               0.376
                                                                               0.629
                                                                                       0.512
                                                                                       0.520

                                                                                       0.370
                                                                                       0.304
                                                                                       0.264
                                                                                               0.517
                                                                                               0.379

                                                                                               0.352
                                                                                               0.396
                                                                                               0.276
                                                                                                       0.621
                                                                                                       0.646

                                                                                                       0.360
                                                                                                       0.238
                                                                                                       0.372
                                                                                                                0.519
                                                                                                                0.400

                                                                                                                0.588
                                                                                                                0.501
                                                                                                                1.220
                                                                                                                        0.641
                                                                                                                        0.407

                                                                                                                        0.313
                                                                                                                        0.171
                                                                                                                        0.600


         MR
                  S&P 500
                 Dow Jones
                 Nikkei 225
                               1.313
                               1.088
                               1.870
                                         0.973
                                         0.561
                                         1.460
                                                    0.527
                                                    0.215
                                                    0.237
                                                              er
                                                              0.051
                                                              0.559
                                                              0.970
                                                                      0.784
                                                                      0.939
                                                                      1.580
                                                                               0.869
                                                                               0.463
                                                                               1.005
                                                                                       0.822
                                                                                       0.564
                                                                                       0.458
                                                                                               0.693
                                                                                               0.861
                                                                                               0.363
                                                                                                       0.816
                                                                                                       0.384
                                                                                                       0.490
                                                                                                                0.758
                                                                                                                0.961
                                                                                                                1.797
                                                                                                                        0.490
                                                                                                                        0.283
                                                                                                                        1.091




                                                                 r
           In order to have a better understanding of the models’ performance through time, the outcomes
       of the proposed models in a rolling window approach are also calculated. The rolling window
       approach enables us to evaluate the robustness of the model across diverse market regimes and


                                                   pe
       varying asset behaviors. Table 3 shows how the models performed in three different 4-year periods;
       from 2016 to 2020, 2017 to 2021, and 2018 to 2023. As can be seen from Table 3, similar to Table 2,
       the proposed approaches, having complete settings, outperformed the other models and benchmarks
       from 2016 to 2023. In greater depth, over the period spanning from 2016 to 2020, with the exception
       of AStd in Nikkei 225, CPMM-EW consistently surpassed other models and benchmarks across all
       evaluated metrics. Likewise, during the intervals from 2017 to 2021 and from 2018 to 2023, CPMM-

                                        ot
       EW distinctly emerged as the top-performing model among the aforementioned counterparts. This
       finding proves the reliability of the proposed methodology and shows that the proposed approach
       can be effective during different periods in different markets. It is noteworthy that the PMM


                               tn
       model, relying solely on pattern matching for economic cycle analysis, yields promising results. In
       fact, it ranks as the third-best method among those considered. This underscores the significance
       of incorporating diverse economic cycles to improve overall system performance. As illustrated
       in Figures 9 and 10, the model’s performance, as measured by various metrics, can suffer when
       macroeconomic factors are assigned equal weights and economic cycles are ignored. This highlights

                 rin
       the importance of dynamically adjusting factor weights over time to enhance the model’s overall
       effectiveness.




     ep
Pr
                                                               26

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 28 =====

       Table 3: Four different ratios for ten approaches on several markets. (The bold numbers show the highest value of




                                                                                          iew
       each ratio related to the performance of each approach on the mentioned markets.)
        Metric    Market                               Approaches
                              CPMM-EW   CPMM-MV    CPM-EW CPM-MV         PMM     EWMFM    HRP     HERC    OLMAR    NCO
                                                       2016 - 2020
                  S&P 500      0.286      0.224     0.082       0.011    0.136    0.133   0.075   0.126    0.106   0.115
         AR      Dow Jones     0.245      0.153     0.067       0.100    0.074    0.034   0.074   0.086    0.138   0.043




                                                                                             ed
                 Nikkei 225    0.333      0.253     0.053       0.173    0.163    0.076   0.093   0.094    0.234   0.153

                  S&P 500      0.186      0.214      0.157      0.199    0.173    0.154   0.153   0.114    0.138   0.157
         AStd    Dow Jones     0.224      0.263      0.143      0.104    0.114    0.144   0.095   0.152    0.173   0.114
                 Nikkei 225    0.154      0.134      0.124      0.153    0.134    0.129   0.124   0.143    0.113   0.123

                  S&P 500      1.537      1.045      0.523      0.056    0.788    0.863   0.491   1.105    0.766   0.733
         SR      Dow Jones     1.093      0.582      0.473      0.966    0.650    0.236   0.780   0.569    0.797   0.378
                 Nikkei 225    2.161      1.883      0.429      1.130    1.213    0.592   0.750   0.659    2.065   1.242


         PSR
                  S&P 500
                 Dow Jones
                 Nikkei 225


                  S&P 500
                               0.803
                               0.697
                               0.823


                               0.204
                                          0.515
                                          0.484
                                          0.624


                                          0.195
                                                     0.763
                                                     0.484
                                                     0.313
                                                                0.485
                                                                0.556


                                                        2017 - 2021
                                                     0.093
                                                                0.364


                                                                 0.035
                                                                             ev
                                                                         0.663
                                                                         0.494
                                                                         0.353


                                                                         0.114
                                                                                  0.431
                                                                                  0.442
                                                                                  0.638


                                                                                  0.087
                                                                                          0.526
                                                                                          0.535
                                                                                          0.363


                                                                                          0.115
                                                                                                  0.546
                                                                                                  0.645
                                                                                                  0.615


                                                                                                  0.107
                                                                                                           0.635
                                                                                                           0.467
                                                                                                           0.445


                                                                                                           0.061
                                                                                                                   0.625
                                                                                                                   0.554
                                                                                                                   0.464


                                                                                                                   0.095
         AR      Dow Jones
                 Nikkei 225

                  S&P 500
                               0.234
                               0.354

                               0.276
                                          0.174
                                          0.234

                                          0.223
                                                     0.047
                                                     0.053

                                                     0.153    er 0.094
                                                                 0.113

                                                                0.237
                                                                         0.124
                                                                         0.153

                                                                         0.173
                                                                                  0.046
                                                                                  0.110

                                                                                  0.163
                                                                                          0.114
                                                                                          0.053

                                                                                          0.184
                                                                                                  0.084
                                                                                                  0.075

                                                                                                  0.142
                                                                                                           0.094
                                                                                                           0.155

                                                                                                           0.155
                                                                                                                   0.055
                                                                                                                   0.145

                                                                                                                   0.174
         AStd



         SR
                 Dow Jones
                 Nikkei 225

                  S&P 500
                 Dow Jones
                               0.195
                               0.153

                               0.741
                               1.198
                                          0.232
                                          0.145

                                          0.875
                                          0.750
                                                     0.123
                                                     0.153

                                                     0.608
                                                     0.286
                                                                 r
                                                                0.164
                                                                0.158

                                                                0.149
                                                                0.765
                                                                         0.095
                                                                         0.145

                                                                         0.661
                                                                         1.304
                                                                                  0.135
                                                                                  0.115

                                                                                  0.532
                                                                                  0.343
                                                                                          0.084
                                                                                          0.112

                                                                                          0.628
                                                                                          1.354
                                                                                                  0.153
                                                                                                  0.143

                                                                                                  0.753
                                                                                                  0.550
                                                                                                           0.125
                                                                                                           0.113

                                                                                                           0.396
                                                                                                           0.752
                                                                                                                   0.114
                                                                                                                   0.135

                                                                                                                   0.547
                                                                                                                   0.485



         PSR
                 Nikkei 225

                  S&P 500
                 Dow Jones
                 Nikkei 225
                               2.309

                               0.643
                               0.785
                               0.784
                                          1.608

                                          0.467
                                          0.543
                                          0.575
                                                  pe 0.348

                                                     0.576
                                                     0.514
                                                     0.415
                                                                0.714

                                                                0.457
                                                                0.556
                                                                0.425

                                                        2018 - 2023
                                                                         1.055

                                                                         0.523
                                                                         0.434
                                                                         0.356
                                                                                  0.951

                                                                                  0.331
                                                                                  0.253
                                                                                  0.546
                                                                                          0.475

                                                                                          0.503
                                                                                          0.456
                                                                                          0.338
                                                                                                  0.526

                                                                                                  0.553
                                                                                                  0.565
                                                                                                  0.663
                                                                                                           1.370

                                                                                                           0.573
                                                                                                           0.534
                                                                                                           0.467
                                                                                                                   1.073

                                                                                                                   0.602
                                                                                                                   0.514
                                                                                                                   0.435


                  S&P 500      0.284      0.225      0.088       0.071   0.149    0.099   0.084   0.134    0.093   0.081
         AR



         AStd
                 Dow Jones
                 Nikkei 225

                  S&P 500
                 Dow Jones
                               0.274
                               0.284

                               0.195
                               0.223
                                        ot0.136
                                          0.204

                                          0.197
                                          0.224
                                                     0.046
                                                     0.083

                                                     0.145
                                                     0.134
                                                                 0.104
                                                                 0.123

                                                                0.225
                                                                0.124
                                                                         0.073
                                                                         0.153

                                                                         0.156
                                                                         0.103
                                                                                  0.143
                                                                                  0.174

                                                                                  0.173
                                                                                  0.165
                                                                                          0.103
                                                                                          0.087

                                                                                          0.125
                                                                                          0.134
                                                                                                  0.045
                                                                                                  0.093

                                                                                                  0.167
                                                                                                  0.145
                                                                                                           0.123
                                                                                                           0.152

                                                                                                           0.115
                                                                                                           0.174
                                                                                                                   0.104
                                                                                                                   0.113

                                                                                                                   0.124
                                                                                                                   0.156



         SR
                 Nikkei 225

                  S&P 500
                 Dow Jones
                 Nikkei 225

                  S&P 500
                              tn
                               0.173

                               0.741
                               1.222
                               1.454

                               0.643
                                          0.143

                                          0.875
                                          0.731
                                          1.140

                                          0.467
                                                     0.174

                                                     0.608
                                                     0.345
                                                     0.606

                                                     0.576
                                                                0.153

                                                                0.149
                                                                0.838
                                                                0.316

                                                                0.457
                                                                         0.125

                                                                         0.661
                                                                         0.709
                                                                         0.956

                                                                         0.523
                                                                                  0.178

                                                                                  0.570
                                                                                  0.864
                                                                                  0.974

                                                                                  0.253
                                                                                          0.153

                                                                                          0.628
                                                                                          0.769
                                                                                          0.672

                                                                                          0.503
                                                                                                  0.142

                                                                                                  0.753
                                                                                                  0.312
                                                                                                  0.802

                                                                                                  0.553
                                                                                                           0.114

                                                                                                           0.396
                                                                                                           0.707
                                                                                                           0.808

                                                                                                           0.573
                                                                                                                   0.163

                                                                                                                   0.547
                                                                                                                   0.665
                                                                                                                   0.652

                                                                                                                   0.602
         PSR

                 rin
                 Dow Jones
                 Nikkei 225
                               0.834
                               0.863
                                          0.613
                                          0.622
                                                     0.523
                                                     0.713
                                                                0.614
                                                                0.512
                                                                         0.554
                                                                         0.645
                                                                                  0.277
                                                                                  0.473
                                                                                          0.485
                                                                                          0.523
                                                                                                  0.621
                                                                                                  0.578
                                                                                                           0.553
                                                                                                           0.668



           Table 4 presents the β + , β − , and ∆β values for various markets, showing that the proposed mod-
                                                                                                                   0.604
                                                                                                                   0.577




       els, such as CPMM-MV and CPMM-CV, exhibit higher β + values compared to other approaches.

     epOn the other hand, some benchmark models, such as NCO and HRP, have shown inferior β + in
       comparison to our proposed models. This can be mainly attributed to the incorporation of macroe-
       conomic factors and the regime-aware design of our models, while the benchmark models tend to
       overlook the importance of macroeconomic variables in the process of constructing portfolios.

Pr
                                                              27

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 29 =====

                               Table 4: Different beta ratios for eleven approaches on several markets.




                                                                                            iew
        Metric    Market                                   Approaches
                              CPMM-EW   CPMM-MV     CPM-EW CPM-MV        PMM     EWMFM    Index   HRP     HERC    OLMAR   NCO
                  S&P 500        0.9       0.8         0.6       0.7      0.8       0.3     1      0.6      0.6     0.7    0.4
         β+      Dow Jones       0.9      0.75        0.55       0.6      0.7      0.35     1     0.55     0.55     0.4    0.3
                 Nikkei 225     0.85      0.75        0.55       0.6      0.6      0.35     1      0.5     0.55     0.4    0.3

                  S&P 500       -0.2       -0.3        -0.5      -0.6     -0.4     -0.6    -1      -0.4    -0.4    -0.8    -0.6




                                                                                               ed
         β−      Dow Jones      -0.3       -0.2        -0.5      -0.4     0.1     -0.55    -1     -0.42   -0.35    -0.5   -0.55
                 Nikkei 225     -0.2       -0.2        -0.5      -0.4     -0.2    -0.55    -1      -0.5   -0.55    -0.5    -0.6

                  S&P 500        0.7        0.5        0.1       0.1      0.4     -0.3      0      0.2     0.2     -0.1    -0.2
         ∆β      Dow Jones       0.6       0.55       0.05       0.2      0.6     -0.2      0     0.13     0.2     -0.1   -0.25
                 Nikkei 225     0.65       0.55       0.05       0.2      0.3     -0.2      0     0.1      0.2     -0.1    -0.3



           Moreover, in the proposed models with β − values of -0.3 and -0.2, we demonstrate that these

                                                                                 ev
       strategies maintain resilience during market downturns. Unlike other approaches, such as OLMAR
       and NCO, which tend to exhibit high correlation with downward market trends, our models ef-
       fectively manage downside risk by dynamically adjusting to changing economic conditions. This
       allows us to minimize losses in downward markets, mitigating the risk typically associated with
       high-sensitivity stocks.
                                                                 er
           Additionally, in the PMM model, which relies solely on macroeconomic variables, we observe
       higher resilience during downward market movements compared to models like CPM-EW, which do

                                                                    r
       not incorporate macroeconomic factors. This highlights the importance of macroeconomic signal
       extraction in improving downside protection while still benefiting from market upswings.
           In addition, it is essential to note the importance of joint effect in the proposed models. In the


                                                     pe
       EWMFM model, in which we do not use spillover, the resilience of the model to downward trends
       in the market has been weakened. This can be mainly because of considering the signals of macroe-
       conomic variables that could not influence that stock significantly. This evidence suggests that
       incorporating macroeconomic-driven insights into portfolio construction can enhance risk-adjusted
       returns, enabling a more robust strategy that capitalizes on market upswings while remaining de-
       fensive during downturns.
                                         ot
           Furthermore, to evaluate the performance of the proposed model and verify its robustness,
       models with various settings are tested on out-of-sample data from 2023, to 2025, with the results
       of each model presented in Table 5.


                               tn
                 rin
     ep
Pr
                                                                 28

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 30 =====

       Table 5: Four different ratios for six different settings on several markets. (The bold numbers show the highest value




                                                                                           iew
       of each ratio related to the performance of each approach on the mentioned markets.)
        Metric      Market                                                   Approaches
                                    CPMM-EW             CPMM-MV             CPM-EW           CPM-MV           PMM        EWMFM
                    S&P 500             0.082                0.042              0.009           0.011         0.012         0.0347
        AR



        AStd
                    Dow Jones
                    Nikkei 225
                    S&P 500
                    Dow Jones
                    Nikkei 225
                                        0.091
                                        0.0925
                                          0.352
                                          0.272
                                          0.201
                                                             0.0873
                                                             0.0824
                                                             0.328
                                                             0.264
                                                             0.202
                                                                                0.043
                                                                                0.047
                                                                               0.366
                                                                               0.301
                                                                               0.295
                                                                                              ed 0.051
                                                                                                0.0563
                                                                                                 0.253
                                                                                                 0.233
                                                                                                 0.255
                                                                                                              0.0634
                                                                                                              0.0564
                                                                                                               0.321
                                                                                                               0.188
                                                                                                               0.233
                                                                                                                             0.077
                                                                                                                            0.0754
                                                                                                                            0.364
                                                                                                                            0.204
                                                                                                                            0.199

        SR
                    S&P 500
                    Dow Jones
                    Nikkei 225
                    S&P 500
                                         0.2324
                                         0.3346
                                         0.4602
                                         0.635
                                                             0.1280
                                                             0.3307
                                                             0.4079
                                                             0.553
                                                                                ev
                                                                               0.0246
                                                                               0.1429
                                                                               0.1593
                                                                                0.452
                                                                                                0.0435
                                                                                                0.2189
                                                                                                0.2208
                                                                                                 0.047
                                                                                                              0.0374
                                                                                                              0.3372
                                                                                                              0.2421
                                                                                                               0.527
                                                                                                                            0.9533
                                                                                                                            0.3775
                                                                                                                            0.3789
                                                                                                                            0.513
        PSR         Dow Jones
                    Nikkei 225
                                         0.532
                                         0.671                  er
                                                             0.512
                                                             0.634
                                                                                0.445
                                                                                0.373
                                                                                                 0.418
                                                                                                 0.294
                                                                                                               0.496
                                                                                                               0.533
                                                                                                                            0.504
                                                                                                                            0.611


                                                                   r
           As shown in Table 5, the final proposed models, with their optimized settings and tuned param-
       eters, demonstrate superior performance compared to scenarios where a part of the model is altered


                                                    pe
       or certain proposed approaches are omitted. The significance of each model component is evident in
       the outcomes across different settings. For instance, the EWMFM model, which assigns equal weight
       to each macroeconomic variable and overlooks the varying influence of these variables on stocks with
       different characteristics—such as market size, capitalization, or pricing power—experiences a no-
       table impact on its overall performance. On the other hand, incorporating macroeconomic variables
       and performing pattern matching can significantly enhance model performance. This is evident in

                                        ot
       the superior performance of the PMM model compared to the CPM-MV model, which neglects
       macroeconomic factors and their influence on stock market shifts. As a result,this table acts as a
       tool to assess the importance of each component in the proposed model, evaluating both its overall


                            tn
       performance and the contribution of individual parts using out-of-sample data. It also serves to
       verify the model’s robustness, as the consistent performance across various settings and components
       indicates reliability and stability under different conditions.

       6. Discussion on macroeconomic factors

                rin
           In this section, we analyze how the seven macroeconomic factors mentioned in Remark1 are se-
       lected among 18 macroeconomic factors via BorutaShap; also, the impact and relationships between
       macroeconomic factors and stock markets are examined. BorutaShap is a feature selection method
       that synergistically combines the Boruta algorithm with SHapley Additive exPlanations (SHAP)

     epvalues to identify the most relevant features in a dataset. This method harnesses the strengths
       of both Boruta’s robust feature selection and SHAP’s interpretability, making it particularly ef-
       fective for complex datasets with numerous features Sebastián and González-Guillén (2024). More
       details of this model are explained in Appendix B. The selection is guided by the dynamic nature

Pr     of financial markets, which means these features are evaluated over time to assess changes in their
       importance across different market conditions.



                                                                29

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 31 =====

           Figure 11 shows how the effects of macroeconomic factors on the S&P 500 index change during



                                                                                      iew
       a 10-year period from 2013 to 2023. According to Figure 11, CPI and IR are the most effective
       macroeconomic factors on the S&P 500 index between 2013 and 2023. Additionally, to better
       understand the most influential factors, the average rank of each macroeconomic factor over time
       is calculated, and Figure 12 demonstrates the macroeconomic factors with their ranks of effect on
       the S&P 500 index. Based on these analyses, the top seven factors are selected for consideration in


                                                                                         ed
       this study. So, CPI, IR, GDP, IP, DGDP, UR, and PPI are the factors chosen for the first step of
       the pattern-matching procedure.




                                                                           ev
                                                            er
                                                               r
                     Figure 11: Rank of macroeconomic factors’ effects on S&P 500 between 2013 to 2023.


                                                 pe
                                      ot
                          tn
                rin
     ep             Figure 12: Average of each macroeconomic factor’s rank on S&P 500 from 2013 to 2023.


           To better understand the distinct roles macroeconomic variables play in our proposed asset


Pr     selection methods, consider the example shown in Figure 13. The figure illustrates that down-
       ward movements in CPI have a statistically significant impact on the performance of many stocks,
       highlighting the importance of incorporating macroeconomic factors, such as CPI, when evaluating


                                                            30

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 32 =====

       market trends. However, the direction and magnitude of CPI’s influence vary across stocks, de-



                                                                                       iew
       pending on their market size and characteristics. For instance, the causes of CPI increases—such
       as consumer-driven inflation or supply-side pressures—can lead to divergent outcomes. Companies
       with strong pricing power may benefit from rising CPI by passing on costs, while those with limited
       pricing power often face downward pressure on their stock prices. Our proposed method incorporates
       a spillover approach to analyze the impact of macroeconomic variables on selected assets, enabling


                                                                                          ed
       a nuanced understanding of how macroeconomic variables impact different stocks. On the other
       hand, upward movements of other macroeconomic variables, such as the UR, can cause shifts in the
       behavior of many stocks. This may be caused by the broad economic implications of rising unem-
       ployment, which signals weakening consumer demand, reduced corporate revenues, and heightened
       market uncertainty, leading to significant downward pressure on a wide range of stocks, particularly
       those sensitive to economic cycles. Likewise, for CPI, the magnitude of this macroeconomic vari-

                                                                            ev
       able’s effect on market shifts should be considered for stocks with varying market capitalizations,
       pricing power, or sector exposures, as these characteristics determine their sensitivity to economic
       downturns signaled by rising unemployment.



                                                            er
                                                               r
                                                 pe
                                     ot
                          tn
                  Figure 13: Comparison of proposed models based on joint effects of macroeconomic factors.




                rin
          Moreover, to determine how macroeconomic factors influence three major indexes—S&P 500,
       Dow Jones, and Nikkei 225—a volatility spillover index based on Equation 34 was implemented. The
       normalized correlations, along with their means and standard deviations, are presented in Figure
       14 and Table 6, respectively.


     ep
Pr
                                                             31

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 33 =====

                                                                                         iew
                                                                                            ed
                                                                              ev
                                                              er
                                                                 r
                                                  pe
                                      ot
                          tn
                rin     Figure 14: The volatility spillover from macroeconomic factors to three indexes.




     ep
Pr
                                                              32

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 34 =====

       Table 6: The mean of each macroeconomic factor’s strength on three stock indexes. (The bold numbers show the




                                                                                    iew
       highest mean of the strength of each macroeconomic factor on the mentioned indexes.)
                                                                   Mean
                                Values/Indexes     S&P 500      Dow Jones     Nikkei 225
                                      IR            58.37         173.6         172.7
                                     UR             16.61         49.04         53.89
                                     GDP
                                      IP
                                    DGDP
                                     CPI
                                     PPI
                                                    0.318
                                                    3.988
                                                    4.350
                                                    102.5
                                                    3.012
                                                                  0.941
                                                                  11.78
                                                                  12.84
                                                                  302.7
                                                                  8.888
                                                                                1.053
                                                                                12.82
                                                                                14.05
                                                                                319.3
                                                                                9.611
                                                                                       ed
                                                                          ev
           According to Figure 14 and Table 6, the most influential macroeconomic factors in the three
       mentioned indexes are CPI and IR, while the least powerful one is GDP. In greater detail, Figure
       14 illustrates that throughout the entire time series, CPI has consistently been the most influential
       macroeconomic factor. IR, the second most significant factor, showed peak strength between 2012


                                                           er
       and 2015, and again after 2021. It is worth noting that although UR was significantly important
       among all factors at the beginning of the time series (1995 to 2005), its strength gradually declined
       after that period. In addition, PPI maintained consistent strength throughout the early days of

                                                              r
       all three markets. From another point of view, Figure 14 examines the temporal significance of
       macroeconomic factors on proposed model. CPI and IR consistently emerge as key drivers, but their
       relative influence has fluctuated across economic cycles. The proposed model effectively captures


                                                pe
       these shifts. For instance, the S&P 500’s sensitivity to IR reached a low point during the 1995-
       2005 period but surged between 2013 and 2015 and again in 2022. Similar fluctuations are evident
       for CPI, often exhibiting inverse relationships with IR. By accounting for these cyclical dynamics,
       the model’s predictive power is significantly enhanced. Also, the mean volatility spillovers from
       CPI to the S&P 500, Dow Jones, and Nikkei 225 are 102.5, 302.7, and 319.3, respectively. These
       values significantly surpass other spillovers originating from different macroeconomic factors. This

                                     ot
       demonstrates the substantial impact that certain macroeconomic factors such as CPI and IR can
       exert on financial markets. Moreover, these results, along with the magnitude of influence each
       macroeconomic factor has on indexes, are utilized in Section 4.4 during the extraction of final


                          tn
       signals. To elaborate further, the stronger a macroeconomic factor is, the greater its effect on the
       final signals of assets.
           Moreover, we investigate the influence of incorporating only one macroeconomic factor or ex-
       cluding an individual one on the performance of the currently leading model (CPMM-EW). The
       influence of only one macroeconomic factor means that the joint effect of multiple macroeconomic

                rin
       variables is not considered; instead, each macroeconomic variable individually reflects its impact on
       the proposed model. Excluding an individual macroeconomic factor means that the joint effect of
       the other six macroeconomic factors has been captured and reflected in the leading model.



     ep
Pr
                                                           33

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 35 =====

                                                                                       iew
                                                                                          ed
       Figure 15: The impact of considering and not considering each macroeconomic factor on the portfolio performance.




                                                                            ev
           Figure 15 shows how considering only one macroeconomic factor or excluding a single factor,
       the performance-return and SR- of the proposed approach may change. The system performs best
       when considering only one macroeconomic factor, with peak performance observed for CPI and IR
       (circles). Additionally, when running the algorithm with six macroeconomic factors while excluding


                                                             er
       one (triangles), the least favorable outcomes occur when CPI and IR are excluded. For example,
       within the S&P 500, using only CPI and IR results in the highest Sharpe Ratios, approximately
       0.5 and 0.41, respectively. Moreover, excluding CPI and IR from the analysis results in the largest


                                                                r
       losses for the system, with Sharpe Ratios (SRs) approximately 0.9 and 1.1, respectively. Similar
       results are observed for the Dow Jones and Nikkei 225, where CPI and IR also emerge as the most
       important macroeconomic factors. These findings are consistent with the patterns shown in Figure


                                                 pe
       14 and the data in Table 6, highlighting CPI and IR as the most influential macroeconomic factors
       across all studied markets. Moreover, excluding CPI and IR from the analysis results in the largest
       losses for the system, with Sharpe Ratios (SRs) approximately 0.9 and 1.1, respectively. Similar
       results are observed for the Dow Jones and Nikkei 225, where CPI and IR also emerge as the most
       important macroeconomic factors. These findings are consistent with the patterns shown in Figure
       14 and the data in Table 6, highlighting CPI and IR as the most influential macroeconomic factors
       across all studied markets.
                                      ot
           For the final analysis, we assessed the appropriateness of the selected parameters by testing the
       two best-performing models, CPMM-EW and CPMM-MV, on the S&P 500 with various parameter
       settings. Evaluating different parameters of the proposed model allows us to verify whether the

                           tn
       selected parameters perform effectively in conjunction with other model settings and demonstrate
       the robustness of the overall approach. These models, which have the most parameters, were chosen
       for this evaluation. In this approach, the number of clusters (nc), length of windows (w), and the
       number of considered macroeconomic factors (7), lambda (λ), are assigned different values. Table


                rin
       7 shows the parameter settings of CPMM-EW and CPMM-MV on the S&P 500 and demonstrates
       that the chosen parameters for each section in the proposed approaches are robust.




     ep
Pr
                                                             34

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 36 =====

                                Table 7: Parameter setting of CPMM-EW and CPMM-MV.




                                                                                  iew
                            Metrics/Models                     Parameters
                             CPMM-EW           nc − 2    nc − 1    nc    nc − 1     nc + 2
                               Return          0.201     0.214 0.269 0.235          0.198
                                  Std          0.224     0.234 0.205 0.215          0.225
                                  SR           0.898     0.914 1.317 1.092          0.881
                                 PSR
                             CPMM-EW
                               Return
                                  Std
                                  SR
                                               0.774
                                               w−2
                                               0.215
                                               0.249
                                               0.836
                                                         0.795 0.836 0.743
                                                         w−1       w
                                                         0.226 0.269 0.253
                                                         0.214 0.205 0.221
                                                         1.056 1.317 1.146
                                                                          w+1
                                                                                     ed
                                                                                    0.694
                                                                                    w+2
                                                                                    0.243
                                                                                    0.237
                                                                                    0.985
                                 PSR           0.673     0.778 0.836 0.801          0.753
                             CPMM-MV
                               Return
                                  Std
                                  SR
                                               λ−2
                                               0.236
                                               0.262
                                               0.900
                                                         λ−1
                                                         0.214
                                                         0.243
                                                                   λ
                                                                 0.203
                                                                 0.208
                                                                        ev
                                                         0.881 0.976 0.926
                                                                          λ+1
                                                                          0.185
                                                                          0.200
                                                                                    λ+2
                                                                                    0.172
                                                                                    0.197
                                                                                    0.873
                                 PSR           0.502

                                                          er
                                                         0.514 0.523 0.491          0.489

          In general, our findings emphasize the importance of adapting portfolio strategies to different

                                                             r
       economic scenarios. By identifying key macroeconomic factors and adjusting their weights within
       specific regimes, we achieve more accurate predictions. Unlike traditional models that equally
       weight features, our approach leverages spillover effects to enhance pattern recognition and portfolio


                                               pe
       performance, providing deeper insights into market dynamics.

       6.1. Explanation of Topological Data Analysis
           To further enrich our understanding of macroeconomic influences on financial markets, we em-
       ploy Topological Data Analysis (TDA) to detect structural anomalies within key economic indica-
       tors. Specifically, we utilize the three most influential macroeconomic factors identified in Table 6
                                     ot
       and analyze their historical behavior across three major stock indexes dating back to 1997. Lever-
       aging the TDA model, as discussed in Zomorodian (2012), Ravishanker and Chen (2019), allows
       us to extract deeper insights into the temporal dynamics of these indicators. This complementary


                          tn
       step serves to validate and enrich the pattern-matching approach discussed throughout the paper
       by highlighting time periods where macroeconomic disruptions align with shifts in market behavior.
       The mathematical framework underpinning the TDA implementation is summarized in Appendix
       H.
           The anomalies identified through TDA provide an additional layer of macroeconomic insight

                rin
       that aligns with and supports our portfolio construction methodology. Specifically, they reveal
       time windows where abrupt changes in economic indicators—such as IR, CPI, and UR—correspond
       with significant market events or shifts in investor behavior. For instance, Figure 16 shows that
       anomalies in IR and CPI in 2009 and 2020 align with known economic crises, during which the S&P


     ep500 and Dow Jones indexes experienced structural breaks in performance. Similarly, a rise in these
       indicators in 2023 coincided with substantial upward movements in the same indexes, confirming
       the predictive value of such anomalies.
           Also, the relationship between UR and the Nikkei 225 index follows a distinct path. A sharp
       increase in UR during 2020 was associated with a notable decline in the Nikkei 225, despite relatively

Pr     stable movements in western markets. This observation illustrates differing sensitivities of regional
       markets to specific macroeconomic disruptions, reinforcing the need for geographically tailored
       investment strategies. Overall, the integration of TDA into our analysis highlights the complex

                                                          35

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 37 =====

       interplay between macroeconomic patterns and financial market dynamics. It supports our broader



                                                                                         iew
       methodology by identifying critical inflection points, which, when captured through macroeconomic
       pattern matching, can enhance both predictive accuracy and strategic asset selection.




                                                                                            ed
                                                                              ev
                                                              er
                                                                 r
                                                   pe
       Figure 16: The times that experienced anomalies on IR, CPI, and UR and their corresponding on markets’ time series.


       7. Conclusion

            This paper introduces a macro-financial framework within the OLPS paradigm, offering a novel

                                       ot
       approach to understanding how macroeconomic regimes influence asset selection. Our results show
       that this framework enhances portfolio performance by aligning asset selection with prevailing
       macroeconomic trends, reflecting regime-sensitive market behavior.


                           tn
            Initially, we apply a hierarchical clustering model to assess the relationships between various
       assets, computed using the SU metric. Comparative analyses indicate that hierarchical clustering
       with SU more effectively captures asset interdependencies than traditional methods such as K-Means
       and correlation. Subsequently, with assets categorized into distinct clusters, a novel double pattern-
       matching methodology is employed. This involves applying a pattern-matching approach to seven


                rin
       macroeconomic factors, identifying analogous periods in the past based on economic determinants.
       This stage acts as a cycle detector, enhancing the conditions for subsequent training, testing, and
       fitting steps. In the second phase of the double pattern-matching process, a distinct pattern-
       matching technique is applied to assets, specifically targeting time instances exhibiting behavior
       analogous to the current period. This contributes to refining the accuracy of asset pattern matching,

     epas the approach selectively explores periods that closely align with the present timeframe in terms
       of macroeconomic factors. It is noteworthy that during this phase, the degree of impact exerted by
       each macroeconomic factor on the markets is determined. These influences are then incorporated
       into the signal aggregation process. Subsequently, an asset with the highest predicted return is

Pr     chosen from each cluster to build the signals, and these selected assets are combined to form the
       portfolio. The allocation of these assets to the portfolio is executed through two methods: an
       equally weighted approach and the Mean-Variance (MV) model.


                                                               36

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 38 =====

           The findings of this study underscore the substantial advantage of incorporating macroeconomic



                                                                                  iew
       factors into portfolio construction. By considering these variables, investment strategies exhibited
       superior performance relative to traditional approaches that neglect economic conditions. Aware-
       ness of macroeconomic variable movements results in portfolios with higher ∆β compared to models
       that neglect macroeconomic movements, indicating not only a greater potential for profit during
       favorable market conditions (as measured by β + ), but also enhanced resilience during downturns


                                                                                     ed
       (as measured by β − ). This emphasizes the importance of accounting for the joint impact of macroe-
       conomic dynamics in the portfolio construction process. Furthermore, the research demonstrates
       that clustering techniques, when applied in conjunction with macroeconomic features, significantly
       enhance the identification of relevant patterns within the data. Notably, the CPI and IR emerged as
       the most influential macroeconomic factors impacting the performance of the three examined mar-
       kets. Our proposed methodology surpasses traditional OLPS models by employing a regime-specific,

                                                                        ev
       weighted pattern matching technique, resulting in more accurate predictions. This augmentation
       not only has the potential to amplify investment returns but also serves to mitigate the inherent
       risk within the OLPS framework.
           The enhancement of the proposed methodology’s performance can be pursued through various


                                                          er
       avenues. One way involves the exploration of alternative OLPS methodologies, specifically con-
       sidering the substitution of the present approaches with meta-learning strategies, to assess their
       potential in elevating the overall strategy performance. Furthermore, a broader examination of

                                                             r
       relationship metrics other than the SU, such as Transfer Entropy (TE), could be undertaken to
       capture a more nuanced understanding of the associations between different variables. Addition-
       ally, the incorporation of diverse metrics, including but not limited to Environmental, Social, and


                                               pe
       Corporate Governance (ESG) factors and the credit scores of companies, can be contemplated to
       foster the development of a more comprehensive portfolio. These considerations aim not only to
       refine the existing strategy but also to open avenues for a more holistic and effective approach to
       OLPS.

       References
                                     ot
       Y. Aı̈t-Sahalia, F. Matthys, E. Osambela, and R. Sircar. When uncertainty and volatility are
         disconnected: Implications for asset pricing and portfolio performance. Journal of Econometrics,


                          tn
         248:105654, 2025. ISSN 0304-4076. doi: https://doi.org/10.1016/j.jeconom.2023.105654. URL
         https://www.sciencedirect.com/science/article/pii/S0304407623003706.

       H. Bäcklund, A. Hedblom, and N. Neijman. A density-based spatial clustering of application with
         noise. Data Mining TNM033, 33:11–30, 2011.


                rin
       D. H. Bailey and M. Lopez de Prado. The sharpe ratio efficient frontier. Journal of Risk, 15(2):13,
         2012.

       S. Barak and T. Mokfi. Evaluation and selection of clustering methods using a hybrid group mcdm.


     ep   Expert Systems with Applications, 138:112817, 2019. ISSN 0957-4174. doi: https://doi.org/
          10.1016/j.eswa.2019.07.034. URL https://www.sciencedirect.com/science/article/pii/
          S0957417419305135.

       J. Baz, H. Guo, N. Pedersen, J. Tsai, and Y. Chen. Does macro matter? integrating macroeconomic


Pr        insights into portfolio construction. The Journal of Portfolio Management, 51(6):—, April 2025.

       Bloomberg.
         core?,   2023.
                        Macro hedge funds had a banner year. can they stage an en-
                              URL https://www.bloomberg.com/opinion/articles/2023-01-18/

                                                          37

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 39 =====

         macro-hedge-funds-had-a-banner-2022-how-about-2023?leadSource=uverify%20wall#
         xj4y7vzkg.


                                                                                  iew
       S. T. Bodilsen. Large-Dimensional Portfolio Selection with a High-Frequency-Based Dynamic Factor
          Model. Journal of Financial Econometrics, page nbae018, 08 2024. ISSN 1479-8409. doi: 10.
          1093/jjfinec/nbae018. URL https://doi.org/10.1093/jjfinec/nbae018.



                                                                                     ed
       C. Borio. The financial cycle and macroeconomics: What have we learnt? Journal of Banking
         Finance, 45:182–198, 2014. ISSN 0378-4266. doi: https://doi.org/10.1016/j.jbankfin.2013.07.031.
         URL https://www.sciencedirect.com/science/article/pii/S0378426613003063. Liquidity
         Risk, Reform of Bank Regulation, and Risk Management, Liquidity Risk Management, New York,
         USA, 14 June 2014 Liquidity Risk, Reform of Bank Regulation, and Risk Management, Risk


                                                                        ev
         Management and Reform of Bank Regulation, Beijing, China, 22–23 April 2013 Liquidity shocks,
         governance, systemic risk and financial stability.

       A. Borodin, R. El-Yaniv, and V. Gogan. Can we learn to beat the best stock. Advances in Neural
         Information Processing Systems, 16, 2003.


                                                          er
       H. Bouzgarrou, Z. Ftiti, W. Louhichi, and M. Yousfi. What can we learn about the market reaction
         to macroeconomic surprise? evidence from the covid-19 crisis. Research in International Business


                                                             r
         and Finance, 64:101876, 2023. ISSN 0275-5319. doi: https://doi.org/10.1016/j.ribaf.2023.101876.
         URL https://www.sciencedirect.com/science/article/pii/S0275531923000028.

       S. Chavleishvili and E. Moench. Natural disasters as macroeconomic tail risks. Journal of Econo-

                                               pe
         metrics, 247:105914, 2025. ISSN 0304-4076. doi: https://doi.org/10.1016/j.jeconom.2024.105914.
         URL https://www.sciencedirect.com/science/article/pii/S0304407624002653.

       F. Chazal and B. Michel. An introduction to topological data analysis: fundamental and practical
         aspects for data scientists. Frontiers in artificial intelligence, 4:667963, 2021.


                                     ot
       B. Chiu, E. Keogh, and S. Lonardi. Probabilistic discovery of time series motifs. In Proceedings of
         the Ninth ACM SIGKDD International Conference on Knowledge Discovery and Data Mining,
         KDD ’03, page 493–498, New York, NY, USA, 2003. Association for Computing Machinery. ISBN
         1581137370. doi: 10.1145/956750.956808. URL https://doi.org/10.1145/956750.956808.

                          tn
       C. Conrad. The effects of money supply and interest rates on stock prices, evidence from two
         behavioral experiments. Applied Economics and Finance, 8(2), 2021.

       T. M. Cover. Universal portfolios. Mathematical finance, 1(1):1–29, 1991.

                rin
       T. M. Cover, J. A. Thomas, and J. Kieffer. Elements of information theory. SIAM Review, 36(3):
         509–510, 1994.

       P. Das and A. Banerjee. Meta optimization and its application to portfolio selection. In Proceedings


     ep  of the 17th ACM SIGKDD international conference on Knowledge discovery and data mining,
         pages 1163–1171, 2011.

       H. F. de Mendonça and R. R. R. Dı́az. Can ignorance about the interest rate and macroeco-
         nomic surprises affect the stock market return? evidence from a large emerging economy. The

Pr       North American Journal of Economics and Finance, 64:101868, 2023. ISSN 1062-9408. doi:
         https://doi.org/10.1016/j.najef.2022.101868. URL https://www.sciencedirect.com/science/
         article/pii/S1062940822002030.


                                                          38

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 40 =====

       Y. Deng, Y. Wang, and T. Zhou. Macroeconomic expectations and expected returns. Journal of
         Financial and Quantitative Analysis, pages 1–37, 2024.


                                                                                  iew
       F. X. Diebold and K. Yilmaz. Better to give than to receive: Predictive directional measurement
         of volatility spillovers. International Journal of forecasting, 28(1):57–66, 2012.




                                                                                     ed
       Y. Dong, Y. Hao, and D. Lu. A framework for timely and accessible long-term forecasting of shale
         gas production based on time series pattern matching. International Journal of Forecasting, 41
         (2):821–843, 2025.

       T. A. Dyer, D. T. Roulstone, and A. Van Buskirk. Disclosure similarity and future stock return
         comovement. Management Science, 70(7):4762–4780, 2024.


                                                                        ev
       A. Fereydooni and M. Mahootchi. An algorithmic trading system based on a stacked generalization
         model and hidden markov model in the foreign exchange market. Global Finance Journal, 56:
         100825, 2023.

       A. Fereydooni, S. Barak, and S. M. Asaad Sajadi. A novel online portfolio selection approach based

                                                          er
         on pattern matching and esg factors. Omega, 123:102975, 2024. ISSN 0305-0483. doi: https://doi.
         org/10.1016/j.omega.2023.102975. URL https://www.sciencedirect.com/science/article/
         pii/S0305048323001391.

                                                             r
       L. Ferrara and P. Guérin. What are the macroeconomic effects of high-frequency uncertainty shocks?
         Journal of Applied Econometrics, 33(5):662–679, 2018.


                                               pe
       Forbes. Hedge funds end 2022 on a sour note as global macro outperformed and multi-
         strategy stalled, 2023. URL https://www.forbes.com/sites/jacobwolinsky/2023/01/18/
         hedge-funds-end-2022-on-a-sour-note-as-global-macro-outperformed-and-multi-strategy-stalled/

       A. A. Gaivoronski and F. Stella. On-line portfolio selection using stochastic programming. Jour-
         nal of Economic Dynamics and Control, 27(6):1013–1043, 2003a. ISSN 0165-1889. doi: https:
                                     ot
         //doi.org/10.1016/S0165-1889(02)00053-2. URL https://www.sciencedirect.com/science/
         article/pii/S0165188902000532. High-Performance Computing for Financial Planning.



                          tn
       A. A. Gaivoronski and F. Stella. On-line portfolio selection using stochastic programming. Journal
         of Economic Dynamics and Control, 27(6):1013–1043, 2003b.

       S. Guo, J.-W. Gu, and W.-K. Ching. Adaptive online portfolio selection with transaction costs.
         European Journal of Operational Research, 295(3):1074–1086, 2021.


                rin
       L. Györfi, G. Lugosi, and F. Udina. Nonparametric kernel-based sequential investment strate-
         gies. Mathematical Finance: An International Journal of Mathematics, Statistics and Financial
         Economics, 16(2):337–357, 2006.

       E. Hazan and C. Seshadhri. Efficient learning algorithms for changing environments. In Proceedings

     ep  of the 26th annual international conference on machine learning, pages 393–400, 2009.

       D. P. Helmbold, R. E. Schapire, Y. Singer, and M. K. Warmuth. On-line portfolio selection using
         multiplicative updates. Mathematical Finance, 8(4):325–347, 1998.


Pr     H. Iyetomi, H. Aoyama, Y. Fujiwara, W. Souma, I. Vodenska, and H. Yoshikawa. Relationship
         between macroeconomic indicators and economic cycles in us. Scientific reports, 10(1):8420,
         2020.

                                                          39

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 41 =====

       M. Jayashankar and B. N. Rath. The dynamic linkage between exchange rate, stock price and



                                                                                  iew
        interest rate in india. Studies in Economics and Finance, 34(3):383–406, 2017.
       E. Keany. BorutaShap : A wrapper feature selection method which combines the Boruta feature
         selection algorithm with Shapley values., Nov. 2020. URL https://doi.org/10.5281/zenodo.
         4247618.



                                                                                     ed
       I. N. Khindanova and S. T. Rachev. Value at risk: Recent advances. Handbook of Analytic Com-
          putational Methods in Applied Mathematics, pages 801–858, 2019.
       Y. M. Kim and K. H. Kang. Bayesian inference of multivariate regression models with endogenous
         markov regime-switching parameters. Journal of Financial Econometrics, 20(3):391–436, 2022.



                                                                        ev
       D. Korobilis and M. Schröder. Monitoring multi-country macroeconomic risk: A quantile factor-
         augmented vector autoregressive (qfavar) approach. Journal of Econometrics, page 105730,
         2024. ISSN 0304-4076. doi: https://doi.org/10.1016/j.jeconom.2024.105730. URL https:
         //www.sciencedirect.com/science/article/pii/S0304407624000769.



                                                          er
       B. Li and S. C. Hoi. Online portfolio selection: A survey. ACM Computing Surveys (CSUR), 46
         (3):1–36, 2014.



                                                             r
       B. Li, S. C. Hoi, and V. Gopalkrishnan. Corn: Correlation-driven nonparametric learning approach
         for portfolio selection. ACM Transactions on Intelligent Systems and Technology (TIST), 2(3):
         1–29, 2011.


                                               pe
       B. Li, P. Zhao, S. C. Hoi, and V. Gopalkrishnan. Pamr: Passive aggressive mean reversion strategy
         for portfolio selection. Machine learning, 87:221–258, 2012.
       B. Li, S. C. Hoi, D. Sahoo, and Z.-Y. Liu. Moving average reversion strategy for on-line portfolio
         selection. Artificial Intelligence, 222:104–123, 2015.
       X. Lin, M. Zhang, Y. Zhang, Z. Gu, Y. Liu, and S. Ma. Boosting moving average reversion strategy
                                     ot
         for online portfolio selection: a meta-learning approach. In Database Systems for Advanced
         Applications: 22nd International Conference, DASFAA 2017, Suzhou, China, March 27-30, 2017,
         Proceedings, Part II 22, pages 494–510. Springer, 2017.


                          tn
       X. Lin, C. Li, W. Ren, X. Luo, and Y. Qi. A new feature selection method based on symmetrical
         uncertainty and interaction gain. Computational biology and chemistry, 83:107149, 2019.
       W. Liu and I. Garrett. Regime-dependent effects of macroeconomic uncertainty on realized


                rin
        volatility in the u.s. stock market. Economic Modelling, 128:106483, 2023. ISSN 0264-9993.
        doi: https://doi.org/10.1016/j.econmod.2023.106483. URL https://www.sciencedirect.com/
        science/article/pii/S026499932300295X.
       M. Lopez de Prado. Building diversified portfolios that outperform out-of-sample. Journal of


     ep Portfolio Management, 2016.
       M. M. López de Prado. Machine Learning for Asset Managers. Elements in Quantitative Finance.
        Cambridge University Press, 2020. doi: 10.1017/9781108883658.
       F. Ma, X. Lu, J. Liu, and D. Huang. Macroeconomic attention and stock market return pre-

Pr       dictability. Journal of International Financial Markets, Institutions and Money, 79:101603,
         2022. ISSN 1042-4431. doi: https://doi.org/10.1016/j.intfin.2022.101603. URL https://www.
         sciencedirect.com/science/article/pii/S104244312200083X.

                                                          40

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 42 =====

       H. Markowitz. Portfolio selection*. The Journal of Finance, 7(1):77–91, 1952. doi: https://doi.



                                                                                  iew
         org/10.1111/j.1540-6261.1952.tb01525.x. URL https://onlinelibrary.wiley.com/doi/abs/
         10.1111/j.1540-6261.1952.tb01525.x.

       A. A. Mustafa, C.-Y. Lin, and M. Kakinaka. Detecting market pattern changes: A machine learning
         approach. Finance Research Letters, 47:102621, 2022.



                                                                                     ed
       P. K. Narayan, S. Narayan, and K. S. Thuraisamy. Can institutions and macroeconomic factors
         predict stock returns in emerging markets? Emerging Markets Review, 19:77–95, 2014. ISSN 1566-
         0141. doi: https://doi.org/10.1016/j.ememar.2014.04.005. URL https://www.sciencedirect.
         com/science/article/pii/S156601411400020X.

       M. Phillot. Us treasury auctions: A high-frequency identification of supply shocks. American
        Economic Journal: Macroeconomics, 17(1):245–273, 2025.
                                                                        ev
       T. Raffinot. The hierarchical equal risk contribution portfolio. Available at SSRN 3237540, 2018.

       N. Ravishanker and R. Chen. Topological data analysis (tda) for time series. arXiv preprint
         arXiv:1909.10604, 2019.
                                                          er
       P. J. Rousseeuw. Silhouettes: a graphical aid to the interpretation and validation of cluster analysis.


                                                             r
         Journal of computational and applied mathematics, 20:53–65, 1987.

       A. A. Salisu, R. Swaray, and T. F. Oloko. Improving the predictability of the oil–us stock nexus:
         The role of macroeconomic variables. Economic Modelling, 76:153–171, 2019. ISSN 0264-9993.

                                               pe
         doi: https://doi.org/10.1016/j.econmod.2018.07.029. URL https://www.sciencedirect.com/
         science/article/pii/S0264999317319454.

       C. Sebastián and C. E. González-Guillén. A feature selection method based on shapley values robust
         for concept shift in regression. Neural Computing and Applications, pages 1–23, 2024.


                                     ot
       A. Sensoy and C. Sobaci. Effects of volatility shocks on the dynamic linkages between exchange
         rate, interest rate and the stock market: The case of turkey. Economic Modelling, 43:448–
         457, 2014. ISSN 0264-9993. doi: https://doi.org/10.1016/j.econmod.2014.09.005. URL https:


                          tn
         //www.sciencedirect.com/science/article/pii/S0264999314003320.

       W. F. Sharpe. Capital asset prices: A theory of market equilibrium under conditions of risk. The
        journal of finance, 19(3):425–442, 1964.

       Y. Shu, C. Yu, and J. M. Mulvey. Dynamic asset allocation with asset-specific regime forecasts.

                rin
         Annals of Operations Research, pages 1–34, 2024.

       F. A. Sortino and L. N. Price. Performance measurement in a downside risk framework. the Journal
         of Investing, 3(3):59–64, 1994.


     epP. Taveeapiradeecharoen and N. Aunsri. A bayesian approach for dynamic variation of specific
         sectors in stock exchange: A case study of stock exchange thailand (set) indexes. Wireless
         Personal Communications, 115:2995–3032, 2020.

       X. Wang, Q. Huang, and S. Zhang. Effects of macroeconomic factors on stock prices for brics using

Pr       the variational mode decomposition and quantile method. The North American Journal of Eco-
         nomics and Finance, 67:101939, 2023. ISSN 1062-9408. doi: https://doi.org/10.1016/j.najef.2023.
         101939. URL https://www.sciencedirect.com/science/article/pii/S1062940823000621.

                                                          41

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 43 =====

       Y. Wang and D. Wang. Market symmetry and its application to pattern-matching-based portfolio
         selection. The Journal of Financial Data Science, 1(2):78–93, 2019.


                                                                                      iew
       I. H. Witten and E. Frank. Data mining: practical machine learning tools and techniques with java
          implementations. Acm Sigmod Record, 31(1):76–77, 2002.




                                                                                         ed
       Y. Zhu, M. Imamura, D. Nikovski, and E. Keogh. Matrix profile vii: Time series chains: A new
         primitive for time series data mining (best student paper award). In 2017 IEEE International
         Conference on Data Mining (ICDM), pages 695–704, 2017. doi: 10.1109/ICDM.2017.79.

       A. Zomorodian. Topological data analysis. Advances in applied and computational topology, 70:
         1–39, 2012.


                                                                           ev
       Štefan Lyócsa, P. Molnár, T. Plı́hal, and M. Širaňová. Impact of macroeconomic news, regulation
          and hacking exchange markets on the volatility of bitcoin. Journal of Economic Dynamics and
          Control, 119:103980, 2020. ISSN 0165-1889. doi: https://doi.org/10.1016/j.jedc.2020.103980.
          URL https://www.sciencedirect.com/science/article/pii/S0165188920301482.


       Appendix                                             er
       Appendix A
                                                               r
                       Table A.1: Full names and abbreviations of the examined macroeconomic factors.

             Macroeconomic factor
             Consumer Price Index
             Interest Rate
             Gross Domestic Product
                                                 pe
                                          Abbreviation
                                          CPI
                                          IR
                                          GDP
                                                            Macroeconomic factor
                                                            Price To Rent
                                                            Corporate Profit
                                                            Wage Growth
                                                                                                Abbreviation
                                                                                                PTR
                                                                                                CP
                                                                                                WG
             Debt to GDP                  DGDP              Currency Transaction Report         CTR
             Industrial Production
             Unemployment Rate
             Producer Price Index
                                     ot   IP
                                          UR
                                          PPI
                                                            Money Supply M2
                                                            Gold Reserve
                                                            Carbon Dioxide Emission
                                                                                                M2
                                                                                                GR
                                                                                                CE
             Saving Rate
             Balance Trade

       Appendix B
                          tn              SR
                                          BT
                                                            Consumer Credit
                                                            Household Debt
                                                                                                CC
                                                                                                HHD




                rin
       Boruta Algorithm
          The Boruta algorithm is an all-relevant feature selection method that identifies important fea-
       tures by comparing them against shadow features. The process involves several steps Sebastián and
       González-Guillén (2024):


     ep   1. Shadow Features Creation: Let X = [X1 , X2 , . . . , Xp ] be the original feature matrix. For
             each feature Xi , a shadow feature Xishadow is created by randomly permuting the values of Xi .
             The shadow feature matrix is Xshadow = [X1shadow , X2shadow , . . . , Xpshadow ].
          2. Model Training: Train a machine learning model, typically a tree-based model such as

Pr           Random Forest or XGBoost, on the combined dataset [X, Xshadow ].
          3. Importance Scores: Calculate the importance scores for both the original and shadow
             features. Let IS(Xi ) denote the importance score of feature Xi .


                                                            42

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 44 =====

          4. Comparison and Decision: For each original feature Xi , compare IS(Xi ) with the maxi-
             mum importance score of the shadow features IS(Xjshadow ):

                                  Zi = IS(Xi ) − max(IS(Xjshadow )),
                                                                                               iew
                                                                                   ∀j ∈ {1, 2, . . . , p}   (B.1)

             Use statistical testing (e.g., a two-tailed test) to determine if Zi is significantly greater than
             zero.
                • Features with Zi significantly greater than zero are marked as important.
                • Features with Zi significantly less than zero are marked as unimportant.        ed
                • Features with Zi not significantly different from zero are tentatively marked for further
                  evaluation.

       SHAP Values
                                                                                  ev
          SHAP values provide a unified measure of feature importance based on cooperative game theory.
       For a given model f and input x, the SHAP value ϕi for feature i is defined as:

                               ϕi =
                                           X

                                      κ⊆{1,...,p}\{i}           er
                                                        |κ|!(p − |κ| − 1)!
                                                                p!
                                                                           [f (κ ∪ {i}) − f (κ)]            (B.2)



                                                                   r
          where κ represents all possible subsets of features excluding i, and f (κ) denotes the model
       prediction when only features in κ are considered.

       BorutaShap Methodology

                                                   pe
         1. Compute SHAP Values: Train the chosen machine learning model on the dataset X and
            compute SHAP values ϕi for each feature i.
         2. Shadow Features and Importance Calculation: Create shadow features as described in
            the Boruta algorithm. Train the model on the combined dataset and compute SHAP values
            for both original and shadow features.

                                      ot
         3. Iterative Comparison: For each feature Xi , compute the difference:

                                      ZiSHAP = ϕi − max(ϕshadow
                                                         j      ),              ∀j ∈ {1, 2, . . . , p}      (B.3)



                          tn
             Perform statistical tests to assess the significance of ZiSHAP .
          4. Feature Decision:
                • Features with ZiSHAP significantly greater than zero are deemed important.
                • Features with ZiSHAP not significantly different from zero are evaluated further in subse-


                rin
                  quent iterations.
                • The iterative process continues until all features are decisively marked as important or
                  unimportant.



     epAppendix C
           The ideal correlation matrix Om is an m × m symmetric, positive semi-definite matrix. It
       possesses a unit diagonal, and its off-diagonal elements are defined as 1 minus the inverse of one
                                               1
       less than the total number of assets ( 1−m ).


Pr                                                   

                                            Om =  ...
                                                     
                                                       1          1
                                                           · · · 1−m
                                                           ..
                                                              1
                                                               .
                                                             1−m
                                                                      
                                                                   .. 
                                                                    . 
                                                                      ···   1
                                                                                                    (C.1)



                                                                 43

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 45 =====

          When a collection of m assets is chosen in such a way that their correlation matrix aligns with
       Om , it enables the creation of a portfolio with no volatility.

                                                    lim
                                                   m→∞ 1 − m
                                                            1
                                                                =0                 iew
          This suggests that as the portfolio grows in size, the correlation matrix Om gradually converges
                                                                                                           (C.2)




                                                                                      ed
       towards the identity matrix Im . Discovering m assets whose correlation matrix Cm exactly replicates
       Om is an unattainable objective. Nevertheless, our goal is to get as close as possible to approximating
       Om .
          The distance (d ) between Cm and Om can be quantified by computing the Frobenius norm of
       the disparity between the two matrices.

                                                  d = ∥Cm − Om ∥F
                                                                         ev                                (C.3)
       A reduced value of d signifies a greater level of precision, rendering it a suitable metric for evaluating
       the extent of diversification.

       Appendix D
       Hopkins score                                      er
                                                             r
           The Hopkins score serves as a statistical metric for evaluating the clustering potential of a
       dataset. It gauges the propensity of data points in the dataset to assemble into clusters. The
       Hopkins Statistic typically falls within the range of 0 to 1. A low value (close to 0) suggests that
       the data is uniformly distributed and does not exhibit natural clusters, making it challenging to

                                               pe
       perform clustering effectively. A high value (closer to 1) suggests that the data is more suitable
       for clustering, indicating that there are natural clusters or structures in the data that clustering
       algorithms can potentially uncover. The Hopkins score, denoted as HS, is calculated by the formula:
       HS = x/(x + y). In this formula, x represents the sum of distances between a sample of data points
       and their nearest neighbors within the original dataset, and y signifies the sum of distances between

                                     ot
       the original dataset and its nearest neighbors within a simulated subsampled dataset.

       Calinski-Harabasz score
           The Calinski-Harabasz score, sometimes referred to as the Variance Ratio Criterion, serves as

                          tn
       a measure for assessing the effectiveness of clustering within a dataset. It quantifies the ratio of
       variance between clusters to variance within clusters, where a higher score denotes more distinct
       and well-defined clusters. The formula for calculating the Calinski-Harabasz score is as follows:

                                                          Tr(B)/nc

                rin                            CH =
                                                       Tr(W )/(η − nc)

       In the equation, CH stands for the Calinski-Harabasz score, T r represents the trace of a matrix,
       B signifies the between-cluster scatter matrix, W denotes the within-cluster scatter matrix, nc
       indicates the number of clusters, and η is the total count of data points. The ideal number of
                                                                                                           (D.1)




     epclusters is typically determined by selecting the value of k that maximizes the Calinski-Harabasz
       score. A higher CH score indicates a well-separated arrangement of data into distinct clusters,
       while a lower score suggests that the data may not display clear clustering patterns.


Pr
                                                          44

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 46 =====

       Davies-Bouldin score



                                                                                  iew
          The Davies-Bouldin score, a metric employed to assess the effectiveness of clustering within a
       dataset, quantifies the average similarity between each cluster and its closest neighboring cluster.
       Lower scores are indicative of more distinct, well-separated clusters. The formula for computing
       the Davies-Bouldin score is as follows:



                                                                                     ed
                                                     n                      
                                                 1 X            Qi + Qj
                                         DB =          c max                                         (D.2)
                                                 nc      j̸=i   d (ci , cj )
                                                      i=1

       where, DB stands for the Davies-Bouldin score, nc represents the number of clusters, Qi signifies
       the average distance between data points in cluster i and its centroid, d(ci , cj ) denotes the distance
       between the centroids of clusters i and j, and the summation extends across all nc clusters. The

                                                                            ev
       optimal number of clusters is determined by selecting the value of nc that minimizes the Davies-
       Bouldin score. A lower DB score indicates well-separated and distinct clusters, while a higher score
       suggests potential overlap or less well-defined cluster boundaries.

       Dunn index

                                                             er
           Developed by Dunn in 1974, Dunn’s index is an internal evaluation method. Its goal is to
       recognize cohesive clusters where the means of distinct clusters are maximally separated. The
       definition of Dunn’s index is as follows:

                                             D=
                                                                r
                                                  min1≤i<j≤nc {d(ci , cj )}
                                                  max1≤i≤nc {dmax (ci )}
                                                                                                          (D.3)


                                               pe
       where D is the Dunn index, nc is the number of clusters, ci and cj are clusters, d(ci , cj ) is the
       distance between ci and cj , and dmax (ci ) is the maximum distance within ci Barak and Mokfi
       (2019).

       Silhouette score

                                     ot
           This metric, also known as the Silhouette Coefficient, is a measure used to assess the effectiveness
       of a clustering model. It ranges from -1 to +1. A score of 1 indicates well-separated clusters, while
       0 suggests that the clusters are indistinct or have little separation between them. On the other


                          tn
       hand, a score of -1 implies misassigned or improperly classified clusters.
           To compute the Silhouette Coefficient for each sample (n), both the average distance within
       clusters (α) and the average distance to the nearest neighboring cluster (ζ) are determined. The
       formula for calculating the Silhouette Coefficient is as follows:



                rin                              SSn =
                                                             ζn − α n
                                                            max(αn , ζn )

       In Equation D.4, αn and ζn represent the average distances of object n to other objects within its
       own cluster and to the nearest neighboring cluster, respectively.
                                                                                                          (D.4)




     ep
Pr
                                                             45

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 47 =====

       Appendix E



                                                                                      iew
                                                                                         ed
                                                                           ev
                                                            er
                                                               r
                                                pe
                       Figure E.1: The comparison of different ∆β on six other macroeconomic factors.


          As demonstrated in Figure E.1, stocks comprising the S&P 500 index exhibit varying responses

                                     ot
       to macroeconomic variables. While some stocks react positively or negatively to changes in specific
       macroeconomic factors, others display a neutral tendency toward upward or downward movements.
       These neutral stocks do not contribute added value to our proposed model, as our approach primarily
       captures signals by reflecting the behavior of macroeconomic variables on stock performance.

       Appendix F         tn
       Probabilistic Sharpe Ratio
           While adhering to stringent scientific protocols is common practice, there exists a substantial


                rin
       risk of disseminating false positive outcomes when introducing strategies. Although skewness and
       kurtosis does not affect the point estimate of Sharpe ratio, it greatly impacts its confidence bands,
       and consequently its statistical significance. So, an important conclusion is that, despite of the
       Non Normality of the returns distributions, the SR would always follows a Normal distribution.


     epTo overcome the limitations identified in the preceding section, Bailey and Lopez de Prado (2012)
       developed the Probabilistic Sharpe Ratio (PSR) metric. Given a predetermined benchmark Sharpe
       Ratio (SR∗ ), the estimated Sharpe Ratio ( c
       of this metric is as follows:
                                                  SR) can be probabilistically determined. The calculation




Pr                                          P SR(SR∗ ) = P rob[SR ≤ c
                                                                    SR]                                    (F.1)




                                                            46

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 48 =====

       therefore:
                                                                                 √

                                                                                  iew
                                       "             #                                         
                                      c − SR∗
                                     (SR                                c − SR∗ ) L − 1
                                                                       (SR
                      P SR(SR∗ ) = Z                     = Z q                                           (F.2)
                                       σ̂(SR)                      1 c2           γ4 −3 d2
                                                               1 + 2 SR − γb3 SR + 4 SR
                                          c                                   c   c



       here, SR

                                                                                     ed
             c is its estimated SR, L is the sample length, γb3 and γb4 are the skewness and kurtosis of
       the returns distribution for the selected strategy, and Z is the cumulative function of the standard
       Normal distribution.

       Sortino Ratio
          The SOR was initially introduced by Sortino and Price (1994), and it is defined as follows:

                                                    SOR =
                                                                R−rf
                                                                 σ−       ev
       here, σ − represents the downside standard deviation. While the SR takes into account all obser-
                                                                                                           (F.3)




                                                           er
       vations when computing the standard deviation, the SOR specifically considers only the adverse
       variance.

       Modigliani Ratio
         the MR is defined as follows:                        r
                                                 M R = SR × σb + rf                                        (F.4)


                                               pe
       where σb is the standard deviation of the benchmark, which is S&P 500, Dow Jones, and Nikkei
       225, in this study.

       Appendix G
          To better understand how macroeconomic variables jointly impact our proposed models, we ex-

                                     ot
       tended our similarity pattern analysis beyond the closest matches. Instead of relying solely on the
       most similar patterns, we incorporated the second-most similar patterns across different macroe-
       conomic variables. These models are named as extended similarity clustered pattern-matching
       approach based on macroeconomic factors with equal weighting portfolio construction (ESCPMM-

                          tn
       EW) and extended similarity clustered pattern-matching approach based on macroeconomic factors
       with MV portfolio construction (ESCPMM-MV). This comparison allowed us to analyze portfolio
       behavior under distinct yet related macroeconomic conditions.
          By moving from the most similar joint patterns to the second-most similar ones, we captured


                rin
       how different macroeconomic forces work together in building portfolio outcomes. This approach
       provided a clearer view of the joint effects at play, revealing how portfolio performance shifts under
       varying combinations of macroeconomic influences.




     ep
Pr
                                                           47

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 49 =====

                                                                                       iew
                                                                                          ed
                                                                            ev
                                                             er
                                                                r
                                                 pe
                                      ot
                           tn
                rin
                  Figure G.1: Comparison of proposed models based on joint effects of macroeconomic factors.


     ep    As demonstrated in Figure G.1, considering various joint effects among macroeconomic variables
       can significantly influence the outcomes of our proposed models. This stems from the fact that the
       most similar patterns among macroeconomic factors tend to exhibit strong and stable interplay

Pr     forces, reinforcing the robustness of their combined effects. However, as we extend our analysis to
       less similar patterns, this robustness gradually diminishes, potentially leading to weaker or more
       inconsistent interactions. This decline suggests that while secondary similarity patterns still hold


                                                             48

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

===== PAGE 50 =====

       predictive value, their influence on portfolio behavior may exhibit higher variability, reflecting the
       evolving interplay among macroeconomic forces.

       Appendix H
       Data Representation
                                                                                   iew
                                                                                      ed
          Let X = {x1 , x2 , ..., xn } be the dataset consisting of n data points, where each xi belongs to a
       high-dimensional space Rd .

       Simplicial Complex Construction
          Given a distance metric d(xi , xj ) measuring the pairwise dissimilarity between data points, we
       construct a simplicial complex K on the dataset X as follows:


                                                                         ev
           • Define a threshold parameter ϵ to determine the neighborhood of each data point.

           • For each data point xi , construct a simplex (vertex) [xi ].

           • Connect two vertices [xi ] and [xj ] with an edge (1-simplex) if d(xi , xj ) ≤ ϵ.

                                                          er
           • Generalize to higher-dimensional simplices (e.g., triangles, tetrahedra) based on higher-order
             interactions among data points.

                                                             r
          The resulting simplicial complex captures the topological structure of the dataset across various
       spatial scales.

       Persistent Homology
                                                pe
          Persistent homology is computed to analyze the topological features of the simplicial complex
       K across different values of ϵ. This involves computing homology groups Hk (K) representing k-
       dimensional topological features such as connected components, loops, voids, etc.


                                     ot
           • For each dimension k, compute the k-th homology group Hk (K) using algebraic topology
             techniques (e.g., matrix reduction).

           • Track the birth and death of topological features as the threshold parameter ϵ varies.


                          tn
           • Represent persistence diagrams or barcodes to visualize the persistence of topological features
             across different scales.

       Anomaly Detection


                rin
           Anomalies are detected based on deviations from the expected persistence patterns in the per-
       sistence diagrams. Anomalies may manifest as:

           • Persistent topological features appearing or disappearing unexpectedly.


     ep    • Unusual clustering or distribution of persistence points in the diagrams.

           • Presence of high-dimensional topological features that deviate from the norm.



Pr
                                                           49

This preprint research paper has not been peer reviewed. Electronic copy available at: https://ssrn.com/abstract=6115073

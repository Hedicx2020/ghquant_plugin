===== PAGE 1 =====

              A Bipartite Graph Approach to U.S.-China

                           Cross-Market Return Forecasting

                  Jing Liu∗1 , Maria Grith2 , Xiaowen Dong3 , and Mihai Cucuringu4,1,5

                                1
                                    Department of Statistics, University of Oxford, UK
                            2
                                Finance Department, Neoma Business School, France
                     3
                         Department of Engineering Science, University of Oxford, UK
              4
                  Department of Mathematics, University of California Los Angeles, US
          5
              Oxford-Man Institute of Quantitative Finance, University of Oxford, UK




                                                        Abstract

         This paper studies cross-market return predictability through a machine learning framework
     that preserves economic structure. Exploiting the non-overlapping trading hours of the U.S. and
     Chinese equity markets, we construct a directed bipartite graph that captures time-ordered pre-
     dictive linkages between stocks across markets. Edges are selected via rolling-window hypothesis
     testing, and the resulting graph serves as a sparse, economically interpretable feature-selection
     layer for downstream machine learning models. We apply a range of regularized and ensem-
     ble methods to forecast open-to-close returns using lagged foreign-market information. Our
     results reveal a pronounced directional asymmetry: U.S. previous-close-to-close returns contain
     substantial predictive information for Chinese intraday returns, whereas the reverse effect is
     limited. This informational asymmetry translates into economically meaningful performance
     differences and highlights how structured machine learning frameworks can uncover cross-market
     dependencies while maintaining interpretability.

∗
    Corresponding author; Email: jing.liu@exeter.ox.ac.uk


                                                            1

===== PAGE 2 =====

Keywords: Return prediction, cross-market analysis, machine learning, bipartite graphs

JEL Classification: G17, G15, C58




1    Introduction

Return prediction remains a central problem in empirical asset pricing and portfolio management, yet

its statistical difficulty is amplified by noise, non-stationarity, and nonlinear dependence structures

in financial markets. While machine learning methods have become increasingly prevalent in single-

market forecasting applications (Chen et al., 2015; Wang, 2024; Yang and He, 2026), comparatively

little attention has been paid to stock-level cross-market return prediction under realistic trading-

session timing constraints.

    Most existing studies on return forecasting focus on predicting within a single market. For

example, Chen et al. (2015) apply a Long Short-Term Memory (LSTM) model to predict stock

returns in the Chinese market, while Wang (2024) studies U.S. stock return prediction using neural

network models. Similarly, Yang and He (2026) propose an intraday volume-based uncertainty

proxy to predict return direction in the Chinese market. These studies demonstrate the growing

use of machine learning methods in single-market settings. By contrast, research on cross-market

interactions has largely emphasized contemporaneous co-movement, spillovers, or causal transmission

rather than explicit stock-level return prediction. For instance, Eun and Shim (1989) analyze the

international transmission of stock market movements using vector autoregression, Baur and Jung

(2006) evaluate contemporaneous return correlations using GARCH models, and Rapach et al. (2013)

document the leading role of the U.S. market through causality tests. Sarwar (2014) examine the

relationship between U.S. market uncertainty and European equity returns during crisis periods,

while Jung et al. (2024) study interdependency patterns between the U.S. and Chinese markets

using threshold overnight co-movement processes.

    Only a limited number of studies have attempted explicit cross-market predictive analysis using

machine learning models. For example, Lee and Yoo (2020) apply a deep neural network to fuse

information from the U.S. and South Korean markets for index-level return prediction, and Kumar

et al. (2024) propose a graph neural network to model volatility spillovers across markets. However,


                                                  2

===== PAGE 3 =====

most existing work operates at the index level, and to our knowledge no prior study has examined

stock-level cross-market return prediction between the U.S. and Chinese markets under realistic

trading-session timing.

   Our study fills this gap by developing a directed bipartite graph framework for stock-level

cross-market return forecasting between the U.S. and Chinese equity markets. We construct a

time-ordered bipartite graph that selects cross-market predictors based on rolling-window screening,

thereby capturing directed predictive links across non-overlapping trading sessions. The selected

predictors are then embedded into a suite of ten machine learning models to forecast next-session

open-to-close (OPCL) returns in each market.

   Empirically, we demonstrate a pronounced directional asymmetry: U.S. market information

is substantially more informative for predicting Chinese stock returns than vice versa. Sharpe

Ratios (SRs) obtained when forecasting Chinese stocks using U.S. predictors consistently exceed

those in the reverse direction. We further show that both the graph-based selection mechanism and

cross-market information contribute materially to predictive performance.

   Sector-level patterns in the estimated graph reveal economically interpretable transmission

channels across markets. For instance, sector-level aggregation of the bipartite graph reveals

meaningful cross-sector transmission patterns rather than a block-diagonal structure. Our focus

is on documenting directional cross-market predictability and the structure of the associated

dependency graph rather than designing a fully implementable trading strategy. Accordingly,

performance metrics are reported pre-transaction-cost and without liquidity-optimized weighting,

and should be interpreted as evidence of predictive asymmetry rather than deployable alpha.

   Our setting is economically and statistically distinctive because the U.S. and Chinese equity

sessions do not overlap. This implies that U.S. previous-close-to-close (pvCLCL) information is fully

observed before the subsequent Chinese OPCL window begins, yielding a clean timing structure for

cross-market prediction. The directed bipartite graph can therefore be interpreted as a time-ordered

map of potential information transmission channels across markets, rather than a contemporaneous

correlation network.

   The structure of the paper is arranged as follows. Section 2 provides a detailed review of related

work. Section 3 describes the data we use and the definitions of financial terms involved. Section 4

introduces the graph-based methodology for feature selection and prediction. Section 5 presents the

                                                 3

===== PAGE 4 =====

evaluation metrics and experimental results. Finally, Section 6 summarizes the study and discusses

future research directions.



2     Related Literature

2.1   Cross-Market Analysis and Prediction

Global financial markets have become increasingly interconnected with the intensification of inter-

national economic and financial integration. As a result, shocks, volatility, and information can

propagate rapidly across countries through multiple transmission channels. A substantial body of

research therefore examines cross-market linkages, including price discovery, return co-movement,

volatility spillovers, and broader measures of financial interconnectedness, typically within economet-

ric frameworks. Such interconnectedness has motivated studies of directional information flow and

market leadership across countries. For example, Liu and An (2011) examine information transmis-

sion and price discovery between the U.S. and Chinese markets. Asgharian et al. (2013) study how

economic and geographical relationships across countries affect stock market returns. Mohammadi

and Tan (2015) analyze daily returns and volatility dynamics in the U.S. and Chinese markets.

Clements et al. (2015) investigate global transmission of news and volatility across financial markets,

while Ahmad et al. (2018) explore market interconnectedness through return and volatility spillovers.

Huang and Liu (2023) construct a financial network to characterize cross-market risk spillovers

and interaction topology. These studies primarily emphasize contemporaneous relationships and

transmission mechanisms rather than explicit stock-level return prediction.

    Beyond studying cross-market information propagation, a growing strand of research incorporates

signals from multiple markets into forecasting models to improve predictive performance. Such

integration typically relies on feature engineering that embeds external market indicators, deep

learning architectures that fuse multi-market inputs, or graph-based models designed to capture

inter-market dependencies. For example, Thenmozhi and Sarath Chand (2016) use foreign index

information to enhance index prediction, Lee and Yoo (2020) develop multimodal deep learning

models for cross-market index forecasting, and Lin et al. (2025) leverage external futures market

data to predict movements of the China Securities Index. Gong et al. (2025) propose a cross-market

volatility forecasting framework exploiting risk transmission across markets.

                                                  4

===== PAGE 5 =====

   However, much of this literature focuses on aggregate indices or volatility measures rather than

stock-level return prediction. Moreover, network structures are often employed to characterize

spillovers and interconnectedness rather than as predictive screening devices for individual stocks.

Explicit stock-level cross-market return forecasting under time-ordered, non-overlapping trading

sessions remains largely unexplored. Applying our methodology in this setting is therefore novel.

Empirically, the directed bipartite structure reveals pronounced asymmetry in cross-market pre-

dictability, with U.S. stocks exerting substantially stronger predictive influence on Chinese stocks

than vice versa. These findings align with the literature documenting asymmetric cross-market

return predictability with a leading role for the U.S.. Rapach et al. (2013) show that lagged U.S.

market returns possess substantial predictive power for foreign equity markets, while the reverse

predictability is considerably weaker, highlighting the central role of the U.S. in global price discovery.

Similarly, Siliverstovs (2017) finds that the predictive influence of the U.S. is particularly pronounced

during market downturns, reinforcing the view that U.S. information dominates international return

dynamics. Focusing specifically on China-related markets, Mohammadi and Tan (2015) document

significant return and volatility spillovers from the U.S. to Chinese mainland and Hong Kong, with

weaker effects in the opposite direction.


2.2   Graph Methods in Finance

Graph methods provide a way to represent relationships among financial entities, rather than

treating each entity in isolation. The use of graphs aligns with the view that financial systems

are interconnected (Bardoscia et al., 2021), and that modeling these interconnections can improve

forecasting and risk-management (Chen and Fan, 2025). Many financial phenomena, such as asset

co-movements, spillovers and supply-chain linkages, are naturally represented as graphs.

   Bipartite graphs, which originate in graph theory and network science as representations of

relationships between two distinct sets of nodes (Guillaume and Latapy, 2006; Newman, 2018),

provide a natural framework for modeling interactions across disjoint groups. In economics and

finance, bipartite structures arise in contexts such as credit networks, production networks, and

supply-chain relationships, where connections form between two heterogeneous sets of entities

rather than within a single homogeneous market. For instance, Kley et al. (2020) study extremal

dependence for operational risk by a bipartite graph. Wang and Chen (2020) design a bipartite-

                                                    5

===== PAGE 6 =====

graph-based recommender for crowdfunding with sparse data. In econometrics, Wu et al. (2024)

propose a quasi-maximum likelihood approach to estimate a bipartite network influence model.

   A growing literature applies graph neural networks (GNNs) and related architectures to financial

forecasting tasks. Wang et al. (2021) provide a survey of GNN methods in financial applications,

including stock movement prediction, loan default risk assessment, recommender systems, fraud

detection, and other financial events. Chen et al. (2018) apply a Graph Convolutional Network

(GCN) to integrate information from related companies and improve stock price prediction. Li et al.

(2021) propose an LSTM-relational GCN that captures inter-stock relationships through correlation

matrices to predict overnight movements. Capponi et al. (2024) develop a GNN framework for

asset pricing using supply-chain data. Zhang et al. (2025) incorporate cross-stock spillover effects

to forecast multivariate realized volatilities, and Luo et al. (2025) construct a semantic company

relationship graph to enhance stock price forecasting.

   Some recent empirical work extends graph-based forecasting to richer and more dynamic

architectures. For example, Cheng and Li (2021) employ a Graph Attention Network (GAT) to

model momentum spillovers in stock returns, while Kumar et al. (2024) introduce a temporal GAT

that combines graph convolution and attention mechanisms to capture structural and temporal

dependencies across global market indices. Lee et al. (2025) show that GCN- and GAT-based models

can outperform conventional machine learning baselines by exploiting symmetric interdependencies

among financial indices. Related research also incorporates multimodal information into graph

construction. Cheng et al. (2022) integrate financial events and news into a multimodal GNN

framework for price prediction, and Liu et al. (2024) develop a multiscale dynamic GCN that

combines textual and numerical inputs to forecast stock movements.

   Despite these advances, most graph-based forecasting models construct within-market networks,

where edges are defined through contemporaneous similarity, correlation, or learned attention

mechanisms. Such graphs typically capture symmetric interdependencies among assets within a

single market and are primarily used to enhance predictive performance through richer representation

learning. In contrast, our framework constructs a directed bipartite graph across two distinct markets,

where edges are formed through time-ordered predictive screening rather than contemporaneous

association. The resulting graph serves as a feature-selection mechanism for stock-level cross-market

return prediction, explicitly exploiting the non-overlapping trading sessions between the U.S. and

                                                  6

===== PAGE 7 =====

Chinese markets.


2.3   Machine Learning in Finance

Driven by increasing data availability and computational power, the application of machine learning in

finance has expanded substantially in recent years. Compared to classical time-series and econometric

models, such as ARIMA and GARCH, machine learning approaches are often considered better

suited to high-dimensional and nonlinear settings. A survey by Rundo et al. (2019) documents that

machine-learning-based systems demonstrate superior overall performance compared to traditional

approaches. Another survey by Kelly et al. (2023) highlights how machine learning methods have

become established in empirical financial research. Key applications include forecasting asset returns,

volatility estimation, fraud detection, and algorithmic trading. Forecasting asset returns remains

inherently difficult due to low signal-to-noise ratios, structural instability, and nonlinear dependence

patterns. Moreover, evidence of predictive gains is often sensitive to model specification and feature

construction. These challenges partly motivate the adoption of flexible machine learning methods

and the incorporation of richer information sets. Given recent developments in machine learning, its

applications in finance can be grouped into several major categories: traditional machine learning

methods, deep learning methods, and large-language-model-based methods.

   For traditional machine learning methods, Huang et al. (2005) employ support vector machines

(SVM) to predict the direction of weekly price movements. Kumar and Thenmozhi (2006) investigate

the application of SVM and Random Forests (RF) in predicting the direction of a market index. Cakra

and Trisedya (2015) incorporate sentiment information and use a basic linear regression model

for stock price prediction. Thenmozhi and Sarath Chand (2016) predict stock prices of several

major indices using support vector regression. Yang and He (2026) propose a novel proxy and apply

Extreme Gradient Boosting (XGBoost) to predict return directions in the Chinese market.

   For deep learning methods, Chen et al. (2015) use an LSTM model for sequence learning and

Chinese stock return forecasting. Wang (2024) investigates the performance of neural network

models in predicting stock returns. A survey by Gao et al. (2024) highlights the expanding use of

deep neural networks, convolutional neural networks, recurrent neural networks, and other advanced

architectures in financial contexts.

   For large-language-model-based methods, Nie et al. (2024) review how Large Language Models

                                                   7

===== PAGE 8 =====

(LLMs) are applied in finance. Ding et al. (2023) demonstrate the effectiveness of LLMs in forecasting

stock returns. Chen et al. (2023) propose a framework that integrates ChatGPT and GNN to forecast

stock movements. Chen et al. (2024) investigate the ability of ChatGPT for stock return forecasting.

    Despite these advances, most existing studies focus on single-market return prediction and rely

primarily on information drawn from within the same market. Additional information is often shown

to improve predictive performance, yet it is typically incorporated in contemporaneous or symmetric

settings. Very few studies employ machine learning methods in stock-level cross-market forecasting

environments characterized by asynchronous trading sessions and explicitly time-ordered information

flows. Differing from existing studies, our framework combines directed bipartite screening with

a second-stage machine learning prediction step, enabling systematic exploitation of cross-market

dependencies, temporal ordering, and asymmetric predictive structure.



3       Data

The stock data used in this study cover several of the world’s largest markets by market capitalization,

including the New York Stock Exchange (NYSE), Nasdaq, the Shanghai Stock Exchange (SSE),

and the Shenzhen Stock Exchange (SZSE). Daily U.S. stock data are sourced from the Center for

Research in Security Prices1 (CRSP), while daily Chinese stock data are sourced from the Wind

Database2 . The data span the period from 2014 through 2021. This selection of data enables us to

investigate the transferability of signals across the world’s largest and most liquid equity markets

operating under non-overlapping trading sessions.

    In this paper, we rely on the market excess return of a stock, defined as the difference between

the raw return of its price and the return of an exchange-traded fund (ETF) representing overall

stock market performance. We use both pvCLCL returns and OPCL returns in one market to

forecast OPCL returns in the other market (see Section 4.2 for a more detailed justification of this

setting). The pvCLCL logarithmic raw return for stock i on day t can be calculated by:

                                                           (t)
                                        (t)               pi,cl
                                       Ri,pvCLCL = log    (t−1)
                                                                  ,                                 (1)
                                                         pi,cl

    1
        https://www.crsp.org/
    2
        https://www.wind.com.cn/


                                                   8

===== PAGE 9 =====

while the OPCL logarithmic raw return for stock i on day t can be calculated by:

                                                                (t)
                                                  (t)          pi,cl
                                                 Ri,OPCL = log (t) .                                             (2)
                                                              pi,op

        (t)       (t)
Here pi,cl and pi,op denote the closing and opening price of stock i on day t respectively. Then the

market excess return of stock i on day t can be defined as:


                                         (t)       (t)          (t)
                                       ri = Ri,pvCLCL − RETF,pvCLCL                                              (3)


for pvCLCL returns, or
                                           (t)       (t)        (t)
                                         ri = Ri,OPCL − RETF,OPCL                                                (4)

for OPCL returns. We use SPY as the market ETF in the U.S. and 513500.SH in China.

    We select 500 stocks with the highest average market capitalizations over the years covered in

the dataset from each country.3 Unless otherwise specified, all returns mentioned in the following

contents refer to market excess returns.

    To mitigate the influence of extreme values and potential outliers, we apply winsorization to the

training-sample returns of each stock, replacing observations below the 0.5th percentile with the

0.5th percentile value and those above the 99.5th percentile with the 99.5th percentile value.



4       Methodology

This study aims to predict individual stock returns using a cross-market directed bipartite graph.

The prediction framework consists of two main stages. First, we build a directed bipartite graph

using return data from two markets within a look-back training window. This graph identifies

cross-market predictive links: if a directed edge connects two stocks, the stock at the source of the

edge is treated as a predictor for forecasting the returns of the stock at the destination. In the

    3
     This universe selection relies on full-sample information (average market capitalization over 2014–2021) and
therefore introduces a mechanical look-ahead component. We adopt it as a pragmatic way to focus on continuously
traded, highly liquid stocks and reduce missing observations. However, we caution that a fully investable design
would require time-t reconstitution based solely on lagged market capitalization information. Importantly, our main
qualitative finding is directional asymmetry (the influence of the U.S. market on the Chinese market being stronger
than the reverse effect), which is unlikely to be driven solely by this selection procedure. Nonetheless, we consider
time-local universe formation as a valuable extension.


                                                           9

===== PAGE 10 =====

second stage, we apply various machine learning methods to forecast returns based on the identified

relationships.


4.1       Directed Bipartite Graph

A graph can be defined as G = (V, E), where V represents the vertex set and E represents the edge

set. G is called bipartite if V can be divided into two disjoint sets X and Y such that all edges have

one endpoint in X and another in Y. We denote a directed edge from vi to vj as eij with associated

weight wij . For a bipartite graph G, the biadjacency matrix B is defined where rows correspond to

nodes in X , columns correspond to nodes in Y, and each entry bij contains the weight wij of edge

eij .

        We represent two different markets, the source market X and target market Y, as two vertex

sets, where stocks in each market are interpreted as nodes. Edges originate from nodes in X and

point to nodes in Y. For a specific period of time w, which is the look-back training window in the

experiment, the daily return vector of the jth stock in market X is


                                         (t−l−w)       (t−l−w+1)            (t−l−1) ⊺
                                   x = [rXj        , rXj            , ..., rXj         ] ,


            (t)
where rXj is the return of the jth stock on day t. The daily return vector of the ith stock in market

Y is
                                              (t−w)     (t−w+1)           (t−1) ⊺
                                      y = [rYi        , rYi        , ..., rYi    ] .

The lag parameter l captures the temporal ordering induced by non-overlapping trading sessions,

ensuring that returns in the source market precede those in the target market. Note that in our

study the calculation with t uses the trading calendar rather than the natural calendar.

        This time-ordered screening procedure induces a directed bipartite graph, where nodes in the

source market X are connected to nodes in the target market Y whenever statistically significant

predictive links are detected within the rolling training window. Figure 1 provides a schematic

illustration of this bipartite structure.

        For each ordered pair (Xj , Yi ), we estimate a univariate linear regression of y on x within the




                                                              10

===== PAGE 11 =====

Figure 1: Schematic illustration of the directed bipartite graph linking source-market stocks to
target-market stocks based on significant predictive relationships.


look-back window. We quantify such relationship using the t-statistic from regression, defined as

                                                      β
                                       tβ =       pPw               .                                   (5)
                                                                  2
                                              se /  i=1 (xi − x̄)


                                                                                 cov(x, y)
Here, β is the slope coefficient of the simple linear regression, given by β =              and se denotes
                                                r                                  var(x)
                                                   SSE
the standard error of the regression se =                . SSE denotes the sum of squared residuals,
                                                   w−2
       Xw
SSE =       (yi − yˆi )2 , where ŷ = βx + α, and α = ȳ − β x̄. Here, yˆi is the fitted value of yi , and α
        i=1
is the intercept of the regression line.

   The use of pairwise univariate screening serves primarily as a computationally tractable sparsifi-

cation device rather than as a formal structural inference procedure. Similar marginal screening

approaches are common in high-dimensional predictive settings where the objective is feature

selection rather than causal identification (see, e.g., Fan and Lv (2008); Hastie et al. (2009)). We

recognize that testing across a large number of stock pairs raises multiple-testing considerations

and may introduce spurious edges in finite samples (cf. Harvey et al. (2015)). In principle, false

discovery rate or multiple-comparison corrections could be applied. However, our primary goal is

to construct a predictive graph that enhances out-of-sample forecasting performance rather than

to perform statistical inference on individual edges. We therefore treat the screening step as a

model-selection heuristic and assess its validity through out-of-sample forecasting performance and


                                                     11

===== PAGE 12 =====

robustness analyses.

   Figure 2 shows the return time series for an example pair of U.S. and Chinese technology stocks,

CDNS (pvCLCL returns) and 002410.XSHE (OPCL returns), smoothed with a three-day moving

average for visualization purposes. Here l = 1 and w = 250. The t-statistic from the regression

of 002410.XSHE on CDNS is high during the period shown, illustrating a statistically significant

cross-market predictive relation within the training window under the linear screening specification.




Figure 2: Example time series of U.S. pvCLCL returns for CDNS and Chinese OPCL returns for
002410.XSHE over the rolling training window. The series are shown for illustrative purposes to
highlight cross-market co-movement underlying the detected predictive link.


   In our setting, either the U.S. or the Chinese market can be treated as the source market X , with

the target market of prediction serving as market Y. After performing the regression t-test above

for all ordered stock pairs in market X and Y, we set a threshold to filter the resulting t-statistics by

magnitude. We introduce an explicit threshold parameter, denoted by τ , to facilitate later reference.

In our experiments, we set τ = 2, and select edges whenever |tβ | > τ , corresponding approximately

to conventional significance levels under standard asymptotic approximations. If the magnitude

of the t-statistics for x and y is larger than τ , we select the return of Xj on day t − l to predict

the return of Yi on day t. This selection forms a directed edge in the graph pointing from Xj to Yi .

Note that the thresholding step is used purely as a sparsification mechanism, aimed at denoising the

signal and improving computational tractability rather than constituting a formal multiple-testing

correction. A sample directed bipartite graph is shown in Figure 1, where Xj and Xk on day t − l

are selected to predict Yi on day t. This construction yields a time-lagged cross-market predictive

                                                   12

===== PAGE 13 =====

network that can be naturally interpreted as a directed bipartite graph.

   Figure 3 presents a section of the heatmap corresponding to the biadjacency matrix of the

U.S.–Chinese stock network on 21 October 2021. To illustrate the structure more clearly, we select

25 representative stocks from each sector. For sectors containing fewer than 25 stocks in the original

dataset, all available stocks are included, resulting in 254 U.S. stocks and 235 Chinese stocks in this

visualization. Each row corresponds to a Chinese stock, while each column represents a U.S. stock.

The colour intensity represents the value of the t-statistic, and black grid lines delineate sectoral

boundaries. This visualization shows that cross-market predictive connectivity is not restricted to

within-sector interactions (which would lead to a block-diagonal structure), thereby motivating a

flexible cross-market predictive framework.




Figure 3: Heatmap of the directed biadjacency matrix for a representative trading day. Rows
correspond to Chinese stocks and columns to U.S. stocks, grouped by sector. Each entry represents
the t-statistic from the rolling-window regression of Chinese returns on lagged U.S. returns. Colour
intensity reflects the magnitude and sign of the predictive relationship.


   To summarize cross-market structure over time, we average the daily biadjacency matrices

across the full sample period, obtaining an aggregate representation of predictive linkages. We


                                                  13

===== PAGE 14 =====

then compute, for this time-averaged matrix, the median of absolute t-statistics within each sector-

by-sector block of the corresponding heatmap (Figure 4). This aggregation highlights systematic

sectoral dependencies rather than stock-specific effects. For example, the financial services sector in

the Chinese market exhibits strong predictive links with the utilities sector in the U.S. market.




Figure 4: Sector-level heatmap of the absolute median t-statistic in the time-averaged biadjacency
matrix of the directed cross-market graph. Rows correspond to Chinese sectors and columns to U.S.
sectors. Each entry reports the median absolute predictive strength across all stock pairs within the
corresponding sector-by-sector block.


   We also examine the cross-market relations over time. Figure 5 shows how the in-degree of all

nodes in set Y evolves over time. For each day, the 25th, 50th, and 75th percentiles of the in-degree

distribution are computed across all target nodes. The blue curves represent the number of U.S.

pvCLCL nodes selected to predict Chinese OPCL returns, while the red curves correspond to the

number of Chinese pvCLCL nodes selected to predict U.S. OPCL returns. As time progresses, the

in-degree in both directions increases, suggesting strengthening cross-market predictive connectivity

over the sample period.


4.2   Predictive Analysis with Machine Learning

In order to predict the return of stock Yi on day t, we use training data from day t − w to day

t − 1 for market Y and from day t − l − w to day t − l − 1 for market X . Since we wish to predict


                                                  14

===== PAGE 15 =====

Figure 5: The figure shows the 25th, 50th, and 75th percentiles of the in-degree distribution of
target nodes by day. US-CN represents the number of U.S. pvCLCL nodes selected to predict
Chinese OPCL returns, while CN-US represents the number of Chinese pvCLCL nodes selected to
predict U.S. OPCL returns.

 (t)
rYi by using information from market X , we select n stocks, i.e., X1 , X2 , ..., Xn from market X ,

corresponding to those stocks that exhibit the strongest cross-market predictive associations with Yi
                                                                                  (t−l)   (t−l)   (t−l)
according to the t-statistic defined above. Their daily returns on day t − l are rX1 , rX2 , ..., rXn .

The data used for training and prediction are illustrated in Figure 6. All predictor selection is

performed within the rolling training window to avoid look-ahead bias.

       The U.S. market is open from 9:30am to 4:00pm U.S. Eastern Time (ET), while the Chinese

market is open from 9:30am to 11:30am, and 1:00pm to 3:00pm China Standard Time (UTC+8).

There is no overlap between the two trading periods, as shown in the time zone diagram in Figure 7,

under the standard time difference. Note that adjusting for daylight saving time does not result in

any overlap between the trading sessions. We predict OPCL returns for both countries. We set

l = 1 when predicting Chinese stocks using the latest information from the U.S. market, and l = 0

in the reverse direction. This timing structure ensures that predictor information from the source

market is fully observable prior to the opening of the target market.

       We build the forecasting model as follows:


                                 (t)       (t−l)    (t−l)   (t−l)      (t)
                                rYi = Fi (rX1 , rX2 , ..., rXn ; θ) + ϵi .                          (6)


                                                      15

===== PAGE 16 =====

Figure 6: Schematic illustration of the rolling training and prediction framework. For each target
stock Yi , returns over the look-back window [t − w, t − 1] are regressed on lagged source-market
                                                                                               (t)
returns over [t − l − w, t − l − 1]. The bottom row represents the out-of-sample prediction of rYi using
source returns observed at t − l, thereby preserving temporal ordering and eliminating look-ahead
bias.




Figure 7: Timeline of opening and closing times for the U.S. and Chinese stock markets. The
non-overlapping trading sessions induce a natural temporal ordering of information, with U.S. day
t − 1 close preceding Chinese day t trading, and Chinese day t close preceding U.S. day t trading.



                                                  16

===== PAGE 17 =====

Here, the function Fi represents the different machine learning methods we use, and θ refers to the

parameters that are estimated for each machine learning model. The aim is to identify a model that
                                                             (t)
can generate accurate out-of-sample predictions of rYi so that a high SR can be achieved.

   We applied a total of ten machine learning models to forecast returns. They include: Ordinary

Least Squares (OLS), Least Absolute Shrinkage and Selection Operator (LASSO), Ridge Regression

(RIDGE), Support Vector Machine (SVM), Extreme Gradient Boosting (XGBoost), Light Gradient

Boosting Machine (LGBM), Random Forests (RF), Adaptive Boosting (AdaBoost), ensemble by

results average (ensemble-avg) and ensemble by results median (ensemble-med). This range of

models spans linear, regularized, kernel-based, tree-based, and ensemble approaches, allowing us to

assess whether cross-market predictive gains depend on model class or are robust across specifications.

We describe each model in detail below. All models are estimated within each rolling training

window and evaluated out-of-sample to ensure temporal validity.

   • Ordinary Least Squares (OLS): The main idea of OLS is to estimate regression coefficients

     by choosing parameter values that minimize the sum of squared residuals between observed

     and predicted values. Specifically, the model is defined as:

                                                       n
                                          (t)                      (t−l)      (t)
                                                       X
                                         rYi = αi +          βij rXj       + ϵi .                           (7)
                                                       j=1


     The linear model is fit with an objective of minimizing the residual sum of squares (RSS):


                                               min ∥y − αi 1 − Xw∥22 .                                      (8)
                                               αi ,w


                                                                   (t)
     y ∈ Rd is the vector of returns corresponding to rYi , X ∈ Rd×n is the matrix of predictors
                           (t−l)       (t−l)
     where each row is [rX1 , . . . , rXn ], and w = [βi1 , . . . , βin ]⊤ is the associated coefficient vector.

     Here d = w, which is the length of training window, i.e., the number of time points.

   • Least Absolute Shrinkage and Selection Operator (LASSO): The OLS method often

     leads to low bias but high variance (Hastie et al., 2009). Shrinkage methods are introduced to

     mitigate this problem, and LASSO is one of them. It uses ℓ1 -norm regularization to impose a

     penalty on the size of regression coefficients (Hastie et al., 2009). The objective function is

     given by:

                                                       17

===== PAGE 18 =====

                                                                     
                                           1
                             min             ∥y − αi 1 − Xw∥22 + λ∥w∥1 .                                (9)
                             αi ,w        2d

  Here λ is the regularization parameter.

• Ridge Regression (RIDGE): RIDGE is another type of shrinkage method. It adds ℓ2 -norm

  regularization to the linear least squares loss function. The objective function is given by:

                                                               
                                  min ∥y − αi 1 − Xw∥22 + λ∥w∥22 .                                     (10)
                                  αi ,w



• Support Vector Machine (SVM): SVMs can tackle complex learning problems while

  retaining the analytical simplicity of linear models. With kernel functions, this method avoids

  direct computation in high-dimensional spaces, enabling nonlinear learning using a linear

  algorithm in the feature space (Hearst et al., 1998). We use the radial basis function kernel

  throughout our experiment. The goal is to minimize the following dual optimization problem

  with respect to the Lagrange multipliers:

                                          n   n                                   n
                                 1 XX                           X
                             min      αj αk yj yk K(xj , xk ) −   αj
                              α 2
                                      j=1 k=1                                     j=1
                                     n
                                                                                                       (11)
                                     X
                           s.t.            αj yj = 0
                                     j=1

                                    0 ≤ αj ≤ C,            j = 1, 2, . . . , n.


  Here αj is the Lagrange multiplier, C is a hyperparameter that controls the trade-off between

  the flatness of the function and the amount by which deviations larger than ϵ are tolerated,
                                                   (t−w+j−1)
  K(xj , xk ) is the kernel function, yj is rYi                       in the training window, and xj is its
                                              (t−w+j−1−l)                (t−w+j−1−l) ⊺
  corresponding vector of predictors [rX1                      , . . . , rXn            ] .

• Extreme Gradient Boosting (XGBoost): XGBoost is a scalable end-to-end tree boosting

  method (Chen and Guestrin, 2016). It implements parallel and distributed computing to

  accelerate training. The model is defined by the following equation:

                                                   X
                                  ŷj = ϕ(xj ) =             fk (xj ),     fk ∈ F,                     (12)
                                                       k



                                                   18

===== PAGE 19 =====

  where F is the space of regression trees, and fk is one independent tree. The objective function

  is given by:
                                          X                    X
                                    min       l(ŷj , yj ) +       Ω(fk ),                     (13)
                                          j                    k

  where
                                                  1
                                      Ω(f ) = γM + λ∥w∥2 .                                     (14)
                                                  2

  Here l is a differentiable convex loss function, Ω(f ) is the regularization term, M is the number

  of leaves, w is the leaf weight, and γ and λ are the corresponding regularization parameters.

• Light Gradient Boosting Machine (LGBM): LGBM is another gradient boosting method

  that improves computational efficiency compared with standard gradient boosting tree al-

  gorithms (Ke et al., 2017). Two key techniques employed by LGBM are Gradient-Based

  One-Side Sampling and Exclusive Feature Bundling. The former retains instances with large

  gradients and randomly samples those with small gradients. The latter combines mutually

  exclusive sparse features, which never take nonzero values at the same time, into a single

  combined feature, effectively reducing computational complexity (Ke et al., 2017).

• Random Forests (RF): Random forests consist of an ensemble of decision trees. At each

  node of each tree, the algorithm randomly selects a subset of features to consider for splitting.

  Each tree is grown using bootstrap sampling of the data (Breiman, 2001). By combining these

  de-correlated trees, the final prediction is obtained by averaging their outputs (Hastie et al.,

  2009).

• Adaptive Boosting (AdaBoost): AdaBoost combines multiple weak learners to form a

  strong learner. Each weaker learner is trained to correct the errors made by the previous

  learners. The algorithm iteratively reweights training observations based on their absolute

  prediction errors, so that more emphasis is given to instances with larger errors from earlier

  learners. The final prediction is obtained by aggregating the weak learners, summing their

  probabilistic predictions (Freund and Schapire, 1997). We choose a decision tree regressor as

  the base learner in our experiment.

• Ensemble by results average (ensemble-avg): For each stock and each day, we take the


                                                 19

===== PAGE 20 =====

      average of the prediction results from the eight methods above as the final output.

    • Ensemble by results median (ensemble-med): Similar to ensemble-avg, we take the

      median of the prediction results from the eight methods as the final output for each stock on

      each day.



5     Experiments

In this section, we conduct an extensive set of experiments to evaluate the cross-market predictability

of individual stock returns and examine the economic relevance of the proposed graph-based

framework. All results are obtained using a rolling-window estimation scheme and evaluated strictly

out-of-sample.


5.1   Evaluation Metrics

We use Profit and Loss (PnL) and Sharpe Ratio (SR) to evaluate the performance of forecasting

methods. We abstract from liquidity-optimized portfolio construction and explicit transaction cost

modeling, and therefore interpret reported SRs as pre-cost measures of predictive strength rather

than implementable performance.


    • Profit and Loss (PnL): The PnL on day t is calculated with the following equation:


                                                                (t)   (t)   (t)
                                                  X
                                      P nL(t) =        sign(si ) · ri · bi .                                 (15)
                                                  i


            (t)                                                                   (t)
      Here si denotes the predicted return of stock i on day t, and ri                  denotes the actual return
                             (t)                      (21)
      of stock i on day t. bi = min(0.001 × mdvi             , L) is the amount of capital deployed on stock
                   (21)
      i, where mdvi       denotes the median daily traded volume of stock i over the 21-day interval

      preceding day t, and L is the maximum limit to the bid. The parameter L controls the

      maximum position size. This position-sizing rule serves as a coarse liquidity proxy, limiting

      exposure in less actively traded names. Throughout our experiment, L is set to 100,000 USD

      for the U.S. market prediction and 1,500,000 CNY for the Chinese market prediction.

    • Sharpe Ratio (SR): After computing daily PnLs of all stocks, we calculate the mean and


                                                      20

===== PAGE 21 =====

                                                                                (T )       (T )
        standard deviation of the daily PnL vector with length T , denoted as µP nL and σP nL , where

        T is the length of predicting period in our experiment. The annualized SR is given by:

                                                  (T )
                                                 µP nL √
                                             SR = (T ) · 252.                                     (16)
                                                 σP nL

        Here the scaling accounts for the fact that there are 252 trading days in a calendar year and

        annualizes daily PnL variability.


   Several practical limitations should be noted. First, the graph is obtained via large-scale pairwise

screening and therefore may include spurious edges in the presence of multiple testing. Second, our

economic evaluation abstracts from transaction costs, market impact, short-sale constraints, and

other trading frictions, so reported SRs reflect pre-cost predictive performance. Third, we do not

implement liquidity-weighted portfolio construction or dynamic capacity controls; position sizes

are capped but not optimized with respect to market depth. Consequently, the trading design is

stylized rather than fully implementable. As emphasized by Cartea et al. (2025), ignoring stock-level

capacity constraints can substantially overstate the implementable value of predictive strategies.

Our objective is to isolate and quantify directional cross-market predictive asymmetries rather than

to construct a production-ready trading strategy.


5.2     Experimental Setup

We use a 250-day training window and update both the graphs and the predictive models every 10

days. Prediction begins on the first trading day of 2016 and ends on the last trading day of 2021.

All models are re-estimated using a rolling-window scheme to ensure strict out-of-sample evaluation

and avoid look-ahead bias.


5.2.1     Graph-Based Cross-Market Prediction.

   • Predicting the Chinese Market with the U.S. market: We let market X denote the

        U.S. market, and market Y denote the Chinese market. We use the most recent available U.S.

        returns as predictors to forecast Chinese returns, i.e., l = 1, reflecting the non-overlapping

        trading sessions and the temporal ordering of information flow.



                                                  21

===== PAGE 22 =====

   • Predicting the U.S. Market with the Chinese market: We let market X denote the

        Chinese market, and market Y denote the U.S. market. We also use the most recent available

        returns for forecasting, i.e., l = 0, since Chinese trading concludes before the U.S. market

        opens on the same calendar day.


5.2.2     Baseline.

   • Non-Graph-Based Same-Market Baseline: For each target stock, the previous 25 days of

        daily return data are used as predictive features. The training window remains 250 days and

        models are updated every 10 days to ensure comparability with the graph-based specifications.

        This baseline model can be described with the following equation:


                                   (t)          (t−25)      (t−24)             (t−1)          (t)
                                  rYi = Fi (rYi          , rYi       , ..., rYi        ; θ) + ϵi .                (17)


                                           (t−25)        (t−24)            (t−1)
        Note that the predictive features rYi       , rYi         , ..., rYi       can be either all pvCLCL returns or
                                   (t)
        all OPCL returns, while rYi is an OPCL return.

   • Graph-Based Same-Market Baseline: Based on the methodology described in Section 4.1,

        this baseline sets markets X and Y identical, so that for each stock its predictors are drawn

        from the same market. The return values of predictors are one-day ahead of the response

        values, i.e., l = 1. This specification isolates the incremental contribution of cross-market

        information relative to graph-based modeling per se.


5.3     Main Results

We begin by evaluating the economic performance of the cross-market forecasting framework.

Portfolio sorts based on model-implied signals are standard in the return predictability literature.
                                                                                                      (t)
For each day t, stocks are ranked by the absolute value of their predicted returns, |r̂i |. To examine

how performance varies with signal strength, we construct six nested quantile portfolios:

   • quantile 1 (qr1): all stocks;

                                                                     (t)
   • quantile 2 (qr2): top 80% of stocks ranked by |r̂i |;

   • quantile 3 (qr3): top 60%;

                                                          22

===== PAGE 23 =====

   • quantile 4 (qr4): top 40%;

   • quantile 5 (qr5): top 20%;

   • quantile 6 (qr6): top 10%.

These portfolios are nested, so that qr6 ⊂ qr5 ⊂ qr4 ⊂ qr3 ⊂ qr2 ⊂ qr1. This construction allows

us to assess whether stronger model signals translate into improved risk-adjusted performance.

Importantly, the ranking at day t is based solely on model predictions available at that date

and does not use realized returns, thereby avoiding look-ahead bias in portfolio formation. We

first document that cross-market information and graph-based modeling contribute to improved

forecasting performance.




      (a) Predictors: U.S. pvCLCL returns.               (b) Predictors: U.S. OPCL returns.

Figure 8: Sharpe Ratios for forecasting Chinese OPCL returns using U.S. pvCLCL and OPCL
returns as predictors.


   Figure 8 and Figure 9 display the results of forecasting in two different directions. According

to Figure 8, when predicting Chinese stocks with U.S. stocks, RIDGE, LGBM, ensemble-avg and

ensemble-med yield strong performance. SVM appears less effective for this task, since its SRs are

mostly lower than one. For other forecasting methods and most quantiles, SRs exceed one, with

some approaching two. Notably, the ensemble-average and ensemble-median methods maintain

robust and stable performance, often comparable to the best individual models, highlighting the

benefit of model diversification. Using U.S. pvCLCL returns as features performs better than using

the U.S. OPCL returns to predict Chinese OPCL returns. The cumulative PnL plots of each method

for the former are shown in Figure 10, where the upward-sloping trajectories indicate economically

                                               23

===== PAGE 24 =====

meaningful profitability.

   In contrast, as shown in Figure 9, when predicting the U.S. stocks with Chinese stocks, SRs

are substantially lower across methods and quantiles. Therefore the Chinese market exerts weaker

predictive influence than the U.S. market in cross-market return prediction. Since the performance

is stronger when predicting Chinese stocks using U.S. pvCLCL returns, we focus on this setting in

subsequent experiments and analyses.




       (a) Predictors: Chinese pvCLCL returns.          (b) Predictors: Chinese OPCL returns.

Figure 9: Sharpe Ratios for forecasting U.S. OPCL returns using Chinese returns as predictors.


   Figure 11 shows the results of predicting Chinese stocks with Chinese stocks based on graph

structures. Figure 12 summarizes SRs across specifications, comparing graph-based cross-market

approaches, graph-based single-market approaches, and the non-graph-based baseline, with pvCLCL

returns used as predictors. Figure 13 reports the corresponding performance differentials (deltas),

computed as SRs of graph-based approaches minus those of the non-graph-based baseline. The

results indicate that graph-based same-market approaches outperform non-graph-based same-market

approaches for most machine learning models under most quantiles, especially for OLS, LGBM, and

qr5.

   Turning to the incremental value of cross-market information, combining cross-market information

with graph information yields the strongest overall performance, outperforming approaches that

use graph structures with same-market information only, as well as the non-graph-based baseline

relying solely on same-market information.




                                                 24

===== PAGE 25 =====

Figure 10: Cumulative daily Profit and Loss (PnL) from forecasting Chinese OPCL returns using
U.S. pvCLCL returns as predictors. Each panel corresponds to a different machine learning model,
and coloured curves represent nested quantile portfolios ranked by the absolute value of predicted
returns.
                                               25

===== PAGE 26 =====

    (a) Predictors: Chinese pvCLCL returns.             (b) Predictors: Chinese OPCL returns.

Figure 11: Sharpe Ratios for forecasting Chinese OPCL returns using Chinese returns as predictors.




Figure 12: Comparison of Sharpe Ratios across graph-based cross-market, graph-based same-
market, and non-graph-based baseline specifications, using pvCLCL returns as predictors. CN-CN
denotes using Chinese stocks to forecast Chinese stocks, while US-CN denotes using U.S. stocks to
forecast Chinese stocks.




                                               26

===== PAGE 27 =====

Figure 13: Performance differentials (Sharpe Ratio deltas) relative to the non-graph-based baseline,
using pvCLCL returns as predictors. US-CN denotes using U.S. stocks to forecast Chinese stocks,
while CN-CN denotes using Chinese stocks to forecast Chinese stocks.


5.4   Sensitivity Analysis

We next evaluate the robustness of predictive performance to perturbations in graph structure and

temporal alignment when forecasting Chinese returns using U.S. pvCLCL returns. We first conduct

a feature-replacement test, where selected informative stocks are randomly substituted with other

stocks. Additionally, we assess temporal sensitivity by varying the recency of input data, using

features from earlier days (e.g., t − 2, t − 3, etc.) instead of the most recent day t − 1.

   First, we conduct a feature-replacement experiment. Based on graphs built for predicting returns

on day t in the Chinese market using returns on day t − 1 in the U.S. market, we maintain the same

in-degree of each target node to preserve graph sparsity while randomly changing some of their

connections. Only previously unconnected nodes are considered as replacements for the original

connections. We randomly replace 20%, 40%, 60%, 80% and all of the edges. For each quantile

level, we obtain the median of the results from all the 10 methods.

   As shown in Figure 14a, SRs generally decline as a larger fraction of edges is replaced, indicating

that predictive gains depend critically on the economically meaningful structure captured by the

graph rather than on generic diversification effects. The deterioration is strongest in lower and

intermediate quantiles, whereas the highest quantile (qr6) exhibits comparatively greater resilience.

                                                  27

===== PAGE 28 =====

    Second, we assess temporal sensitivity by varying the recency of input data. Still based on

graphs built for predicting returns on day t in the Chinese market using returns on day t − 1 in

the U.S. market, we look into forecasting performance as the temporal gap increases (e.g., two-day,

three-day, or longer gaps) between the predictor window and the target return window. As defined
                                    (t)                               (t−l)   (t−l)    (t−l)
in Section 4.2, when we forecast rYi , the predictors are given by [rX1 , rX2 , ..., rXn ]. Here we set

l = 2, 3, ... when predicting Chinese stocks. For each quantile level, we also obtain the median of

the results from all the 10 methods.

    Figure 14b shows that SRs generally decline as l increases, consistent with the hypothesis that

cross-market predictive content decays with time. The decline is again less pronounced for qr6,

suggesting that large-magnitude signals may capture more persistent cross-market effects. A mild

stabilization beyond Lag 4 likely reflects weekly trading-cycle effects.

    Taken together, these experiments confirm that predictive performance depends critically on

both the structural accuracy of the graph and the recency of cross-market information.




(a) Effect of graph randomization (fraction of edges        (b) Effect of increasing temporal lag l.
replaced).

Figure 14: Median forecasting performance under graph randomization (a) and increasing temporal
lag (b). Panel (a) reports Sharpe Ratios as a function of the fraction of replaced edges while preserving
in-degree. Panel (b) reports Sharpe Ratios as the lag parameter l increases, measuring the effect of
input recency.




6    Conclusion and Future Research

This paper investigates cross-market return forecasting at the individual stock level. We develop a

graph-based architecture that enables structured information transmission across markets and use


                                                       28

===== PAGE 29 =====

it to construct cross-market predictive features. Building on this framework, we implement a range

of machine learning models to forecast OPCL returns for each stock.

   Empirically, we find that combining cross-market information with graph-based feature selection

delivers superior performance relative to both graph-based same-market approaches and non-graph-

based baselines. The predictive relationship is asymmetric: U.S. stocks are substantially more

informative for forecasting Chinese returns than the reverse. In particular, U.S. pvCLCL returns

exhibit stronger predictive power for Chinese OPCL returns than U.S. OPCL returns, highlighting

the importance of overnight information transmission. Sensitivity analyses confirm that preserving

the economically meaningful bipartite graph structure is crucial for achieving strong risk-adjusted

performance. Moreover, forecasting performance deteriorates as the temporal gap between predictor

and target returns widens, emphasizing the value of recency.

   Several directions for future research emerge. First, extending the analysis to additional regions,

including European and other Asian markets, would help assess the generalizability of cross-market

predictive linkages. Second, GNNs could be applied directly to the constructed bipartite graph

to learn nonlinear cross-market dependencies. Finally, recent advances in time-series-specialized

large language models may offer an alternative framework for modeling structured cross-market

interactions.



Conflicts of Interest

The authors declare that they have no competing interests.



References

Ahmad, W., Mishra, A. V., and Daly, K. J. (2018). Financial connectedness of brics and global

  sovereign bond markets. Emerging Markets Review, 37:1–16.

Asgharian, H., Hess, W., and Liu, L. (2013). A spatial analysis of international stock market

  linkages. Journal of Banking & Finance, 37(12):4738–4754.

Bardoscia, M., Barucca, P., Battiston, S., Caccioli, F., Cimini, G., Garlaschelli, D., Saracco, F.,



                                                 29

===== PAGE 30 =====

  Squartini, T., and Caldarelli, G. (2021). The physics of financial networks. Nature Reviews

  Physics, 3(7):490–507.

Baur, D. and Jung, R. C. (2006). Return and volatility linkages between the us and the german

  stock market. Journal of International Money and Finance, 25(4):598–613.

Breiman, L. (2001). Random forests. Machine learning, 45(1):5–32.

Cakra, Y. E. and Trisedya, B. D. (2015). Stock price prediction using linear regression based

  on sentiment analysis. In 2015 international conference on advanced computer science and

  information systems (ICACSIS), pages 147–154. IEEE.

Capponi, A., Sidaoui, J. A., and Zou, J. (2024). Graph machine learning for asset pricing: Traversing

  the supply chain and factor zoo. Available at SSRN 5031617.

Cartea, Á., Cucuringu, M., Jin, Q., and Zhu, J. (2025). Liquidity constraints and the illusion of

  anomaly profitability. Available at SSRN 5797502.

Chen, K., Zhou, Y., and Dai, F. (2015). A lstm-based method for stock returns prediction: A case

  study of china stock market. In 2015 IEEE international conference on big data (big data), pages

  2823–2824. IEEE.

Chen, L. and Fan, X. (2025). Financial risk forecasting with rgct-prerisk: a relational graph and

  cross-temporal contrastive pretraining framework. Journal of King Saud University Computer

  and Information Sciences, 37(6):143.

Chen, S., Green, T. C., Gulen, H., and Zhou, D. (2024). What does chatgpt make of historical

  stock returns? extrapolation and miscalibration in llm stock return forecasts. arXiv preprint

  arXiv:2409.11540.

Chen, T. and Guestrin, C. (2016). Xgboost: A scalable tree boosting system. In Proceedings of

  the 22nd acm sigkdd international conference on knowledge discovery and data mining, pages

  785–794.

Chen, Y., Wei, Z., and Huang, X. (2018). Incorporating corporation relationship via graph



                                                 30

===== PAGE 31 =====

  convolutional neural networks for stock price prediction. In Proceedings of the 27th ACM

  international conference on information and knowledge management, pages 1655–1658.

Chen, Z., Zheng, L. N., Lu, C., Yuan, J., and Zhu, D. (2023). Chatgpt informed graph neural

  network for stock movement prediction. arXiv preprint arXiv:2306.03763.

Cheng, D., Yang, F., Xiang, S., and Liu, J. (2022). Financial time series forecasting with multi-

  modality graph neural network. Pattern Recognition, 121:108218.

Cheng, R. and Li, Q. (2021). Modeling the momentum spillover effect for stock prediction via

  attribute-driven graph attention networks. In Proceedings of the AAAI conference on artificial

  intelligence, volume 35, pages 55–62.

Clements, A. E., Hurn, A. S., and Volkov, V. V. (2015). Volatility transmission in global financial

  markets. Journal of Empirical Finance, 32:3–18.

Ding, Y., Jia, S., Ma, T., Mao, B., Zhou, X., Li, L., and Han, D. (2023). Integrating stock features

  and global information via large language models for enhanced stock return prediction. arXiv

  preprint arXiv:2310.05627.

Eun, C. S. and Shim, S. (1989). International transmission of stock market movements. Journal of

  financial and quantitative Analysis, 24(2):241–256.

Fan, J. and Lv, J. (2008). Sure independence screening for ultrahigh dimensional feature space.

  Journal of the Royal Statistical Society: Series B (Statistical Methodology), 70(5):849–911.

Freund, Y. and Schapire, R. E. (1997). A decision-theoretic generalization of on-line learning and

  an application to boosting. Journal of computer and system sciences, 55(1):119–139.

Gao, H., Kou, G., Liang, H., Zhang, H., Chao, X., Li, C.-C., and Dong, Y. (2024). Machine learning

  in business and finance: a literature review and research opportunities. Financial Innovation,

  10(1):86.

Gong, J., Wang, G.-J., Zhou, Y., and Xie, C. (2025). Cross-market volatility forecasting with

  attention-based spatial-temporal graph convolutional networks. Journal of Empirical Finance,

  page 101639.

                                                31

===== PAGE 32 =====

Guillaume, J.-L. and Latapy, M. (2006). Bipartite graphs as models of complex networks. Physica

  A: Statistical Mechanics and its Applications, 371(2):795–813.

Harvey, C. R., Liu, Y., and Zhu, H. (2015). . . . and the cross-section of expected returns. The

  Review of Financial Studies, 29(1):5–68.

Hastie, T., Tibshirani, R., Friedman, J. H., and Friedman, J. H. (2009). The elements of statistical

  learning: data mining, inference, and prediction, volume 2. Springer.

Hearst, M. A., Dumais, S. T., Osuna, E., Platt, J., and Scholkopf, B. (1998). Support vector

  machines. IEEE Intelligent Systems and their applications, 13(4):18–28.

Huang, W., Nakamori, Y., and Wang, S.-Y. (2005). Forecasting stock market movement direction

  with support vector machine. Computers & operations research, 32(10):2513–2522.

Huang, W.-Q. and Liu, P. (2023). Cross-market risk spillovers among sovereign cds, stock, foreign

  exchange and commodity markets: An interacting network perspective. International Review of

  Financial Analysis, 90:102875.

Jung, J., Lee, K., and Leung, T. (2024). Threshold overnight comovement analysis of intraday and

  overnight returns. Available at SSRN 4946188.

Ke, G., Meng, Q., Finley, T., Wang, T., Chen, W., Ma, W., Ye, Q., and Liu, T.-Y. (2017). Lightgbm:

  A highly efficient gradient boosting decision tree. Advances in neural information processing

  systems, 30.

Kelly, B., Xiu, D., et al. (2023). Financial machine learning. Foundations and Trends® in Finance,

  13(3-4):205–363.

Kley, O., Klüppelberg, C., and Paterlini, S. (2020). Modelling extremal dependence for operational

  risk by a bipartite graph. Journal of Banking & Finance, 117:105855.

Kumar, M. and Thenmozhi, M. (2006). Forecasting stock index movement: A comparison of support

  vector machines and random forest. In Indian institute of capital markets 9th capital markets

  conference paper.



                                                32

===== PAGE 33 =====

Kumar, P. N., Umeorah, N., and Alochukwu, A. (2024). Dynamic graph neural networks for

  enhanced volatility prediction in financial markets. arXiv preprint arXiv:2410.16858.

Lee, S. I. and Yoo, S. J. (2020). Multimodal deep learning for finance: integrating and forecasting

  international stock markets. The Journal of Supercomputing, 76(10):8294–8312.

Lee, T. K., Choi, I., and Kim, W. C. (2025). Symmetry-aware graph neural approaches for

  data-efficient return prediction in international financial market indices. Symmetry, 17(9):1372.

Li, W., Bao, R., Harimoto, K., Chen, D., Xu, J., and Su, Q. (2021). Modeling the stock relation

  with graph network for overnight stock movement prediction. In Proceedings of the twenty-

  ninth international conference on international joint conferences on artificial intelligence, pages

  4541–4547.

Lin, S., Chen, Y., Qi, Y., Ma, C., Cao, B., Zhang, Y., Liu, X., and Guo, J. (2025). Cspo: Cross-

  market synergistic stock price movement forecasting with pseudo-volatility optimization. In

  Companion Proceedings of the ACM on Web Conference 2025, pages 354–363.

Liu, Q. and An, Y. (2011). Information transmission in informationally linked markets: Evidence

  from us and chinese commodity futures markets. Journal of International Money and Finance,

  30(5):778–795.

Liu, R., Liu, H., Huang, H., Song, B., and Wu, Q. (2024). Multimodal multiscale dynamic graph

  convolution networks for stock price prediction. Pattern Recognition, 149:110211.

Luo, C., He, H., Cucuringu, M., and Ma, T. (2025). Spatial-temporal stock movement prediction

  and portfolio selection based on the semantic company relationship graph. Quantitative Finance,

  pages 1–19.

Mohammadi, H. and Tan, Y. (2015). Return and volatility spillovers across equity markets in

  mainland china, hong kong and the united states. Econometrics, 3(2):215–232.

Newman, M. (2018). Networks. Oxford university press.

Nie, Y., Kong, Y., Dong, X., Mulvey, J. M., Poor, H. V., Wen, Q., and Zohren, S. (2024). A survey



                                                 33

===== PAGE 34 =====

  of large language models for financial applications: Progress, prospects and challenges. arXiv

  preprint arXiv:2406.11903.

Rapach, D. E., Strauss, J. K., and Zhou, G. (2013). International stock return predictability: what

  is the role of the united states? The Journal of Finance, 68(4):1633–1662.

Rundo, F., Trenta, F., Di Stallo, A. L., and Battiato, S. (2019). Machine learning for quantitative

  finance applications: A survey. Applied Sciences, 9(24):5574.

Sarwar, G. (2014). Us stock market uncertainty and cross-market european stock returns. Journal

  of Multinational Financial Management, 28:1–14.

Siliverstovs, B. (2017). International stock return predictability: on the role of the united states in

  bad and good times. Applied Economics Letters, 24(11):771–773.

Thenmozhi, M. and Sarath Chand, G. (2016). Forecasting stock returns based on information

  transmission across global markets using support vector machines. Neural Computing and

  Applications, 27(4):805–824.

Wang, C. (2024). Stock return prediction with multiple measures using neural network models.

  Financial Innovation, 10(1):72.

Wang, H. and Chen, S. (2020). A bipartite graph-based recommender for crowdfunding. Banking

  and finance, page 197.

Wang, J., Zhang, S., Xiao, Y., and Song, R. (2021). A review on graph neural network methods in

  financial applications. arXiv preprint arXiv:2111.15367.

Wu, Y., Lan, W., Fan, X., and Fang, K. (2024). Bipartite network influence analysis of a two-mode

  network. Journal of Econometrics, 239(2):105562.

Yang, D. and He, Q. (2026). Enhancing intraday momentum prediction: The role of volume-based

  information uncertainty in the chinese stock market. International Journal of Financial Studies,

  14(2):47.




                                                  34

===== PAGE 35 =====

Zhang, C., Pu, X., Cucuringu, M., and Dong, X. (2025). Forecasting realized volatility with

  spillover effects: Perspectives from graph neural networks. International Journal of Forecasting,

  41(1):377–397.




Appendix A             Hyperparameter Settings

The OLS method does not involve any hyperparameters. Table A.1 reports the performance of the

remaining seven machine learning models under alternative hyperparameter configurations. The

SVM model appears relatively insensitive to variations in hyperparameter values, and its SRs remain

generally below one across specifications, suggesting limited suitability for this particular forecasting

setting. For the other models, SRs exceed one across most quantiles and hyperparameter choices,

indicating that the cross-market forecasting framework delivers robust risk-adjusted performance

and is not overly sensitive to specific tuning parameters.



Appendix B            Comparison with Baselines when Predicting with

                      OPCL Returns

Similar to Figure 12 and Figure 13, Figure B.1 and Figure B.2 report the performance comparison

among the graph-based cross-market approach, the graph-based same-market baseline, and the

non-graph-based baseline when OPCL returns are used as predictors.

   The results indicate that incorporating graph structure generally improves forecasting perfor-

mance across most quantiles and machine learning models. However, in contrast to the pvCLCL

setting, the incremental contribution of cross-market information is substantially weaker when

OPCL returns are used as predictors.



Appendix C            Cross-Market Spillovers under U.S. Market Shocks

To investigate whether cross-market predictability strengthens during periods of heightened U.S.

market activity and volatility, we condition the analysis on large movements in the U.S. market.

Specifically, we identify days on which the S&P 500 ETF (SPY) exhibits large absolute pvCLCL


                                                   35

===== PAGE 36 =====

     Table A.1: Summary of SR results across different hyperparameter settings (using the most recent U.S. pvCLCL returns to predict
     Chinese OPCL returns). Values are reported as mean ± standard deviation.

      Methods     Parameters                                       qr1             qr2             qr3             qr4             qr5             qr6
      LASSO       λ={1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100, 1000} 0.848 ± 0.222   0.969 ± 0.247   1.238 ± 0.31    1.65 ± 0.398    1.821 ± 0.433   1.777 ± 0.424
      RIDGE       λ={1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100, 1000} 1.238 ± 0.429   1.293 ± 0.43    1.437 ± 0.449   1.715 ± 0.51    1.668 ± 0.619   1.55 ± 0.461
      SVM         C={0.1, 1, 10, 100, 1000}                   0.743 ± 0.194    0.751 ± 0.196   0.782 ± 0.204   0.719 ± 0.188   1.02 ± 0.267    0.836 ± 0.218
                  max depth = {3,6,9}
      XGBoost     learning rate = {0.01, 0.1, 0.2}            1.445 ± 0.224    1.48 ± 0.247    1.587 ± 0.214   1.539 ± 0.309   1.381 ± 0.401   0.964 ± 0.233
                  n estimators = {50, 100, 300}
36
                  num leaves = {10, 31, 90}
      LGBM        learning rate = {0.01, 0.1, 0.2}             1.32 ± 0.348    1.457 ± 0.388   1.541 ± 0.422   1.44 ± 0.485    1.652 ± 0.466   1.424 ± 0.407
                  n estimators = {50, 100, 300}
                  n estimators = {50, 100, 300}
      RF                                                       1.481 ± 0.41    1.558 ± 0.422   1.639 ± 0.447   1.799 ± 0.486   1.747 ± 0.474   1.09 ± 0.351
                  max depth = {5, 10, 50}
                  max depth = {1, 5, 10}
      AdaBoost    n estimators = {50, 100, 300}               1.389 ± 0.358    1.405 ± 0.385   1.549 ± 0.436   1.548 ± 0.419    1.1 ± 0.305    0.667 ± 0.187
                  learning rate = {0.01, 0.1, 0.2}

     Note: max depth is the maximum depth of a tree. learning rate is the learning rate. n estimators is the maximum number of estimators
     at which boosting is terminated. num leaves is maximum tree leaves for base learners in an LGBM model.

===== PAGE 37 =====

Figure B.1: Comparison of Sharpe Ratios across graph-based cross-market, graph-based same-
market, and non-graph-based baseline specifications, using OPCL returns as predictors. US-CN
denotes using U.S. stocks to forecast Chinese stocks, while CN-CN denotes using Chinese stocks to
forecast Chinese stocks.




Figure B.2: Performance differentials (Sharpe Ratio deltas) relative to the non-graph-based
baseline, using OPCL returns as predictors. US-CN denotes using U.S. stocks to forecast Chinese
stocks, while CN-CN denotes using Chinese stocks to forecast Chinese stocks.



                                               37

===== PAGE 38 =====

returns.

   We divide the SPY absolute pvCLCL returns into nested quantiles (qr1–qr6), consistent with the

earlier quantile construction. For example, qr2 contains the top 80% of days ranked by absolute SPY

returns. For each identified SPY shock date ti , we extract the model’s OPCL return forecast for the

next trading day ti + 1 in the Chinese market. We then compute SRs restricted to these subsets

of dates. This conditional evaluation allows us to assess whether predictive performance improves

during periods of elevated U.S. market volatility, when cross-market information transmission is

likely to be stronger.

   The results are shown in Figure C.1. Nonlinear ensemble models such as XGBoost, LGBM,

RF, and AdaBoost achieve consistently high SRs across quantiles, especially in the upper ranges

(qr4–qr6), suggesting that nonlinear models capture state-dependent spillover effects more effectively.

OLS also performs well, achieving its highest SR in qr6. In contrast, LASSO and SVM exhibit

weaker performance, with SRs turning negative in some quantiles, while RIDGE shows comparatively

unstable performance.




Figure C.1: Sharpe Ratios of forecasting models conditional on SPY absolute pvCLCL return
nested quantiles, measuring predictive performance following different magnitudes of U.S. market
shocks.




Appendix D               Comparison of Sharpe Ratio Results across Sectors

We continue to focus on the setting in which U.S. pvCLCL returns are used to forecast Chinese

OPCL returns. The sector-level SR results are reported in Figure D.1. Because the number of stocks


                                                  38

===== PAGE 39 =====

Figure D.1: Sector-level Sharpe Ratios for cross-market forecasting (using U.S. pvCLCL returns
to forecast Chinese OPCL returns).


varies across sectors, these results should be interpreted with caution. Overall, the technology and

consumer defensive sectors exhibit relatively higher SRs compared with other sectors, indicating

stronger cross-market predictive effects in these segments.



Appendix E           Predicting Chinese Stocks Using Both U.S. and Chi-

                     nese Stocks

We extend the analysis by allowing the predictor set X to include all stocks from both the U.S. and

Chinese markets, while the target set Y continues to consist of Chinese stocks only. The graph

construction phase follows the procedure introduced in Section 4.1. The results are presented in

Figure E.1. In several specifications, the resulting SRs exceed those obtained when using only U.S.

returns as predictors (Figure 8), suggesting that combining domestic and cross-market information

can further enhance predictive performance.




                                                39

===== PAGE 40 =====

 (a) U.S. pvCLCL + Chinese pvCLCL returns.         (b) U.S. pvCLCL + Chinese OPCL returns.




  (c) U.S. OPCL + Chinese pvCLCL returns.           (d) U.S. OPCL + Chinese OPCL returns.


Figure E.1: Sharpe Ratios for forecasting Chinese OPCL returns when the predictor set includes
both U.S. and Chinese stocks. Panels vary the combination of pvCLCL and OPCL features across
the two markets.




                                             40

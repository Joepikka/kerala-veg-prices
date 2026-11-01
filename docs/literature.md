# Literature

What published work says about the three questions this project asks, and how the project's methods
relate to it. Results quoted here come from each paper's abstract or summary as found on 1 November 2026;
where only a secondary summary was available, that is stated.

## 1. Price volatility of tomato, onion and potato (TOP)

- **Vegetables inflation in India: a study of tomato, onion and potato** (TNAU agritech repository).
  Agmarknet data, tomato from July 2012 and onion/potato from July 2014 to June 2022; studies volatility
  and its transmission from tomato to onion and potato in retail and wholesale markets.
  https://agritech.tnau.ac.in/govt_schemes_services/pdf/tomato,%20onion%20and%20potato.pdf
- **Volatility forecasting of highly perishable vegetable prices using GARCH-augmented deep learning**
  (Journal of Revenue and Pricing Management, 2026). Argues econometric and ML models each miss part of
  the picture (non-linearity, volatility clustering, asymmetric shocks) and combines GARCH with deep learning.
  https://link.springer.com/article/10.1057/s41272-026-00625-1

## 2. How price shocks move between markets (transmission and integration)

- **Asymmetric and threshold price transmission dynamics in onion markets in India** (Cogent Economics &
  Finance, 2024). Seven major onion markets, 2011-2018, momentum threshold autoregression and threshold VECM
  with Lasalgaon as the reference market; finds threshold cointegration and asymmetric adjustment in the
  short and long run. https://www.tandfonline.com/doi/full/10.1080/23322039.2024.2402557
- **Market analysis and price dynamics in perishable crop supply chains in India** (2025, NARDL on weekly
  farm, wholesale and retail prices). Asymmetry in magnitude and speed in the wholesale-retail chain for
  onion and potato, in magnitude for tomato; the farm-wholesale link is more efficient than wholesale-retail.
  https://www.researchgate.net/publication/393991410
- **Price transmission in major tomato markets of India** (2024). Johansen cointegration across major
  tomato markets: long-run price association, but no asymmetry test. https://www.researchgate.net/publication/379688308
- **Market integration and price transmission analysis of onion in wholesale markets of India**.
  https://www.researchgate.net/publication/366507130
- **Asymmetric price transmission: a case of wheat in India** (Agriculture, 2022). Not a vegetable, but a
  clean threshold-VECM template: retail responds to deviations from the long-run equilibrium more than
  wholesale. https://www.mdpi.com/2077-0472/12/3/410

Gap this project fills: almost all of this work uses data from before 2019, looks at producing-region
markets, and stops at onion. None of it measures how shocks reach a consuming state that buys most of its
vegetables from its neighbours, as Kerala does, with 2021-2026 market data.

## 3. Forecasting prices and warning of spikes with ML

- **Predicting agricultural commodities prices with machine learning: a review** (arXiv 2310.18646, 2023).
  https://arxiv.org/pdf/2310.18646
- **Enhancing agricultural commodity price forecasting with deep learning** (Scientific Reports, 2025).
  23 Indian commodities, daily wholesale prices 2010 to mid-2024, statistical vs ML vs DL; notes SVR and
  XGBoost as strong baselines. https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12215695/
- **Deep learning approaches for potato price forecasting: LSTM, Bi-LSTM and AM-LSTM** (Potato Research,
  2025). Attention LSTM best, MAPE 8.95%. https://link.springer.com/article/10.1007/s11540-024-09823-z
- **Forecasting potato prices in Agra: linear time series vs neural network models** (Potato Research,
  2025). LSTM best, MAPE 7.99%. https://link.springer.com/article/10.1007/s11540-024-09838-6
- **Price forecasting of TOP crops with hidden Markov models and deep learning** (SSCA). Gains over plain
  LSTM are mixed. https://www.ssca.org.in/media/4_SA99102023_R2_SA_26112023_V_99yqeAF._Ramasubramanian_FINAL_Finally.pdf
- **NourishNet: proactive severity-state forecasting of food commodity prices for global warning systems**
  (arXiv 2407.00698, 2024). Closest to this project's framing: classify warning severity rather than
  forecast a level; a secondary review reports F1 of 72.18% (to be checked against the paper).
  https://arxiv.org/abs/2407.00698

Gap this project fills: most Indian TOP papers forecast a price level and report MAPE on one market.
A buyer acts on "will it spike?", so this project predicts a 14-day spike as a classification problem,
uses features from the markets that supply Kerala (arrivals, prices, weather, news), and evaluates on a
held-out later period against simple rules, reporting precision, recall and warning lead time.

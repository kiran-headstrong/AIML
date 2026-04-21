# Stock Analyser Tutorial: Implementation Details

## Overview

This notebook builds a multi-stage stock analysis pipeline around five agent-style components:

1. Data analysis
2. Sentiment analysis
3. Technical analysis
4. Risk assessment
5. Decision making

The orchestration layer is implemented with LangGraph. The workflow takes a stock ticker symbol as input, progressively enriches a shared state object, and returns a recommendation such as BUY, HOLD, or SELL.

The tutorial is organized as a single notebook, but the code is structured more like a small application with:

- configuration classes
- a typed shared state
- one class per analysis domain
- graph nodes that adapt those classes into LangGraph
- a wrapper class that executes the full workflow

## Notebook Structure

The notebook is split into the following implementation blocks:

- Cell 1: package installation command
- Cells 3-4: imports and environment setup
- Cells 5-6: shared state and configuration dataclasses
- Cells 8-9: data analysis agent
- Cells 10-14: sentiment analysis agent
- Cells 15-19: technical analysis agent
- Cells 20-24: risk assessment agent
- Cells 25-29: decision making agent
- Cells 30-34: LangGraph workflow setup and utility functions
- Remaining cells: empty placeholders

## Dependencies and External Services

The notebook uses a broad dependency set:

- Core Python: os, json, asyncio, logging, warnings, datetime, typing, dataclasses
- Data and math: pandas, numpy, scipy
- Technical analysis: ta
- Market data: yfinance, alpha_vantage, fredapi
- Sentiment/news/social: requests, newsapi-python, tweepy, praw, textblob, beautifulsoup4
- Agent orchestration: langgraph, langchain-openai, langchain-core
- Visualization: plotly, matplotlib, seaborn

### Practical note on package installation

The first install cell and the later setup cell do not match exactly.

- The first cell installs a shorter list.
- The later setup comment includes additional packages such as ta, plotly, matplotlib, seaborn, fredapi, tweepy, and praw.

For the notebook to run fully, the second, more complete package list is the accurate one.

### External APIs used

The implementation is designed to optionally use these services:

- Yahoo Finance through yfinance
- Alpha Vantage for time series and fundamentals
- FRED for macroeconomic indicators
- NewsAPI for article retrieval
- Twitter via tweepy
- Reddit via praw
- OpenAI key storage in config, although no LLM call is actually used in the notebook logic

If credentials are missing, some components degrade gracefully and return empty or neutral outputs.

## Shared State Design

The central data contract is the StockAnalysisState TypedDict.

It stores:

- input data: symbol, company_name, analysis_date
- live market metrics: current_price, change, volume, market_cap
- historical and financial data
- sentiment outputs
- technical outputs
- risk outputs
- final recommendation outputs
- execution metadata: errors, warnings, execution_time

This state is passed from one graph node to the next and updated in place.

### Important implementation detail

Several fields are written into the state later in the workflow but are not declared in the TypedDict. These include:

- market_context
- economic_data
- technical_analysis_details
- decision_details

This works at runtime because Python dictionaries are dynamic, but it weakens the benefit of the TypedDict and would likely trigger type-checking complaints in a stricter codebase.

## Configuration Classes

Three dataclasses are defined:

### APIConfig

Stores API credentials for:

- Alpha Vantage
- NewsAPI
- FRED
- Twitter
- Reddit
- OpenAI

### AnalysisConfig

Stores tunable analysis parameters such as:

- lookback_days = 252
- short_ma_period = 20
- long_ma_period = 50
- rsi_period = 14
- bollinger_period = 20
- confidence_threshold = 0.6
- risk_free_rate = 0.02

### TechnicalIndicators

Defines a container for common indicator outputs such as SMA, EMA, RSI, MACD, Bollinger Bands, ATR, and volume averages.

This dataclass is declared but not actually used downstream. The implementation instead passes indicator values around as plain dictionaries.

## DataAnalysisAgent

This class handles raw market and company data acquisition.

### Initialization

The constructor creates optional clients for:

- Alpha Vantage time series
- Alpha Vantage fundamentals
- FRED

These clients are only initialized if the required API key exists.

### fetch_stock_data

This method uses yfinance to fetch:

- ticker metadata from ticker.info
- historical OHLCV data from ticker.history

It computes:

- current price
- previous close
- absolute daily price change
- daily percentage change
- trading volume
- market capitalization

The method returns a dictionary that also includes the raw historical DataFrame and the full Yahoo info payload.

### get_historical_analysis

This method computes performance statistics over a recent trailing window:

- annualized average return
- annualized volatility
- Sharpe ratio
- maximum drawdown
- average volume
- 52-week high and low style range

Although implemented, this method is not called by the LangGraph workflow nodes.

### _calculate_max_drawdown

Calculates rolling peak values and then the minimum drawdown from those peaks.

### get_financial_data

Uses yfinance to retrieve:

- income statement
- balance sheet
- cash flow statement
- ratio-like values from ticker.info
- analyst price target values

The method converts pandas tables into dictionaries when available.

### get_market_context

Pulls recent data for major indices:

- S&P 500
- Dow Jones
- NASDAQ
- VIX

It computes one-day percent moves and also extracts sector and industry from the target company.

### get_economic_indicators

Uses FRED, if configured, to fetch the latest value for:

- GDP
- unemployment rate
- CPI
- federal funds rate
- 10-year Treasury rate

## SentimentAnalysisAgent

This class aggregates sentiment from news, social media, and analyst opinions.

### Initialization and client setup

The constructor optionally creates:

- a NewsAPI client
- a Twitter client
- a Reddit client

The helper setup_social_media_clients method performs this conditional setup.

### analyze_news_sentiment

The method:

1. Determines the company name from yfinance.
2. Fetches articles using a helper.
3. Scores sentiment with TextBlob.
4. Weights title sentiment at 70 percent and description sentiment at 30 percent.
5. Aggregates mean sentiment and counts positive, neutral, and negative articles.

Only the first ten analyzed articles are retained in the returned payload.

### _fetch_news_articles

This helper combines two sources:

- NewsAPI search over the symbol and company name
- Yahoo Finance news as a fallback or supplement

Articles are deduplicated by title and sorted newest first.

### analyze_social_sentiment

Combines Twitter and Reddit sentiment into a single social score by averaging non-zero source scores.

It also reports:

- which sources were used
- total mention count

### _get_twitter_sentiment

Searches recent tweets matching the ticker symbol query and scores each tweet using TextBlob polarity.

### _get_reddit_sentiment

Searches several investing-related subreddits for the symbol and scores combined post title and body text.

### get_analyst_sentiment

Uses yfinance analyst data and recommendationMean.

The implementation converts Yahoo's 1 to 5 recommendation scale into an internal -1 to 1 sentiment score.

### calculate_overall_sentiment

Produces a weighted sentiment score using:

- news: 0.4
- social: 0.3
- analyst: 0.3

It also maps the numeric score to labels such as Bullish, Neutral, or Bearish.

## TechnicalAnalysisAgent

This class computes indicators, levels, patterns, and momentum.

### calculate_all_indicators

This method acts as the main aggregator. It requires a non-empty DataFrame with at least the long moving-average period of data.

It merges results from:

- moving averages
- momentum indicators
- volatility indicators
- volume indicators
- trend indicators

### Moving averages

The notebook calculates:

- SMA 20
- SMA 50
- SMA 200, if enough data exists
- EMA 12
- EMA 26
- EMA 50
- WMA 20

### Momentum indicators

The notebook calculates:

- RSI
- MACD line
- MACD signal
- MACD histogram
- stochastic %K and %D
- Williams %R
- CCI

### Volatility indicators

The notebook calculates:

- Bollinger upper, lower, and middle bands
- Bollinger width
- ATR
- Keltner channel upper and lower bands

### Volume indicators

The notebook calculates:

- OBV
- VWAP
- Chaikin Money Flow
- volume SMA
- volume ratio

### Trend indicators

The notebook calculates:

- ADX
- ADX positive and negative directional components
- Parabolic SAR down series
- Aroon up and down

### identify_support_resistance

This method uses rolling local maxima and minima over a recent window to estimate nearby support and resistance.

It also adds:

- support and resistance strength counts
- one-year Fibonacci retracement levels
- a pivot point

### analyze_trend_and_patterns

This method performs three things:

1. Multi-timeframe trend classification over 20, 50, and 200-day windows
2. Pattern detection
3. Momentum scoring

Short-term, medium-term, and long-term trend labels are converted into a weighted trend score.

### Pattern recognition helpers

The notebook contains heuristic detectors for:

- Double Top
- Double Bottom
- Head and Shoulders
- Ascending Triangle
- Descending Triangle
- Symmetrical Triangle
- Bull Flag
- Bear Flag

These are simplified statistical heuristics based on recent highs, lows, slopes, and consolidation behavior rather than full pattern-recognition models.

### _analyze_momentum

Momentum is based on weighted rates of change over 5, 10, and 20 trading days, then mapped to qualitative labels from Strong Positive to Strong Negative.

## RiskAssessmentAgent

This class converts historical price behavior and company metrics into a multi-component risk profile.

### calculate_comprehensive_risk

This is the risk aggregator. It merges results from:

- volatility risk
- market risk
- Value at Risk
- liquidity risk
- fundamental risk
- overall risk score

### _calculate_volatility_risk

Computes:

- annualized volatility
- trailing 30-day volatility
- trailing 90-day volatility
- a normalized volatility risk score
- current volatility percentile relative to rolling history

### _calculate_market_risk

Uses SPY as the market proxy and computes:

- beta
- correlation with market
- alpha
- systematic risk
- a market risk score

### _calculate_var

Implements three Value at Risk approaches:

- historical VaR
- parametric VaR under a normal assumption
- Monte Carlo VaR

It also calculates expected shortfall and maximum drawdown.

### _monte_carlo_var

Runs a normal-distribution simulation with a fixed random seed of 42 for reproducibility.

### _calculate_liquidity_risk

Approximates liquidity risk using:

- average volume
- volume volatility
- a spread proxy from high-low ranges
- market cap tiers

### _calculate_fundamental_risk

Builds a simple rule-based risk model from:

- P/E ratio
- debt-to-equity
- profit margin
- current ratio

### _calculate_overall_risk_score

Combines risk components using these weights:

- volatility: 0.3
- market: 0.2
- liquidity: 0.2
- fundamental: 0.2
- VaR: 0.1

It returns:

- overall_risk_score
- risk_category
- a component breakdown
- the weights used

### Important implementation detail

The method returns a dictionary with the key overall_risk_score whose value is itself another dictionary containing overall_risk_score and risk_category.

Because of that, the risk node later extracts the final scalar using:

state["risk_score"] = risk_metrics.get("overall_risk_score", {}).get("overall_risk_score", 0.5)

This works, but the data shape is more awkward than necessary.

## DecisionMakingAgent

This class converts all previous outputs into a final recommendation.

### make_investment_decision

The method performs the full synthesis pipeline:

1. Extract domain-specific slices from the shared state.
2. Compute four component scores.
3. Combine them into one weighted score.
4. Convert the score into a recommendation label.
5. Estimate confidence.
6. Compute price target and stop-loss values.
7. Generate a narrative rationale.

### Component score calculation

#### Sentiment score

Uses the aggregated sentiment score and adds an agreement bonus when the sentiment sources are aligned.

#### Technical score

Uses:

- trend direction
- RSI
- MACD versus MACD signal
- moving average alignment
- bullish or bearish chart patterns

#### Important implementation caveat

The moving-average part of the technical score expects current_price to exist inside technical_indicators, but the indicator dictionary does not store it.

As a result, this line defaults current_price to sma_20:

current_price = indicators.get('current_price', sma_20)

That means the moving-average scoring logic is less informative than intended unless current_price is manually added elsewhere.

#### Risk score

Transforms the overall risk value into a score where lower risk becomes more positive.

It also adjusts for:

- volatility preference
- how far beta is from 1.0

#### Fundamental score

Uses rule-based thresholds over:

- P/E ratio
- ROE
- debt-to-equity
- profit margin

### _combine_scores

Final score weights are:

- sentiment: 0.2
- technical: 0.3
- risk: 0.25
- fundamental: 0.25

### _generate_recommendation

Maps the final score to five buckets:

- STRONG BUY
- BUY
- HOLD
- SELL
- STRONG SELL

### _calculate_confidence

Confidence is based on:

- agreement between the four component scores
- absolute strength of the combined signal

The final confidence is returned on a 0 to 100 scale.

### _calculate_price_targets

Computes target and stop-loss levels from:

- current price
- recommendation strength
- nearest support and resistance
- volatility proxy from risk data

It also returns upside, downside, and risk-reward ratio.

### _generate_rationale

Builds a plain-language explanation string by combining:

- recommendation and confidence
- sentiment interpretation
- technical trend summary
- chart pattern findings
- risk profile
- basic valuation commentary

### _determine_time_horizon

Sets a suggested holding period based on recommendation strength and trend direction.

## LangGraph Workflow Implementation

The graph orchestration is built in setup_stock_analysis_workflow.

### Nodes

Five nodes are added:

- data_analysis
- sentiment_analysis
- technical_analysis
- risk_assessment
- decision_making

### Edges

The graph is wired like this:

1. data_analysis is the entry point
2. data_analysis feeds both sentiment_analysis and technical_analysis
3. sentiment_analysis feeds risk_assessment
4. technical_analysis feeds risk_assessment
5. risk_assessment feeds decision_making
6. decision_making ends the workflow

This creates a fork-join pattern where sentiment and technical analysis are intended to run after data collection and before risk assessment.

## Node Adapter Functions

Each agent class is wrapped in a node factory that returns a LangGraph-compatible function.

### create_data_analysis_node

Updates the shared state with:

- company metadata
- pricing metrics
- historical data
- financial data
- market context
- economic indicators
- execution timing

### create_sentiment_analysis_node

Updates the state with:

- news_sentiment
- social_sentiment
- analyst_consensus
- overall_sentiment
- sentiment_details
- execution timing

### create_technical_analysis_node

Updates the state with:

- technical_indicators
- support_resistance
- trend_direction
- chart_patterns
- technical_analysis_details
- execution timing

### create_risk_assessment_node

Updates the state with:

- risk_score
- volatility
- beta
- var_score
- risk_metrics
- execution timing

### create_decision_making_node

Writes final outputs into the state:

- recommendation
- confidence_score
- price_target
- stop_loss
- rationale
- decision_details
- total execution time

Each node catches exceptions, appends an error message to state["errors"], and returns the modified state instead of failing hard.

## StockAnalysisWorkflow Wrapper

This class is the primary application-facing interface.

### __init__

Stores both configs and compiles the LangGraph workflow.

### analyze_stock

Creates a fully initialized default state object, invokes the graph, logs warnings and errors, and returns the final result dictionary.

### analyze_multiple_stocks

Loops over a list of symbols and analyzes them one at a time.

This is synchronous despite the notebook importing asyncio.

### get_workflow_status

Returns a small status report about configuration and enabled analysis stages.

## Utility Functions

### create_default_configs

Loads configuration values from environment variables.

### validate_configuration

Checks which optional API credentials are present.

### setup_logging_config

Creates stream and file logging handlers.

### async_analyze_stocks

This is only a placeholder. It returns the synchronous multi-stock analysis result and does not yet perform concurrent execution.

### create_workflow_visualization

Returns a text diagram of the processing flow.

### demo_workflow_setup

Demonstrates:

- config creation
- validation
- workflow construction
- status printing

The notebook ends by printing the workflow visualization.

## Error Handling Strategy

Most methods follow the same pattern:

- wrap logic in try/except
- log the exception
- return an empty dictionary or safe default

At the graph level, node functions add human-readable messages to the shared state error list.

This makes the tutorial robust for demonstration purposes, but it can also hide failures because many functions silently fall back to neutral values.

## Design Strengths

- Clear separation of concerns across agent classes
- Shared state makes inter-stage communication explicit
- LangGraph provides a visible execution pipeline
- External API usage is optional rather than mandatory
- Output includes both structured metrics and a narrative rationale

## Design Gaps and Caveats

Several implementation gaps are worth noting if this tutorial is used as a base for a real project.

### Imported but unused components

These imports or configs are present but not meaningfully used in the final workflow logic:

- ChatOpenAI
- create_react_agent
- HumanMessage and AIMessage
- tool
- TechnicalIndicators dataclass
- Alpha Vantage clients in the workflow path
- BeautifulSoup
- requests in most of the final logic

### Type consistency issues

- The TypedDict omits fields later added to the state.
- Several functions promise one shape but return nested dictionaries that require awkward extraction.

### Incomplete use of available analysis

- get_historical_analysis exists but is never injected into the state.
- Alpha Vantage is configured but most data retrieval relies entirely on yfinance.
- OpenAI configuration exists but no LLM-driven reasoning is actually used.

### Heuristic modeling

- Sentiment uses TextBlob, which is simple and easy to explain but shallow for finance text.
- Chart pattern detection is rule-based and may produce false positives.
- Monte Carlo VaR assumes normally distributed returns.

### Final notebook state

The last several cells are empty, so the notebook stops at framework setup rather than showing a full worked example of calling analyze_stock on a real ticker inside the notebook itself.

## End-to-End Execution Flow

When analyze_stock("AAPL") or a similar call is made, the code follows this sequence:

1. Create an initialized state dictionary.
2. Run data_analysis to fetch price, company, financial, market, and economic data.
3. Run sentiment_analysis to derive sentiment scores and detail payloads.
4. Run technical_analysis to derive indicators, levels, trend, and patterns.
5. Run risk_assessment to compute volatility, beta, VaR, liquidity, and fundamental risk.
6. Run decision_making to synthesize everything into a recommendation.
7. Return the enriched state with final outputs and execution metadata.

## Summary

The tutorial implements a modular stock-analysis engine using a notebook as the delivery format. The real core is not an LLM agent in the strict sense, but a deterministic multi-stage analysis pipeline wrapped in LangGraph. Each stage adds a specialized layer of analysis, and the final decision layer converts those outputs into an investment recommendation with a confidence score, price target, stop-loss, and written rationale.

For teaching purposes, the notebook is well structured and demonstrates how to break a complex financial workflow into reusable agents. For production use, the main follow-up work would be tightening typing, removing unused dependencies, improving signal quality, and adding a real example execution plus tests.
# Stock Analyser Agent - Workflow

## Workflow Graph

```
┌─────────────────────┐
│   data_analysis     │  (Entry Point)
└─────────┬───────────┘
          │
    ┌─────┼──────────────┐
    │     │              │
    ▼     ▼              ▼
┌────────┐ ┌──────────────┐ ┌───────────────────┐
│sentiment│ │  technical   │ │ upstock_prediction │
│analysis │ │  analysis    │ │                   │
└────┬───┘ └──────┬───────┘ └────────┬──────────┘
     │             │                  │
     └──────┬──────┴──────────────────┘
            ▼
┌─────────────────────┐
│   risk_assessment   │
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   decision_making   │
└─────────┬───────────┘
          │
          ▼
        [END]
```

## Nodes

### 1. Data Analysis (Entry Point)
- **Function:** `create_data_analysis_node(data_agent)`
- **Role:** Fetches and processes raw stock market data (price history, volume, fundamentals).
- **Outputs to:** Sentiment Analysis, Technical Analysis, Upstock Prediction

### 2. Sentiment Analysis
- **Function:** `create_sentiment_analysis_node(sentiment_agent)`
- **Role:** Analyzes news articles, social media, and market sentiment related to the stock.
- **Outputs to:** Risk Assessment

### 3. Technical Analysis
- **Function:** `create_technical_analysis_node(technical_agent)`
- **Role:** Performs technical indicator calculations (moving averages, RSI, MACD, etc.) on price data.
- **Outputs to:** Risk Assessment

### 4. Upstock Prediction
- **Function:** `create_upstock_prediction_node(prediction_agent)`
- **Role:** Uses ML (Linear Regression on engineered features) to predict the stock's price direction over the next 5 trading days. Features include lagged returns, SMA ratios, volatility, and volume ratio.
- **Outputs to:** Risk Assessment

### 5. Risk Assessment
- **Function:** `create_risk_assessment_node(risk_agent)`
- **Role:** Evaluates overall risk by combining sentiment, technical signals, and prediction data.
- **Outputs to:** Decision Making

### 6. Decision Making (Terminal)
- **Function:** `create_decision_making_node(decision_agent)`
- **Role:** Makes final buy/sell/hold recommendation based on the risk assessment.
- **Outputs to:** END

## Edges (Data Flow)

| From | To |
|------|-----|
| data_analysis | sentiment_analysis |
| data_analysis | technical_analysis |
| data_analysis | upstock_prediction |
| sentiment_analysis | risk_assessment |
| technical_analysis | risk_assessment |
| upstock_prediction | risk_assessment |
| risk_assessment | decision_making |
| decision_making | END |

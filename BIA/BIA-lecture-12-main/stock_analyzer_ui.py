import os
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from scipy import stats
from datetime import datetime, timedelta
from typing import Dict, List, Optional, TypedDict, Any
from dataclasses import dataclass
import logging
import ta
import yfinance as yf
from textblob import TextBlob
from sklearn.linear_model import LinearRegression
import gradio as gr

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── Stock Search Helper ───────────────────────────────────────────────────────
POPULAR_STOCKS = {
    "Apple": "AAPL", "Microsoft": "MSFT", "Google (Alphabet)": "GOOGL",
    "Amazon": "AMZN", "Tesla": "TSLA", "Meta (Facebook)": "META",
    "Netflix": "NFLX", "Nvidia": "NVDA", "AMD": "AMD",
    "Intel": "INTC", "IBM": "IBM", "Oracle": "ORCL",
    "Salesforce": "CRM", "Adobe": "ADBE", "PayPal": "PYPL",
    "Visa": "V", "Mastercard": "MA", "JPMorgan Chase": "JPM",
    "Goldman Sachs": "GS", "Bank of America": "BAC",
    "Wells Fargo": "WFC", "Citigroup": "C",
    "Walmart": "WMT", "Costco": "COST", "Target": "TGT",
    "Nike": "NKE", "Starbucks": "SBUX", "McDonald's": "MCD",
    "Coca-Cola": "KO", "PepsiCo": "PEP",
    "Johnson & Johnson": "JNJ", "Pfizer": "PFE", "Moderna": "MRNA",
    "UnitedHealth": "UNH", "Abbott Labs": "ABT",
    "ExxonMobil": "XOM", "Chevron": "CVX", "Shell": "SHEL",
    "Boeing": "BA", "Lockheed Martin": "LMT", "General Electric": "GE",
    "Ford": "F", "General Motors": "GM", "Toyota": "TM",
    "Disney": "DIS", "Comcast": "CMCSA", "AT&T": "T",
    "Verizon": "VZ", "T-Mobile": "TMUS",
    "Uber": "UBER", "Airbnb": "ABNB", "Spotify": "SPOT",
    "Snowflake": "SNOW", "Palantir": "PLTR", "Coinbase": "COIN",
    # Indian Stocks (NSE)
    "Tata Steel": "TATASTEEL.NS", "Tata Motors": "TATAMOTORS.NS",
    "Tata Consultancy Services (TCS)": "TCS.NS", "Tata Power": "TATAPOWER.NS",
    "Reliance Industries": "RELIANCE.NS", "Infosys": "INFY.NS",
    "Wipro": "WIPRO.NS", "HCL Tech": "HCLTECH.NS",
    "HDFC Bank": "HDFCBANK.NS", "ICICI Bank": "ICICIBANK.NS",
    "State Bank of India (SBI)": "SBIN.NS", "Kotak Mahindra Bank": "KOTAKBANK.NS",
    "Axis Bank": "AXISBANK.NS", "IndusInd Bank": "INDUSINDBK.NS",
    "Bajaj Finance": "BAJFINANCE.NS", "Bajaj Finserv": "BAJAJFINSV.NS",
    "Hindustan Unilever": "HINDUNILVR.NS", "ITC": "ITC.NS",
    "Asian Paints": "ASIANPAINT.NS", "Maruti Suzuki": "MARUTI.NS",
    "Mahindra & Mahindra": "M&M.NS", "Larsen & Toubro (L&T)": "LT.NS",
    "Sun Pharma": "SUNPHARMA.NS", "Dr Reddy's": "DRREDDY.NS",
    "Cipla": "CIPLA.NS", "Divis Labs": "DIVISLAB.NS",
    "Adani Enterprises": "ADANIENT.NS", "Adani Ports": "ADANIPORTS.NS",
    "Power Grid": "POWERGRID.NS", "NTPC": "NTPC.NS",
    "Coal India": "COALINDIA.NS", "ONGC": "ONGC.NS",
    "Bharti Airtel": "BHARTIARTL.NS", "Tech Mahindra": "TECHM.NS",
    "UltraTech Cement": "ULTRACEMCO.NS", "Grasim Industries": "GRASIM.NS",
    "Titan Company": "TITAN.NS", "Nestle India": "NESTLEIND.NS",
    "Britannia": "BRITANNIA.NS", "Hindalco": "HINDALCO.NS",
    "JSW Steel": "JSWSTEEL.NS", "Vedanta": "VEDL.NS",
    "Zomato": "ZOMATO.NS", "Paytm (One97)": "PAYTM.NS",
    "Nykaa (FSN E-Commerce)": "NYKAA.NS",
}

def search_stocks(query: str) -> list:
    """Search stocks by name or symbol and return matching options"""
    if not query or len(query) < 1:
        return [f"{name} ({symbol})" for name, symbol in list(POPULAR_STOCKS.items())[:20]]
    
    query_lower = query.lower()
    matches = []
    for name, symbol in POPULAR_STOCKS.items():
        if query_lower in name.lower() or query_lower in symbol.lower():
            matches.append(f"{name} ({symbol})")
    
    # If no match found in our list, allow direct symbol input
    if not matches:
        matches.append(f"Use symbol directly: {query.upper()}")
    
    return matches[:15]


def extract_symbol(selection: str) -> str:
    """Extract the stock symbol from the dropdown selection"""
    if not selection:
        return ""
    if selection.startswith("Use symbol directly:"):
        return selection.replace("Use symbol directly:", "").strip()
    # Extract symbol from "Company Name (SYMBOL)" format
    if "(" in selection and ")" in selection:
        return selection.split("(")[-1].replace(")", "").strip()
    return selection.strip()


# ─── Configs ───────────────────────────────────────────────────────────────────
@dataclass
class APIConfig:
    alpha_vantage_key: str = ""
    news_api_key: str = ""
    fred_api_key: str = ""
    twitter_bearer_token: str = ""
    reddit_client_id: str = ""
    reddit_client_secret: str = ""
    openai_api_key: str = ""

@dataclass
class AnalysisConfig:
    lookback_days: int = 252
    short_ma_period: int = 20
    long_ma_period: int = 50
    rsi_period: int = 14
    bollinger_period: int = 20
    confidence_threshold: float = 0.6
    risk_free_rate: float = 0.02


# ─── Data Analysis Agent ───────────────────────────────────────────────────────
class DataAnalysisAgent:
    def __init__(self, config: APIConfig):
        self.config = config

    def fetch_stock_data(self, symbol: str, period: str = "1y") -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            hist = ticker.history(period=period)
            if hist.empty:
                return {}
            current_price = info.get('currentPrice', hist['Close'].iloc[-1])
            previous_close = info.get('previousClose', hist['Close'].iloc[-2])
            return {
                'symbol': symbol,
                'company_name': info.get('longName', symbol),
                'current_price': current_price,
                'previous_close': previous_close,
                'price_change': current_price - previous_close,
                'price_change_percent': ((current_price - previous_close) / previous_close) * 100,
                'volume': info.get('volume', int(hist['Volume'].iloc[-1])),
                'market_cap': info.get('marketCap', 0),
                'historical_data': hist,
                'info': info
            }
        except Exception as e:
            logger.error(f"Error fetching stock data for {symbol}: {e}")
            return {}

    def get_financial_data(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                'financial_ratios': {
                    'pe_ratio': info.get('trailingPE', 0),
                    'forward_pe': info.get('forwardPE', 0),
                    'peg_ratio': info.get('pegRatio', 0),
                    'price_to_book': info.get('priceToBook', 0),
                    'debt_to_equity': info.get('debtToEquity', 0),
                    'roe': info.get('returnOnEquity', 0),
                    'profit_margin': info.get('profitMargins', 0),
                    'current_ratio': info.get('currentRatio', 0),
                },
                'analyst_info': {
                    'target_mean_price': info.get('targetMeanPrice', 0),
                    'recommendation_mean': info.get('recommendationMean', 0),
                }
            }
        except Exception as e:
            logger.error(f"Error fetching financial data: {e}")
            return {}


# ─── Sentiment Analysis Agent ──────────────────────────────────────────────────
class SentimentAnalysisAgent:
    def __init__(self, config: APIConfig):
        self.config = config

    def analyze_news_sentiment(self, symbol: str) -> Dict[str, Any]:
        try:
            ticker = yf.Ticker(symbol)
            news = ticker.news
            if not news:
                return {'sentiment_score': 0.0, 'article_count': 0}
            sentiments = []
            for item in news[:20]:
                title = item.get('title', '')
                if title:
                    sentiments.append(TextBlob(title).sentiment.polarity)
            return {
                'sentiment_score': float(np.mean(sentiments)) if sentiments else 0.0,
                'article_count': len(sentiments)
            }
        except Exception as e:
            logger.error(f"News sentiment error: {e}")
            return {'sentiment_score': 0.0, 'article_count': 0}

    def get_analyst_sentiment(self, symbol: str) -> Dict[str, Any]:
        try:
            info = yf.Ticker(symbol).info
            rec_mean = info.get('recommendationMean', 3.0)
            sentiment_score = (5 - rec_mean) / 2 - 1
            return {
                'sentiment_score': max(-1, min(1, sentiment_score)),
                'recommendation_mean': rec_mean,
                'number_of_analysts': info.get('numberOfAnalystOpinions', 0)
            }
        except Exception as e:
            logger.error(f"Analyst sentiment error: {e}")
            return {'sentiment_score': 0.0, 'recommendation_mean': 3.0}


# ─── Technical Analysis Agent ──────────────────────────────────────────────────
class TechnicalAnalysisAgent:
    def __init__(self, config: AnalysisConfig):
        self.config = config

    def calculate_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        try:
            if df.empty or len(df) < self.config.long_ma_period:
                return {}
            close = df['Close']
            high, low = df['High'], df['Low']
            rsi = ta.momentum.rsi(close, window=self.config.rsi_period)
            macd_line = ta.trend.macd(close)
            macd_signal = ta.trend.macd_signal(close)
            return {
                'sma_20': ta.trend.sma_indicator(close, window=20).iloc[-1],
                'sma_50': ta.trend.sma_indicator(close, window=50).iloc[-1],
                'rsi': rsi.iloc[-1] if not rsi.empty else 50,
                'macd': macd_line.iloc[-1] if not macd_line.empty else 0,
                'macd_signal': macd_signal.iloc[-1] if not macd_signal.empty else 0,
                'atr': ta.volatility.average_true_range(high, low, close).iloc[-1],
            }
        except Exception as e:
            logger.error(f"Technical indicators error: {e}")
            return {}

    def determine_trend(self, df: pd.DataFrame) -> str:
        try:
            if len(df) < 50:
                return 'Neutral'
            close = df['Close']
            sma20 = close.rolling(20).mean().iloc[-1]
            sma50 = close.rolling(50).mean().iloc[-1]
            current = close.iloc[-1]
            if current > sma20 > sma50:
                return 'Upward'
            elif current < sma20 < sma50:
                return 'Downward'
            return 'Sideways'
        except:
            return 'Neutral'


# ─── Upstock Prediction Agent ──────────────────────────────────────────────────
class StockPredictionAgent:
    def __init__(self, config: AnalysisConfig):
        self.config = config
        self.prediction_days = 5

    def predict_stock_price(self, df: pd.DataFrame) -> Dict[str, Any]:
        try:
            if df.empty or len(df) < 60:
                return {'predicted_price': 0.0, 'prediction_direction': 'Neutral', 'confidence': 0.0}

            features_df = pd.DataFrame(index=df.index)
            features_df['return_1d'] = df['Close'].pct_change(1)
            features_df['return_5d'] = df['Close'].pct_change(5)
            features_df['sma_10'] = df['Close'].rolling(10).mean() / df['Close'] - 1
            features_df['sma_20'] = df['Close'].rolling(20).mean() / df['Close'] - 1
            features_df['volatility_10'] = df['Close'].pct_change().rolling(10).std()
            features_df['volume_ratio'] = df['Volume'] / df['Volume'].rolling(20).mean()
            features_df.dropna(inplace=True)

            if len(features_df) < 30:
                return {'predicted_price': 0.0, 'prediction_direction': 'Neutral', 'confidence': 0.0}

            aligned_close = df['Close'].loc[features_df.index]
            target = aligned_close.shift(-self.prediction_days) / aligned_close - 1

            valid_mask = target.notna()
            X_train = features_df[valid_mask].values
            y_train = target[valid_mask].values

            if len(X_train) < 20:
                return {'predicted_price': 0.0, 'prediction_direction': 'Neutral', 'confidence': 0.0}

            model = LinearRegression()
            model.fit(X_train, y_train)
            r2_score = model.score(X_train, y_train)

            latest_features = features_df.iloc[-1:].values
            predicted_return = model.predict(latest_features)[0]

            current_price = df['Close'].iloc[-1]
            predicted_price = current_price * (1 + predicted_return)

            if predicted_return > 0.02:
                direction = 'Bullish'
            elif predicted_return < -0.02:
                direction = 'Bearish'
            else:
                direction = 'Neutral'

            return {
                'predicted_price': round(float(predicted_price), 2),
                'predicted_return_pct': round(float(predicted_return * 100), 2),
                'prediction_direction': direction,
                'confidence': round(max(0, min(1, r2_score)) * 100, 1),
                'prediction_horizon_days': self.prediction_days,
                'model_r2': round(r2_score, 4),
                'current_price': round(float(current_price), 2)
            }
        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return {'predicted_price': 0.0, 'prediction_direction': 'Neutral', 'confidence': 0.0}


# ─── Risk Assessment Agent ─────────────────────────────────────────────────────
class RiskAssessmentAgent:
    def __init__(self, config: AnalysisConfig):
        self.config = config

    def calculate_risk(self, df: pd.DataFrame) -> Dict[str, Any]:
        try:
            returns = df['Close'].pct_change().dropna()
            annual_vol = returns.std() * np.sqrt(252)
            var_95 = np.percentile(returns, 5)

            # Beta
            try:
                spy = yf.Ticker("SPY").history(period="1y")
                common = df.index.intersection(spy.index)
                if len(common) > 30:
                    sr = df.loc[common]['Close'].pct_change().dropna()
                    mr = spy.loc[common]['Close'].pct_change().dropna()
                    ci = sr.index.intersection(mr.index)
                    sr, mr = sr.loc[ci], mr.loc[ci]
                    cov = np.cov(sr, mr)[0, 1]
                    beta = cov / np.var(mr) if np.var(mr) > 0 else 1.0
                else:
                    beta = 1.0
            except:
                beta = 1.0

            vol_risk = min(annual_vol / 0.4, 1.0)
            risk_score = vol_risk * 0.5 + min(abs(var_95) / 0.05, 1.0) * 0.3 + min(abs(beta - 1) * 0.5, 1.0) * 0.2

            if risk_score < 0.3:
                category = 'Low'
            elif risk_score < 0.6:
                category = 'Medium'
            else:
                category = 'High'

            return {
                'annual_volatility': round(float(annual_vol * 100), 2),
                'var_95': round(float(var_95 * 100), 2),
                'beta': round(float(beta), 3),
                'risk_score': round(float(risk_score), 3),
                'risk_category': category
            }
        except Exception as e:
            logger.error(f"Risk calculation error: {e}")
            return {'risk_score': 0.5, 'risk_category': 'Medium', 'annual_volatility': 0, 'var_95': 0, 'beta': 1.0}


# ─── Decision Making Agent ─────────────────────────────────────────────────────
class DecisionMakingAgent:
    def __init__(self, config: AnalysisConfig):
        self.config = config

    def make_decision(self, sentiment_score: float, technical_data: Dict, risk_data: Dict,
                      prediction_data: Dict, fundamental_data: Dict, current_price: float) -> Dict[str, Any]:
        # Sentiment score (-1 to 1)
        s_score = max(-1, min(1, sentiment_score))

        # Technical score
        indicators = technical_data.get('indicators', {})
        trend = technical_data.get('trend', 'Neutral')
        t_score = 0.0
        trend_map = {'Upward': 0.5, 'Sideways': 0.0, 'Downward': -0.5, 'Neutral': 0.0}
        t_score += trend_map.get(trend, 0)
        rsi = indicators.get('rsi', 50)
        if rsi > 70:
            t_score -= 0.3
        elif rsi < 30:
            t_score += 0.3
        macd = indicators.get('macd', 0)
        macd_sig = indicators.get('macd_signal', 0)
        t_score += 0.2 if macd > macd_sig else -0.2
        t_score = max(-1, min(1, t_score))

        # Risk score (lower risk = positive)
        r_score = 1 - (risk_data.get('risk_score', 0.5) * 2)
        r_score = max(-1, min(1, r_score))

        # Prediction score
        pred_dir = prediction_data.get('prediction_direction', 'Neutral')
        pred_conf = prediction_data.get('confidence', 0) / 100
        p_score = {'Bullish': 0.6, 'Neutral': 0.0, 'Bearish': -0.6}.get(pred_dir, 0) * pred_conf

        # Fundamental score
        ratios = fundamental_data.get('financial_ratios', {})
        f_score = 0.0
        pe = ratios.get('pe_ratio', 0)
        if 10 <= pe <= 20:
            f_score += 0.2
        elif pe > 30:
            f_score -= 0.2
        roe = ratios.get('roe', 0)
        if roe and roe > 0.15:
            f_score += 0.2
        elif roe and roe < 0:
            f_score -= 0.3
        f_score = max(-1, min(1, f_score))

        # Weighted combination
        weighted = (s_score * 0.15 + t_score * 0.25 + r_score * 0.2 + p_score * 0.2 + f_score * 0.2)
        weighted = max(-1, min(1, weighted))

        # Recommendation
        if weighted > 0.5:
            rec = 'STRONG BUY'
        elif weighted > 0.15:
            rec = 'BUY'
        elif weighted > -0.15:
            rec = 'HOLD'
        elif weighted > -0.5:
            rec = 'SELL'
        else:
            rec = 'STRONG SELL'

        # Confidence
        scores = [s_score, t_score, r_score, p_score, f_score]
        agreement = max(0, (2 - np.std(scores)) / 2)
        confidence = (agreement * 0.6 + abs(weighted) * 0.4) * 100

        # Price targets
        pred_price = prediction_data.get('predicted_price', 0)
        if rec in ['STRONG BUY', 'BUY']:
            target = current_price * 1.08 if pred_price == 0 else max(current_price * 1.05, pred_price)
            stop_loss = current_price * 0.95
        elif rec in ['SELL', 'STRONG SELL']:
            target = current_price * 0.92
            stop_loss = current_price * 1.05
        else:
            target = current_price * 1.02
            stop_loss = current_price * 0.95

        return {
            'recommendation': rec,
            'confidence': round(float(confidence), 1),
            'weighted_score': round(float(weighted), 3),
            'component_scores': {
                'sentiment': round(float(s_score), 3),
                'technical': round(float(t_score), 3),
                'risk': round(float(r_score), 3),
                'prediction': round(float(p_score), 3),
                'fundamental': round(float(f_score), 3),
            },
            'price_target': round(float(target), 2),
            'stop_loss': round(float(stop_loss), 2),
        }


# ─── Main Analysis Function ───────────────────────────────────────────────────
def run_stock_analysis(symbol: str) -> str:
    if not symbol or not symbol.strip():
        return "❌ Please enter a valid stock symbol."

    symbol = symbol.strip().upper()

    api_config = APIConfig()
    analysis_config = AnalysisConfig()

    data_agent = DataAnalysisAgent(api_config)
    sentiment_agent = SentimentAnalysisAgent(api_config)
    technical_agent = TechnicalAnalysisAgent(analysis_config)
    prediction_agent = StockPredictionAgent(analysis_config)
    risk_agent = RiskAssessmentAgent(analysis_config)
    decision_agent = DecisionMakingAgent(analysis_config)

    # Step 1: Data Analysis
    stock_data = data_agent.fetch_stock_data(symbol)
    if not stock_data:
        return f"❌ Could not fetch data for '{symbol}'. Please check the symbol and try again."

    financial_data = data_agent.get_financial_data(symbol)
    hist = stock_data['historical_data']

    # Step 2: Sentiment Analysis
    news_sent = sentiment_agent.analyze_news_sentiment(symbol)
    analyst_sent = sentiment_agent.get_analyst_sentiment(symbol)
    overall_sentiment = news_sent['sentiment_score'] * 0.5 + analyst_sent['sentiment_score'] * 0.5

    # Step 3: Technical Analysis
    indicators = technical_agent.calculate_indicators(hist)
    trend = technical_agent.determine_trend(hist)

    # Step 4: Upstock Prediction
    prediction = prediction_agent.predict_stock_price(hist)

    # Step 5: Risk Assessment
    risk = risk_agent.calculate_risk(hist)

    # Step 6: Decision Making
    decision = decision_agent.make_decision(
        sentiment_score=overall_sentiment,
        technical_data={'indicators': indicators, 'trend': trend},
        risk_data=risk,
        prediction_data=prediction,
        fundamental_data=financial_data,
        current_price=stock_data['current_price']
    )

    # ─── Format Output ─────────────────────────────────────────────────────────
    rec = decision['recommendation']
    rec_emoji = {'STRONG BUY': '🟢🟢', 'BUY': '🟢', 'HOLD': '🟡', 'SELL': '🔴', 'STRONG SELL': '🔴🔴'}.get(rec, '⚪')

    output = f"""
{'='*60}
📊 STOCK ANALYSIS REPORT: {symbol}
{'='*60}

🏢 Company: {stock_data['company_name']}
📅 Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

{'─'*60}
💰 PRICE DATA
{'─'*60}
  Current Price:    ${stock_data['current_price']:.2f}
  Price Change:     ${stock_data['price_change']:.2f} ({stock_data['price_change_percent']:.2f}%)
  Volume:           {stock_data['volume']:,}
  Market Cap:       ${stock_data['market_cap']:,.0f}

{'─'*60}
📰 SENTIMENT ANALYSIS
{'─'*60}
  News Sentiment:      {news_sent['sentiment_score']:.3f} ({news_sent['article_count']} articles)
  Analyst Sentiment:   {analyst_sent['sentiment_score']:.3f} (Rec Mean: {analyst_sent.get('recommendation_mean', 'N/A')})
  Overall Sentiment:   {overall_sentiment:.3f}

{'─'*60}
📈 TECHNICAL ANALYSIS
{'─'*60}
  Trend:         {trend}
  RSI:           {indicators.get('rsi', 'N/A'):.1f}
  MACD:          {indicators.get('macd', 'N/A'):.4f}
  MACD Signal:   {indicators.get('macd_signal', 'N/A'):.4f}
  SMA 20:        ${indicators.get('sma_20', 0):.2f}
  SMA 50:        ${indicators.get('sma_50', 0):.2f}
  ATR:           ${indicators.get('atr', 0):.2f}

{'─'*60}
🔮 UPSTOCK PREDICTION (Next {prediction.get('prediction_horizon_days', 5)} Days)
{'─'*60}
  Predicted Price:     ${prediction.get('predicted_price', 0):.2f}
  Predicted Return:    {prediction.get('predicted_return_pct', 0):.2f}%
  Direction:           {prediction.get('prediction_direction', 'N/A')}
  Model Confidence:    {prediction.get('confidence', 0):.1f}%
  Model R²:           {prediction.get('model_r2', 0):.4f}

{'─'*60}
⚠️ RISK ASSESSMENT
{'─'*60}
  Risk Category:       {risk.get('risk_category', 'N/A')}
  Risk Score:          {risk.get('risk_score', 0):.3f}
  Annual Volatility:   {risk.get('annual_volatility', 0):.2f}%
  VaR (95%):           {risk.get('var_95', 0):.2f}%
  Beta:                {risk.get('beta', 0):.3f}

{'─'*60}
{'='*60}
{rec_emoji} DECISION: {rec}
{'='*60}
  Confidence:      {decision['confidence']:.1f}%
  Weighted Score:  {decision['weighted_score']:.3f}
  Price Target:    ${decision['price_target']:.2f}
  Stop Loss:       ${decision['stop_loss']:.2f}

  Component Scores:
    • Sentiment:    {decision['component_scores']['sentiment']:.3f}
    • Technical:    {decision['component_scores']['technical']:.3f}
    • Risk:         {decision['component_scores']['risk']:.3f}
    • Prediction:   {decision['component_scores']['prediction']:.3f}
    • Fundamental:  {decision['component_scores']['fundamental']:.3f}
{'='*60}
"""
    return output


# ─── Wrapper to handle dropdown selection ──────────────────────────────────────
def analyze_from_selection(selection: str) -> str:
    """Extract symbol from selection and run analysis"""
    symbol = extract_symbol(selection)
    if not symbol:
        return "❌ Please select or type a stock name."
    return run_stock_analysis(symbol)


# ─── Gradio UI ─────────────────────────────────────────────────────────────────
with gr.Blocks(title="Stock Analyzer Agent", theme=gr.themes.Soft()) as app:
    gr.Markdown("# 📊 Stock Analyzer Agent")
    gr.Markdown("Search for a stock by **company name** or **symbol** and get a full AI-powered analysis.")
    gr.Markdown("Pipeline: **Data → Sentiment → Technical → Upstock Prediction → Risk → Decision**")

    with gr.Row():
        search_input = gr.Textbox(
            label="🔍 Search Stock (type company name or symbol)",
            placeholder="Start typing... e.g. Tata, Apple, Reliance, MSFT",
            scale=3
        )

    with gr.Row():
        stock_dropdown = gr.Dropdown(
            label="📋 Select from results",
            choices=[f"{name} ({symbol})" for name, symbol in list(POPULAR_STOCKS.items())[:20]],
            scale=3,
            allow_custom_value=True
        )
        analyze_btn = gr.Button("🚀 Analyze Stock", variant="primary", scale=1)

    with gr.Row():
        gr.Markdown("*💡 Tip: You can also type a symbol directly (e.g. `AAPL`, `TATASTEEL.NS`) in the search box and select it.*")

    output_box = gr.Textbox(
        label="📊 Analysis Report",
        lines=50,
        max_lines=60
    )

    # Update dropdown when user types in search
    search_input.change(
        fn=search_stocks,
        inputs=search_input,
        outputs=stock_dropdown
    )

    # Run analysis on button click
    analyze_btn.click(fn=analyze_from_selection, inputs=stock_dropdown, outputs=output_box)

    # Also run on Enter in search box (uses first match)
    def analyze_from_search(query: str) -> str:
        matches = search_stocks(query)
        if matches:
            return analyze_from_selection(matches[0])
        return run_stock_analysis(query.strip().upper())

    search_input.submit(fn=analyze_from_search, inputs=search_input, outputs=output_box)

    gr.Markdown("---")
    gr.Markdown("*⚠️ This is for educational purposes only. Not financial advice.*")

if __name__ == "__main__":
    app.launch()

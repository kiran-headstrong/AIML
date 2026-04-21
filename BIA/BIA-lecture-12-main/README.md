# Stock Analyser Agent — Lecture 12 Hands-On Demo

---

## Getting Started — Installing VS Code & GitHub Copilot

Before working with the notebook, you need a code editor. We recommend **Visual Studio Code (VS Code)** — a free, lightweight editor that works on all major platforms.

---

### Installing VS Code

#### Windows

1. **Download the installer**
   - Go to [https://code.visualstudio.com/download](https://code.visualstudio.com/download).
   - Click the **Windows** button to download the `.exe` installer (User Setup is recommended).

2. **Run the installer**
   - Double-click the downloaded `VSCodeUserSetup-x64-<version>.exe` file.
   - Accept the licence agreement and click **Next**.
   - Choose the installation location (the default is fine) and click **Next**.
   - On the **Select Additional Tasks** screen, check the following recommended options:
     - **Add "Open with Code" action to Windows Explorer file context menu**
     - **Add "Open with Code" action to Windows Explorer directory context menu**
     - **Add to PATH** (this lets you open VS Code from the terminal with `code .`)
   - Click **Next**, then **Install**.

3. **Launch VS Code**
   - Once installation finishes, check **Launch Visual Studio Code** and click **Finish**.
   - VS Code will open. You are ready to go.

4. **Verify from the terminal** (optional)
   - Open **Command Prompt** or **PowerShell** and run:
     ```
     code --version
     ```
   - You should see the installed version number.

---

#### macOS

1. **Download the application**
   - Go to [https://code.visualstudio.com/download](https://code.visualstudio.com/download).
   - Click the **macOS** button. This downloads a `.zip` file.

2. **Install**
   - Open the downloaded `.zip` file (it will extract automatically).
   - Drag **Visual Studio Code.app** into your **Applications** folder.

3. **Launch VS Code**
   - Open **Applications** and double-click **Visual Studio Code**.
   - If macOS shows a security prompt ("App downloaded from the internet"), click **Open**.

4. **Add `code` to your PATH** (recommended)
   - Open VS Code.
   - Press `Cmd + Shift + P` to open the **Command Palette**.
   - Type `Shell Command: Install 'code' command in PATH` and select it.
   - Now you can open any folder from Terminal:
     ```bash
     code .
     ```

5. **Verify from the terminal** (optional)
   ```bash
   code --version
   ```

---

#### Ubuntu / Debian-based Linux

##### Option A — Using the `.deb` package (recommended)

1. **Download the `.deb` package**
   - Go to [https://code.visualstudio.com/download](https://code.visualstudio.com/download).
   - Click the **.deb** button under Linux.

2. **Install the package**
   ```bash
   sudo apt update
   sudo dpkg -i ~/Downloads/code_*.deb
   sudo apt install -f   # resolves any missing dependencies
   ```

3. **Launch VS Code**
   ```bash
   code
   ```

##### Option B — Using the Snap store

```bash
sudo snap install --classic code
```

##### Option C — Using the Microsoft APT repository

```bash
# Install dependencies
sudo apt update
sudo apt install -y wget gpg apt-transport-https

# Import the Microsoft GPG key
wget -qO- https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > packages.microsoft.gpg
sudo install -D -o root -g root -m 644 packages.microsoft.gpg /etc/apt/keyrings/packages.microsoft.gpg
rm packages.microsoft.gpg

# Add the VS Code repository
echo "deb [arch=amd64,arm64,armhf signed-by=/etc/apt/keyrings/packages.microsoft.gpg] https://packages.microsoft.com/repos/code stable main" | sudo tee /etc/apt/sources.list.d/vscode.list > /dev/null

# Install VS Code
sudo apt update
sudo apt install -y code
```

**Verify installation:**
```bash
code --version
```

---

### Recommended VS Code Extensions for This Course

After installing VS Code, open it and install the following extensions. You can install extensions by clicking the **Extensions** icon in the left sidebar (or pressing `Ctrl+Shift+X` / `Cmd+Shift+X`) and searching by name.

| Extension | Publisher | Purpose |
|---|---|---|
| **Python** | Microsoft | Python language support, IntelliSense, debugging |
| **Jupyter** | Microsoft | Run `.ipynb` notebooks directly in VS Code |
| **Pylance** | Microsoft | Fast Python type checking and auto-complete |
| **GitHub Copilot** | GitHub | AI-powered code suggestions |
| **GitHub Copilot Chat** | GitHub | Chat with Copilot for explanations and help |

---

### Setting Up GitHub Copilot in VS Code

GitHub Copilot is an AI pair programmer that suggests code as you type. As a student, you can get **GitHub Copilot for free** through the GitHub Student Developer Pack.

#### Step 1 — Get GitHub Copilot Access

1. **Create a GitHub account** (if you don't have one) at [https://github.com](https://github.com).
2. **Apply for the GitHub Student Developer Pack:**
   - Go to [https://education.github.com/pack](https://education.github.com/pack).
   - Click **Get your Pack** / **Sign up for Student Developer Pack**.
   - Verify your student status using your university email address or student ID.
   - Approval is usually within a few days.
3. Once approved, GitHub Copilot will be enabled on your account at no cost.

#### Step 2 — Install the GitHub Copilot Extensions

1. Open **VS Code**.
2. Go to the **Extensions** panel (`Ctrl+Shift+X` on Windows/Linux, `Cmd+Shift+X` on macOS).
3. Search for **GitHub Copilot** and click **Install**.
4. Search for **GitHub Copilot Chat** and click **Install**.

#### Step 3 — Sign In to GitHub from VS Code

1. After installing the extensions, you will see a prompt in the bottom-right corner asking you to sign in to GitHub. Click **Sign in to GitHub**.
2. A browser window will open. Sign in with your GitHub account and **Authorize Visual Studio Code**.
3. You will be redirected back to VS Code. The Copilot icon in the status bar (bottom of the window) should now show as active.

#### Step 4 — Verify Copilot is Working

1. Open or create any Python file (e.g., `test.py`).
2. Start typing a function definition:
   ```python
   def calculate_average(numbers):
   ```
3. Copilot should suggest a completion in grey text. Press **Tab** to accept the suggestion.
4. To open **Copilot Chat**, click the chat icon in the left sidebar or press `Ctrl+Shift+I` (Windows/Linux) / `Cmd+Shift+I` (macOS).

#### Useful Copilot Shortcuts

| Action | Windows / Linux | macOS |
|---|---|---|
| Accept suggestion | `Tab` | `Tab` |
| Dismiss suggestion | `Esc` | `Esc` |
| Next suggestion | `Alt + ]` | `Option + ]` |
| Previous suggestion | `Alt + [` | `Option + [` |
| Open Copilot Chat | `Ctrl + Shift + I` | `Cmd + Shift + I` |
| Inline Chat | `Ctrl + I` | `Cmd + I` |

---

## Overview

This notebook demonstrates how to build a **multi-agent stock analysis system** using **LangGraph** and **LangChain**. The system combines five specialised agents that work together in a directed workflow to produce an investment recommendation for any given stock ticker.

## Architecture

```
[Input: Stock Symbol]
        |
[Data Analysis Agent] ──────┐
        |                    |
        v                    v
[Sentiment Analysis]   [Technical Analysis]
        |                    |
        └──────┬─────────────┘
               v
     [Risk Assessment Agent]
               |
               v
     [Decision Making Agent]
               |
               v
     [Output: Recommendation]
```

**Parallel Processing:** Sentiment and Technical analysis can run in parallel. Risk Assessment waits for both to complete before the Decision Making agent synthesises everything.

---

## Prerequisites

- **Python 3.10+** (tested with 3.13)
- This repository intentionally includes a ready-to-use `.venv` so students can run the notebook with the same environment used in class.

### About the bundled `.venv`

The included `.venv` is meant to help students run the notebook with the same package set used for this lecture.

- If you are on a similar setup, you can usually select the bundled `.venv` directly as your notebook kernel.
- If you are on a different operating system or architecture, the bundled `.venv` may not work because Python environments contain platform-specific binaries.
- In that case, keep the repository files but recreate `.venv` locally with the same package list.

### API Keys (Optional)

The system works with **yfinance** out of the box (no API key needed). For richer data, you can set the following environment variables:

| Variable | Service | Used For |
|---|---|---|
| `ALPHA_VANTAGE_API_KEY` | Alpha Vantage | Fundamental data, time series |
| `NEWS_API_KEY` | NewsAPI | News article fetching |
| `FRED_API_KEY` | FRED | Economic indicators (GDP, CPI, etc.) |
| `TWITTER_BEARER_TOKEN` | Twitter/X API | Social media sentiment |
| `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET` | Reddit API | Reddit sentiment |
| `OPENAI_API_KEY` | OpenAI | LLM-powered analysis (future) |

---

## Notebook Structure

The notebook is organised into the following sections:

### Cell 1 — Package Installation
Installs all required Python packages via `pip`.

### Cell 2 — Imports & Logging Setup
Imports libraries for data manipulation (`pandas`, `numpy`), financial data (`yfinance`, `alpha_vantage`), sentiment analysis (`TextBlob`, `newsapi`), technical indicators (`ta`), visualisation (`plotly`, `matplotlib`), and the LangGraph/LangChain framework.

### Cell 3–4 — State & Configuration Classes
- **`StockAnalysisState`** — A `TypedDict` that acts as the shared state passed between all agents. Contains fields for market data, sentiment scores, technical indicators, risk metrics, and the final recommendation.
- **`APIConfig`** — Holds API keys for external services.
- **`AnalysisConfig`** — Tunable parameters (lookback period, moving average windows, RSI period, etc.).
- **`TechnicalIndicators`** — Data class for structured indicator storage.

### Cell 5–9 — Data Analysis Agent
**`DataAnalysisAgent`** fetches and processes raw financial data:
- `fetch_stock_data()` — Current price, volume, market cap, and historical OHLCV via yfinance.
- `get_historical_analysis()` — Annualised return, volatility, Sharpe ratio, max drawdown.
- `get_financial_data()` — Income statement, balance sheet, cash flow, and key ratios (P/E, ROE, debt/equity, etc.).
- `get_market_context()` — S&P 500, Dow Jones, NASDAQ, and VIX current levels.
- `get_economic_indicators()` — GDP, unemployment, CPI, Fed Funds Rate, 10Y Treasury (requires FRED API key).

### Cell 10–14 — Sentiment Analysis Agent
**`SentimentAnalysisAgent`** gauges market sentiment from multiple sources:
- **News sentiment** — Fetches articles via NewsAPI and Yahoo Finance, scores them with TextBlob.
- **Social media sentiment** — Analyses Twitter and Reddit posts (requires API keys).
- **Analyst sentiment** — Converts analyst recommendation consensus to a –1 to +1 scale.
- **Overall sentiment** — Weighted combination: News (40%), Social (30%), Analyst (30%).

### Cell 15–19 — Technical Analysis Agent
**`TechnicalAnalysisAgent`** computes a comprehensive set of indicators using the `ta` library:
- **Moving Averages** — SMA (20, 50, 200), EMA (12, 26, 50), WMA.
- **Momentum** — RSI, MACD, Stochastic Oscillator, Williams %R, CCI.
- **Volatility** — Bollinger Bands, ATR, Keltner Channels.
- **Volume** — OBV, VWAP, Chaikin Money Flow.
- **Trend** — ADX, Parabolic SAR, Aroon.
- **Support/Resistance** — Local min/max detection, Fibonacci retracements, pivot points.
- **Pattern Recognition** — Double Top/Bottom, Head & Shoulders, Triangles, Flags/Pennants.

### Cell 20–24 — Risk Assessment Agent
**`RiskAssessmentAgent`** evaluates investment risk across five dimensions:
- **Volatility risk** — Historical and rolling volatility, volatility percentile.
- **Market risk** — Beta, alpha, correlation with S&P 500.
- **Value at Risk (VaR)** — Historical, parametric, and Monte Carlo methods at 95% and 99% confidence. Also computes Expected Shortfall (CVaR).
- **Liquidity risk** — Average volume, bid-ask spread proxy, market cap classification.
- **Fundamental risk** — Based on P/E, debt/equity, profit margins, current ratio.

### Cell 25–29 — Decision Making Agent
**`DecisionMakingAgent`** synthesises all analyses into a final recommendation:
- Scores each dimension (sentiment, technical, risk, fundamental) on a –1 to +1 scale.
- Applies weighted combination: Technical (30%), Risk (25%), Fundamental (25%), Sentiment (20%).
- Generates recommendation: **STRONG BUY / BUY / HOLD / SELL / STRONG SELL**.
- Calculates confidence score based on inter-agent agreement and signal strength.
- Sets price targets and stop-loss levels using support/resistance and volatility.
- Produces a human-readable rationale and suggested time horizon.

### Cell 30–34 — LangGraph Workflow & Utilities
- **`setup_stock_analysis_workflow()`** — Builds the LangGraph `StateGraph`, wires up all agent nodes and edges, and compiles the workflow.
- **`StockAnalysisWorkflow`** — Orchestrator class with `analyze_stock()` and `analyze_multiple_stocks()` methods.
- **Utility functions** — Default config creation, config validation, logging setup, workflow visualisation, and a demo setup function.

---

## How to Run

### Option 1: Use the bundled lecture environment

1. **Clone the repository**.
2. **Open the project** in VS Code.
3. **Open the notebook**.
4. **Select the kernel** from the bundled `.venv`.
5. **Run cells sequentially** from top to bottom.

### Option 2: Recreate the environment if `.venv` does not work on your machine

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install langgraph langchain-openai yfinance alpha-vantage newsapi-python pandas numpy scikit-learn textblob requests beautifulsoup4 ta plotly matplotlib seaborn fredapi tweepy praw ipykernel scipy
```

After that, reopen the notebook and select the new `.venv` kernel.

### Run the workflow

After setup, use the workflow by calling:

```python
# Create configs (reads API keys from environment variables)
api_config, analysis_config = create_default_configs()

# Build the workflow
workflow = StockAnalysisWorkflow(api_config, analysis_config)

# Analyse a stock
result = workflow.analyze_stock("AAPL")

# View recommendation
print(result["recommendation"])
print(result["rationale"])
print(f"Price Target: ${result['price_target']}")
print(f"Stop Loss: ${result['stop_loss']}")
print(f"Confidence: {result['confidence_score']:.0f}%")
```

---

## Key Concepts for Students

| Concept | Where It Appears |
|---|---|
| **Multi-agent systems** | Each agent class is a specialised module with a single responsibility |
| **State management** | `StockAnalysisState` (TypedDict) is shared across all agents |
| **Graph-based workflows** | LangGraph `StateGraph` defines execution order and data flow |
| **Technical analysis** | Moving averages, RSI, MACD, Bollinger Bands, pattern recognition |
| **Sentiment analysis** | NLP with TextBlob on news/social media text |
| **Risk modelling** | VaR (historical, parametric, Monte Carlo), Beta, max drawdown |
| **Decision fusion** | Weighted scoring system combining multiple analysis dimensions |

---

## Troubleshooting

| Issue | Solution |
|---|---|
| `ImportError: cannot import name 'Graph' from 'langgraph.graph'` | Already fixed — the notebook uses `StateGraph` and `END` only |
| Missing API keys | The system degrades gracefully — yfinance data is always available |
| `IndentationError` | Already fixed — `_identify_triangle` method had incorrect indentation |
| Slow execution | First run downloads package data; subsequent runs are faster |

---

## Dependencies

```
langgraph, langchain-openai, yfinance, alpha-vantage, newsapi-python,
pandas, numpy, scipy, scikit-learn, textblob, requests, beautifulsoup4,
ta, plotly, matplotlib, seaborn, fredapi, tweepy, praw, ipykernel
```

# Stock Analyser Tutorial: Student Summary

## Problem Statement

This tutorial builds a stock analysis system that answers a practical investment question:

**Given a stock symbol, how can we combine market data, sentiment, technical indicators, and risk analysis to generate a final investment recommendation?**

Instead of relying on only one signal, the notebook creates a multi-step workflow that studies the stock from different angles and then produces a final recommendation such as:

- BUY
- HOLD
- SELL

It also estimates confidence, possible price target, stop-loss level, and a written rationale.

## What We Are Going To Implement

The tutorial implements a pipeline with five main stages:

1. Collect stock and company data
2. Analyze news, social, and analyst sentiment
3. Compute technical indicators and chart signals
4. Measure different kinds of risk
5. Combine everything into a final decision

To organize these stages, the notebook uses a shared state object and a LangGraph workflow.

For this lecture repository, a `.venv` folder is also included so students can try to run the notebook with the same environment used during preparation. If that bundled environment does not work on a different machine or operating system, students can recreate it locally and still follow the same notebook steps.

## High-Level Steps in the Tutorial

At a high level, the notebook follows this plan:

1. Set up the Python environment and import the required libraries.
2. Define a common state structure that all analysis stages can read and update.
3. Build a data analysis agent to fetch prices, company information, and financial data.
4. Build a sentiment analysis agent to estimate market mood from news, social media, and analysts.
5. Build a technical analysis agent to calculate indicators such as RSI, MACD, moving averages, and support/resistance.
6. Build a risk assessment agent to measure volatility, beta, Value at Risk, and liquidity/fundamental risk.
7. Build a decision-making agent to combine all previous results into a final recommendation.
8. Connect all stages into a workflow so the analysis runs in a structured sequence.

## Cell-by-Cell High-Level View

### Cell 1

Installs the required packages for financial data, sentiment analysis, technical analysis, and workflow orchestration.

### Cell 2

Introduces the plan for the shared state and the types of analysis the system will perform.

### Cell 3

Adds a heading for environment setup and imports.

### Cell 4

Imports all required libraries and sets up logging.

This cell is meant to prepare the notebook environment before the main implementation starts.

### Cells 5-6

Define the shared state and configuration classes.

These cells establish:

- what information the system tracks
- what API keys may be needed
- what default analysis settings will be used

### Cells 7-9

Introduce the data analysis section.

### Cells 8-9 code block

Implement the data analysis agent.

This stage is responsible for:

- fetching stock prices
- retrieving historical market data
- collecting financial statements and ratios
- getting market context such as index performance
- optionally collecting economic indicators

### Cell 10

Introduces the sentiment analysis section.

### Cell 10-14 code block

Implement the sentiment analysis agent.

This stage:

- fetches recent news
- scores article sentiment
- reads social media sentiment from Twitter and Reddit when configured
- gets analyst recommendations
- combines all sources into one overall sentiment score

### Cell 15

Introduces the technical analysis section.

### Cell 15-19 code block

Implement the technical analysis agent.

This stage calculates:

- moving averages
- RSI and MACD
- Bollinger Bands and volatility measures
- volume-based indicators
- trend direction
- support and resistance levels
- simple chart pattern signals

### Cell 20

Introduces the risk assessment section.

### Cell 20-24 code block

Implement the risk assessment agent.

This stage measures:

- volatility risk
- market risk using beta and correlation
- Value at Risk
- liquidity risk
- fundamental risk
- one overall risk score

### Cell 25

Introduces the decision-making section.

### Cell 25-29 code block

Implement the decision-making agent.

This stage:

- reads the results from all previous stages
- converts them into scores
- combines the scores with weights
- produces the final recommendation
- calculates confidence, price target, and stop-loss
- generates a written explanation

### Cell 30

Introduces the workflow section.

### Cell 30-34 code block

Build the LangGraph workflow and utility functions.

This section:

- creates one workflow node for each analysis stage
- connects the stages in the right order
- initializes the workflow wrapper class
- provides helper functions for configuration and setup

### Cells 19-25 at the end of the notebook

These final code cells are currently empty placeholders and do not yet add new functionality.

## Overall Workflow of the Tutorial

Once fully used, the tutorial is designed to run in this order:

1. Input a stock symbol
2. Fetch company and market data
3. Measure sentiment
4. Compute technical indicators
5. Assess risk
6. Combine results into a recommendation
7. Return the final analysis summary

## What Students Should Learn from This Tutorial

This tutorial is useful for understanding how to:

- break a complex problem into smaller analysis modules
- use Python classes to separate responsibilities
- store intermediate results in a shared state
- combine different financial signals into one decision
- organize a multi-step workflow with LangGraph

It is also a good example of how data engineering, analytics, and decision logic can be combined in one notebook project.

## Conclusion

This tutorial solves the problem of building a structured stock recommendation system from multiple sources of evidence. Instead of using a single indicator, it combines market data, sentiment, technical analysis, and risk metrics into one workflow.

The main idea is simple:

- each stage performs one job well
- each stage updates the shared state
- the final stage brings everything together into a recommendation

From a student perspective, the tutorial demonstrates how to design an end-to-end analytical pipeline, not just how to calculate individual stock metrics. It shows how separate analysis components can work together to produce a complete investment decision system.

For classroom use, the included `.venv` is there to reduce setup friction and help students run the notebook in an environment close to the original lecture setup.
# Binance Trading Bot

## Overview
This software is an automated trading bot designed to interact with the Binance cryptocurrency exchange. It uses Binance's API to execute trades based on predefined strategies, manage stop-loss and take-profit orders, and monitor market prices in real-time. The bot supports both spot and margin trading with isolated margin mode.

## Features
- **Automated Trading**: Executes trades based on predefined conditions.
- **Real-time Market Monitoring**: Continuously tracks the latest market price using Binance WebSocket.
- **Take Profit & Stop Loss**: Implements automated risk management strategies.
- **Trailing Take Profit**: Dynamically adjusts the take profit level based on price movements.
- **Error Handling & Recovery**: Detects and handles common API errors and network issues.
- **Spread Monitoring**: Ensures trades are executed only when the spread is within acceptable limits.
- **Loan Management**: Supports borrowing and repaying funds in margin trading.

## How It Works
1. **Initialization**: The bot connects to the Binance API using API credentials.
2. **Strategy Selection**: The bot operates in two modes:
   - **Up Strategy (Long Position)**: Buys assets and sells them at a higher price.
   - **Down Strategy (Short Position)**: Sells borrowed assets and buys them back at a lower price.
3. **Trade Execution**: The bot places market orders and monitors execution.
4. **Risk Management**: Stop-loss and take-profit orders are placed to manage potential risks.
5. **Live Monitoring**: The bot continuously updates its position and reacts to market movements.
6. **Trade Closure**: When profit/loss targets are hit, the bot closes the trade and records the results.

## Requirements
- Python 3.8+
- Binance API Key & Secret
- Binance Python SDK (`python-binance`)

## Usage
1. **Install Dependencies:**
   ```sh
   pip install python-binance
   ```
2. **Set API Credentials**: Modify `Config.py` with your Binance API Key and Secret.
3. **Run the Bot:**
   ```sh
   python main.py
   ```

## Configuration
The bot settings, including symbol selection, strategy parameters, and risk management configurations, are defined in `Config.py`.

## Disclaimer
Use this bot at your own risk. Trading cryptocurrencies involves significant risk, and past performance does not guarantee future results.


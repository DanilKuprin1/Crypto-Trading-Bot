import logging

from binance.client import Client


class Config:
    API_KEY = "-"
    API_SECRET = "-"
    BaseCurrency = ""
    QuoteCurrency = "USDT"
    Symbol = ""
    TickPriceRounding = 0
    TickPrice = 0
    BaseCurrencyMinAmountRounding = 0
    MinLotSize = 0
    TickPriceToCurrentPrice = 0
    InitialFluctuation = 0
    InitialSpread = 0
    MainDealRange = 0.000
    LossDealRange = 0.001
    ProfitDealRange = 0.005
    TradingAmountInQuote = 14
    FeeRate = 0.001
    BorrowComissionRate = 0.0000625
    AmountToHelpRepayTheLoan = MinLotSize / 10
    TakeProfitFollowingRangeAmount = 0.000
    SafeDealRangeAmount = 0
    AmountNotToMakeStopOrderExecuteInstantly = 0
    StopLossTakeProfitPassedByCheckAmount = 0
    SignificantChangeInHighestPriceInRelationPrevious = 0.002
    AmountToTransfer = 20
    DealTime = 25
    StuckPriceTimeout = 15
    FirstOverstayInDealTimeout = 120
    SecondOverstayInDealTimeout = 180
    TimeBetweenGettingTickers = 3
    NormalFlactuation = 0.01
    NormalStopLossPrice = 0.0015
    NormalProfitDealRange = NormalStopLossPrice + 4 * FeeRate
    MinTickPricesBetweenStopLossPriceAndStopPrice = 1
    MinTickPricesBetweenStopPriceAndCurrentPrice = 2
    MinPairVolumeInUSDTToTradeThePair = 0
    MinChangeAboveTheProfitDealRangeToTradePair = 0.00
    ProfitDealRangeMultiplierForMinRequiredChange = 2.5
    MinProfitDealRange = 1.0
    MinRequiredChangeForStartingSettingPair = (
        FeeRate * 4 * ProfitDealRangeMultiplierForMinRequiredChange + 0.002
    )
    MaxIncreaseInSpreadMultiplier = 1.5
    MaxNumOfDealsForACoughtPair = 1
    UnpleasantPairs = {}
    SpreadMultiplierForStopLossStopPriceAmount = 3
    SpreadMultiplierForStopPriceCurrentPriceAmount = 3
    SavingToFile = True
    FilePathToSave = ""

    def __init__(self, base="", quote="", tickPrice=0.1, minLotSize=0.1):
        self.BaseCurrency = base
        self.QuoteCurrency = quote
        self.TickPrice = tickPrice
        self.MinLotSize = minLotSize

    def setSymbol(self, symbol, currentPrice, priceChange):
        try:
            self.Symbol = symbol
            self.QuoteCurrency = "USDT"
            self.BaseCurrency = self.Symbol.replace("USDT", "")
            self.InitialFluctuation = priceChange
            connected = False
            attempts = 0
            while not connected and attempts < 3:
                try:
                    c = Client(api_key=Config.API_KEY, api_secret=Config.API_SECRET)
                    connected = True
                except Exception as e:
                    logging.error(e)
                    attempts += 1
            if not connected:
                logging.error("Could not connect to Binance client after retries")
                return False
            info_got = False
            info_attempts = 0
            while not info_got and info_attempts < 3:
                try:
                    info = c.get_symbol_info(symbol=self.Symbol)
                    info_got = True
                except Exception as e:
                    logging.error(f"Could not get {symbol} info: {e}")
                    info_attempts += 1
            if not info_got:
                logging.error("Could not retrieve symbol info after retries")
                return False
            for f in info["filters"]:
                if f["filterType"] == "PRICE_FILTER":
                    self.TickPrice = float(f["tickSize"])
                elif f["filterType"] == "LOT_SIZE":
                    self.MinLotSize = float(f["stepSize"])
            tr = 0
            tc = self.TickPrice
            for _ in range(10):
                if tc == 1:
                    self.TickPriceRounding = tr
                    break
                tr += 1
                tc *= 10
            mlr = 0
            mlc = self.MinLotSize
            for _ in range(10):
                if mlc == 1:
                    self.BaseCurrencyMinAmountRounding = mlr
                    break
                mlr += 1
                mlc *= 10
            logging.info(
                f"TickPrice = {self.TickPrice:.8f}; TickPriceRounding = {self.TickPriceRounding}"
            )
            logging.info(
                f"MinLotSize = {self.MinLotSize:.8f}; MinLotRounding = {self.BaseCurrencyMinAmountRounding}"
            )
            ratio = self.TickPrice / currentPrice
            self.TickPriceToCurrentPrice = ratio
            logging.info(
                f"CurrentPrice = {currentPrice:.8f}; PriceChange = {priceChange:.4f}; TickPrice/Price = {ratio:.5f}"
            )
            self.InitialSpread = self.getSpread(c, symbol)
            n1 = (
                self.InitialSpread * self.SpreadMultiplierForStopPriceCurrentPriceAmount
            )
            n1 = round(n1 * pow(10, self.TickPriceRounding)) / pow(
                10, self.TickPriceRounding
            )
            n2 = self.InitialSpread * self.SpreadMultiplierForStopLossStopPriceAmount
            n2 = round(n2 * pow(10, self.TickPriceRounding)) / pow(
                10, self.TickPriceRounding
            )
            n3 = n2 + n1
            self.LossDealRange = n3 / currentPrice
            self.ProfitDealRange = self.FeeRate * 4 + self.LossDealRange
            logging.info(
                f"StopLossPrice - StopPrice = {n2:.8f}; StopPrice - CurrentPrice = {n1:.8f}"
            )
            logging.info(
                f"LossDealRange = {self.LossDealRange:.4f}; ProfitDealRange = {self.ProfitDealRange:.4f}"
            )
            if priceChange > (
                self.ProfitDealRange
                * self.ProfitDealRangeMultiplierForMinRequiredChange
            ):
                self.SafeDealRangeAmount = round(n2, self.TickPriceRounding)
                self.AmountNotToMakeStopOrderExecuteInstantly = round(
                    n1, self.TickPriceRounding
                )
                self.StopLossTakeProfitPassedByCheckAmount = 0
                logging.info(
                    f"Spread = {self.InitialSpread:.8f}; SafeDealRangeAmount = {self.ProfitDealRange:.8f}"
                )
            else:
                logging.info(f"Price change {priceChange:.4f} is not enough")
                logging.info(
                    f"Spread = {self.InitialSpread:.8f}; ProfitDealRange = {self.ProfitDealRange:.4f}; T/P = {self.TickPriceToCurrentPrice:.4f}"
                )
                return False
        except Exception as e:
            logging.error(e)
            return False
        else:
            logging.info(f"Successfully set the symbol - {symbol}")
            return True

    def getSpread(self, client, symbol):
        try:
            info = client.get_orderbook_ticker(symbol=symbol)
            sp = round(
                float(info["askPrice"]) - float(info["bidPrice"]),
                self.TickPriceRounding,
            )
            return sp
        except Exception as e:
            logging.error(f"Could not get {symbol} spread: {e}")
            return -1

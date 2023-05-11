from math import floor
from math import ceil
from binance import Client
from traceback import print_exc

class Config:
    API_KEY = '-'
    API_SECRET = '-'

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
    AmountToHelpRepayTheLoan = MinLotSize/10

    TakeProfitFollowingRangeAmount = 0.000 #DON'T CHANGE HERE IT DOESN'T MATTER, CHANGE IN SETSYMBOL
    SafeDealRangeAmount = 0 #DON'T CHANGE HERE IT DOESN'T MATTER, CHANGE IN SETSYMBOL
    AmountNotToMakeStopOrderExecuteInstantly = 0 #DON'T CHANGE HERE IT DOESN'T MATTER, CHANGE IN SETSYMBOL
    StopLossTakeProfitPassedByCheckAmount = 0 #DON'T CHANGE HERE IT DOESN'T MATTER, CHANGE IN SETSYMBOL
    SignificantChangeInHighestPriceInRelationPrevious = 0.002

    AmountToTransfer = 20

    DealTime = 25
    StuckPriceTimeout = 15 
    FirstOverstayInDealTimeout = 120
    SecondOverstayInDealTimeout = 180
    TimeBetweenGettingTickers = 3

    #--------Experimental settings1.0
    NormalFlactuation = 0.01
    NormalStopLossPrice = 0.0015
    NormalProfitDealRange = NormalStopLossPrice+4*FeeRate
    MinTickPricesBetweenStopLossPriceAndStopPrice = 1
    MinTickPricesBetweenStopPriceAndCurrentPrice = 2
    #MinRequiredSuddenChangeToTradeCurrency = NormalFlactuation
    MinPairVolumeInUSDTToTradeThePair = 0

    #--------2.0
    MinChangeAboveTheProfitDealRangeToTradePair = 0.00
    ProfitDealRangeMultiplierForMinRequiredChange = 2.5
    MinProfitDealRange = 1.0
    MinRequiredChangeForStartingSettingPair = FeeRate*4*ProfitDealRangeMultiplierForMinRequiredChange+0.002
    MaxIncreaseInSpreadMultiplier = 1.5
    MaxNumOfDealsForACoughtPair = 1
    UnpleasantPairs = {}

    SpreadMultiplierForStopLossStopPriceAmount = 3
    SpreadMultiplierForStopPriceCurrentPriceAmount = 3

    SavingToFile = True
    FilePathToSave = "/Users/danilkuprin/Desktop/Speculation/code50_40/mainStrategy/testBookNewStrat43.xlsx"

    def __init__(self, base = "", quote = "", tickPrice = 0.1, minLotSize = 0.1):
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

            success = False
            attempt = 0
            while success == False and attempt <3:
                try:
                    client = Client(api_key=Config.API_KEY,api_secret=Config.API_SECRET)
                except Exception as ex:
                    print("\n"+str(ex))
                    print("_________Couldn't instantly connect Client_________")
                    attempt +=1
                else:
                    success = True
            if success == False:
                print("\n__________Still couldn't connect Client__________")
                return False

            success = False
            attempt = 0
            while success == False and attempt <3:
                try:
                    info = client.get_symbol_info(symbol=self.Symbol)
                except Exception as ex:
                    print(f"________Couldn't get {symbol} info________")
                    print(ex)
                    attempt +=1
                else:
                    success = True
            if success ==False:
                print("\n________Still couldn't get info__________")
                return False
                
            for filter in info["filters"]:
                if filter['filterType'] == 'PRICE_FILTER':
                    self.TickPrice = float(filter["tickSize"])
                elif filter['filterType'] == 'LOT_SIZE':
                    self.MinLotSize = float(filter['stepSize'])
            
            tickRounding = 0
            tickCheck = self.TickPrice
            for num in range(0,10):
                if tickCheck == 1:
                    self.TickPriceRounding = tickRounding
                    break
                tickRounding+=1
                tickCheck*=10

            minLotRounding = 0 
            minLotCheck = self.MinLotSize
            for num in range(0,10):
                if minLotCheck == 1:
                    self.BaseCurrencyMinAmountRounding = minLotRounding
                    break
                minLotRounding+=1
                minLotCheck*=10    
            print(f"\nTickPrice = {self.TickPrice:.8f}; TickPriceRounding = {self.TickPriceRounding:.8f}")
            print(f"\nMinLotSize = {self.MinLotSize:.8f}; MinLotRounding = {self.BaseCurrencyMinAmountRounding:.8f}")
            
            tickPriceToPriceRatio = self.TickPrice/currentPrice
            self.TickPriceToCurrentPrice = tickPriceToPriceRatio
            print("\nCurrentPrice = {:.8f}; PriceChange = {:.4f}; TickPrice/Price = {:.5f}".format(currentPrice,priceChange,tickPriceToPriceRatio))
            
            self.InitialSpread = self.getSpread(client = client, symbol=symbol)
            numOfTickPricesBetweenStopPriceAndCurrentPrice = ceil((self.InitialSpread*self.SpreadMultiplierForStopPriceCurrentPriceAmount)*pow(10,self.TickPriceRounding))/pow(10,self.TickPriceRounding)#have a closer look at past trades 
            numOfTickPricesBetweenStopLossPriceAndStopPrice = ceil((self.InitialSpread*self.SpreadMultiplierForStopLossStopPriceAmount)*pow(10,self.TickPriceRounding))/pow(10,self.TickPriceRounding)
            numOfTickPricesBetweenStopLossPriceAndCurrentPrice =  numOfTickPricesBetweenStopLossPriceAndStopPrice + numOfTickPricesBetweenStopPriceAndCurrentPrice
            self.LossDealRange = numOfTickPricesBetweenStopLossPriceAndCurrentPrice/currentPrice
            self.ProfitDealRange = self.FeeRate*4+self.LossDealRange
            print(f"\nStopLossPrice - StopPrice = {numOfTickPricesBetweenStopLossPriceAndStopPrice:.8f}; StopPrice - CurrentPrice = {numOfTickPricesBetweenStopPriceAndCurrentPrice:.8f}\n")
            print(f"LossDealRange = {self.LossDealRange:.4f}; ProfitDealRange = {self.ProfitDealRange:.4f}")


            if priceChange > (self.ProfitDealRange*self.ProfitDealRangeMultiplierForMinRequiredChange):
                self.SafeDealRangeAmount = round(numOfTickPricesBetweenStopLossPriceAndStopPrice,self.TickPriceRounding)
                self.AmountNotToMakeStopOrderExecuteInstantly = round(numOfTickPricesBetweenStopPriceAndCurrentPrice,self.TickPriceRounding)
                self.StopLossTakeProfitPassedByCheckAmount = 0
                print("\nSpread = {:.8f}; SafeDealRangeAmount = {:.8f}".format(self.InitialSpread,self.ProfitDealRange,self.LossDealRange,self.SafeDealRangeAmount))
            else:
                print(f"\n---------------------------------------------\n\nPrice change of {priceChange:.4f} is not enough for:\n")
                print(f"Spread = {self.InitialSpread:.8f}; ProfitDealRange = {self.ProfitDealRange:.4f}; TickPrice/CurrentPrice = {self.TickPriceToCurrentPrice:.4f}\n")
                print("---------------------------------------------")
                return False

            
            # self.InitialFluctuation = priceChange
            # suddenChangeInRelationToNormal = 1
            # numOfNormalFluctuations = 1
            # if priceChange>self.NormalFlactuation:
            #     suddenChangeInRelationToNormal = priceChange/self.NormalFlactuation
            # adjustedStopLossPrice = self.NormalStopLossPrice*suddenChangeInRelationToNormal

            # print("\ntickPrice = {:.8f}; minLot = {}; currentPrice = {:.8f}; priceChange = {:.4f}; TickPrice/Price = {:.5f}; AdjustedStopLossPrice = {:.5f}\n".format(self.TickPrice,self.MinLotSize,currentPrice,priceChange,tickPriceToPriceRatio,adjustedStopLossPrice))

            # if tickPriceToPriceRatio>=(adjustedStopLossPrice/(self.MinTickPricesBetweenStopLossPriceAndStopPrice + self.MinTickPricesBetweenStopPriceAndCurrentPrice)):

            #     print("\ntickPriceToPriceRatio>=adjustedStopLossPrice/{}".format(self.MinTickPricesBetweenStopLossPriceAndStopPrice + self.MinTickPricesBetweenStopPriceAndCurrentPrice))
            #     return False
                # if floor(priceChange/self.NormalFlactuation) != 0:
                #     numOfNormalFluctuations = floor(priceChange/self.NormalFlactuation)
                
                # self.ProfitDealRange =  tickPriceToPriceRatio*(self.MinTickPricesBetweenStopLossPriceAndStopPrice + self.MinTickPricesBetweenStopPriceAndCurrentPrice)*numOfNormalFluctuations + self.FeeRate*4
                # spread = self.getSpread(client = client, symbol = symbol)

                # if (priceChange-self.ProfitDealRange) < self.RequiredChangeAboveNormalProfitDealRange:
                #     print("\nCought change = {:.4f} and it isn't enough for TickPrice/Price ratio = {:.5f};ProfitDealRange = {:.4f}; RequiredPriceChange = {:.4f}".format(priceChange, tickPriceToPriceRatio, self.ProfitDealRange,(self.ProfitDealRange+self.RequiredChangeAboveNormalProfitDealRange)))
                #     return False
                # elif spread <0:
                #     print(f"\n_________Spread < 0________\n")
                #     return False
                # elif spread > round(self.TickPrice*numOfNormalFluctuations,self.TickPriceRounding):
                #     print(f"\n____________________Spread > {self.TickPrice:.8f}____________________\n")
                #     return False
                
                # self.SafeDealRangeAmount = self.TickPrice*self.MinTickPricesBetweenStopLossPriceAndStopPrice*numOfNormalFluctuations
                # self.AmountNotToMakeStopOrderExecuteInstantly = self.TickPrice*self.MinTickPricesBetweenStopPriceAndCurrentPrice*numOfNormalFluctuations
                # self.LossDealRange = tickPriceToPriceRatio*(self.MinTickPricesBetweenStopLossPriceAndStopPrice + self.MinTickPricesBetweenStopPriceAndCurrentPrice)*numOfNormalFluctuations
                # self.StopLossTakeProfitPassedByCheckAmount = 0
                # print("\nProfitDealRange = {:.4f}; LossDealRange = {:.4f}; SafeDealRangeAmount = {:.8f}; RequiredPriceChange = {:.4f}".format(self.ProfitDealRange,self.LossDealRange,self.SafeDealRangeAmount, (self.ProfitDealRange+self.RequiredChangeAboveNormalProfitDealRange)))
                # print("\nNumberOfNormalFluctuations = {}, ".format(numOfNormalFluctuations))        
                # return True
            # else:
            #     print("\ntickPriceToPriceRatio<adjustedStopLossPrice/{}".format(self.MinTickPricesBetweenStopLossPriceAndStopPrice + self.MinTickPricesBetweenStopPriceAndCurrentPrice))
            #     self.ProfitDealRange = self.FeeRate*4+adjustedStopLossPrice
            #     spread = self.getSpread(client = client, symbol = symbol)
            #     if round(spread/currentPrice,4) >= round(adjustedStopLossPrice/(self.MinTickPricesBetweenStopLossPriceAndStopPrice + self.MinTickPricesBetweenStopPriceAndCurrentPrice)*(self.MinTickPricesBetweenStopPriceAndCurrentPrice-1),4):
            #         print("\n_________Spread is too high!!!_________\n")
            #         return False
            #     self.LossDealRange = adjustedStopLossPrice
            #     self.SafeDealRangeAmount = currentPrice*(adjustedStopLossPrice/(self.MinTickPricesBetweenStopLossPriceAndStopPrice+self.MinTickPricesBetweenStopPriceAndCurrentPrice))*self.MinTickPricesBetweenStopLossPriceAndStopPrice
            #     self.AmountNotToMakeStopOrderExecuteInstantly = currentPrice*(adjustedStopLossPrice/(self.MinTickPricesBetweenStopLossPriceAndStopPrice+self.MinTickPricesBetweenStopPriceAndCurrentPrice))*self.MinTickPricesBetweenStopPriceAndCurrentPrice
            #     self.StopLossTakeProfitPassedByCheckAmount = 0
            #     print("\nProfitDealRange = {:.4f}; LossDealRange = {:.4f}; SafeDealRangeAmount = {:.8f}".format(self.ProfitDealRange,self.LossDealRange,self.SafeDealRangeAmount))
        except Exception as ex:
            print_exc()
            print(ex)
            print("\nSomething went wrong when trying to set {}".format(symbol))
            return False
        else:
            print("\nSuccessfully set the symbol - {}\n".format(symbol))

    def getSpread(self, client, symbol):
        try:
            info = client.get_orderbook_ticker(symbol = symbol)
            spread = round((float(info['askPrice'])-float(info['bidPrice'])),self.TickPriceRounding)
        except Exception as ex:
            print(ex)
            print(f"\n_________Couldn't get {symbol} spread_________\n")
            return -1 
        else:
            #print(f"\nSpread = {spread:.8f}")
            return spread


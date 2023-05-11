import asyncio
from distutils.command.config import config
from sys import exc_info
from time import time
from binance.client import Client
from binance import AsyncClient, BinanceSocketManager
from binance import enums
from binance import exceptions as exc
from enum import Enum
import math 
from Config import Config


class Issue(Enum):
    NoIssue = 0
    MainOrderWasNotPlaced = 1

currentPrice = 0
highestRichedPrice = 0
lowestRichedPrice = 0 

takeProfitPrice = 0 
stopLossPrice = 0
enteringPrice = 0
openOrders = {}
doingJob = True
client = None
inPosition = False
trailingTakeProfitSet = False
quantityInBase = 0
quantityInBaseToSell = 0
quantityInBaseToBuy = 0 
quantityInQoute = 0
mainOrder = None
stopLoss = None 
followingStopLoss = None
takeProfit = None
trailingTakeProfit = None
startedFollowing = False
issue = Issue.NoIssue
forcedClosure = False
forcedCloseOrder = None
exceptions = []
strategy = 0 #0 for up, 1 for down 
repayed = False
Settings = None
isIsolated = "TRUE"
numOfTimesPriceDidNotDeviateFromZero = 0


async def getCurrentPrice():
    global currentPrice
    global exceptions
    global doingJob
    attempt = 0 
    success = False
    asyncClient1 = None
    while success != True and attempt <3:
        try:
            asyncClient1 = await AsyncClient.create()
        except Exception as ex:
            exceptions.append("Couldn't create AsyncClient1")
            print("\n______Couldn't create AsyncClient1!!______\n")
            print(ex)
            attempt+=1
        else:
            print("\nSuccessfully connected AsyncClient1\n")
            success = True
    
    if success == False:
        print("\n________Still couldn't connect AsyncClient1___________")
        raise Exception

    socketManager = BinanceSocketManager(asyncClient1)
    klineSocket = socketManager.trade_socket(symbol=Settings.Symbol)
    startRecievingPricesTime = time()
    async with klineSocket as soc:
        while doingJob:
            if doingJob == False:
                await asyncClient1.close_connection()
                return
            time1 = time()
            result = await soc.recv()
            time2 = time()
            newPrice = float(result["p"])
            print("\nNew market price = {}".format(newPrice))
            priceChange = 0
            if inPosition and newPrice>enteringPrice:
                priceChange = round(((newPrice-enteringPrice)/enteringPrice)*100,3)
                print("+{}% from entering price".format(priceChange))
            elif inPosition and newPrice<enteringPrice:
                priceChange = round(((newPrice-enteringPrice)/enteringPrice)*100,3)
                print("{}% from entering price".format(priceChange))
            elif inPosition == True:
                print("0% from entering price\n")
            print("Strategy - Up\n\n----------" if strategy == 0 else "Strategy - Down\n\n----------")
            currentPrice = newPrice

            priceBrokeThrough = checkForPriceBreakThrough(newPrice)
            if priceBrokeThrough == True and doingJob:
                if takeProfit!=None:
                    status = checkTakeProfitStatus()

                    if status != "FILLED" and forcedCloseOrder== None:
                        exceptions.append("Price went through takeProfit")
                        print("_______Price went through takeProfit!!!________")
                        if closeMainOrder() == False:
                            print("\n_____Couldn't close {} base asset_____\n".format("sell" if strategy == 0 else "buy" ))
                            print("Need to {} manually\n".format("sell" if strategy == 0 else "buy"))
                            exit()
                        await closeConnection()
                        break
                    else:
                        if strategy == 1 and doingJob:
                            repayLoan()
                        await closeConnection()
                        await asyncClient1.close_connection()
                        print("\nAsyncClient1 has successfully been closed\n ")
                        return
                else:
                    status = checkStopLossStatus()

                    if status != "FILLED" and forcedCloseOrder== None:
                        exceptions.append("Price went through stopLoss")
                        print("_______Price went through stopLoss!!!________")
                        if closeMainOrder() == False:
                            print("\n_____Couldn't {} base asset_____\n".format("sell" if strategy == 0 else "buy"))
                            print("Need to {} manually\n".format("sell" if strategy == 0 else "buy"))
                            exit()
                        await closeConnection()
                        break
                    else:
                        if strategy == 1 and doingJob:
                            repayLoan()
                        await closeConnection()
                        await asyncClient1.close_connection()
                        print("\nAsyncClient1 has successfully been closed\n ")
                        return
            if doingJob == False:
                await asyncClient1.close_connection()
                return
            try:
                analyzePriceAndCurrentPosition()
            except Exception as ex:
                print(ex) 
                print("Something went wrong when analyzing price")
                exceptions.append(ex)
                if forcedClosure ==False:
                    closeMainOrder()
                await closeConnection()
                await asyncClient1.close_connection()
                print("\nAsyncClient1 has successfully been closed\n ")
                return

            if checkForStuckPrice(timeChange=(time2-time1),priceChange=priceChange) or checkForOverstayInDeal(startTime = startRecievingPricesTime, priceChange = priceChange):
                closeMainOrder(cancelAllorders=True)
                await closeConnection()
                await asyncClient1.close_connection()
                print("\nAsyncClient1 has successfully been closed\n ")

    await asyncClient1.close_connection()
    print("\nAsyncClient1 has successfully been closed\n ")

def analyzePriceAndCurrentPosition():
    global mainOrder
    global stopLoss
    global inPosition
    global followingStopLoss
    global highestRichedPrice
    global lowestRichedPrice
    global enteringPrice
    global takeProfitPrice
    global stopLossPrice
    global takeProfit
    global startedFollowing
    global quantityInBase
    global quantityInQoute
    global exceptions
    global trailingTakeProfitSet

    if inPosition == True and doingJob == True and strategy == 0:
        if currentPrice>(takeProfitPrice+Settings.SafeDealRangeAmount) and takeProfit == None and currentPrice < (takeProfitPrice+Settings.AmountNotToMakeStopOrderExecuteInstantly+Settings.SafeDealRangeAmount):
            try:
                print("\nTrying to cancel stopLoss..........")
                client.cancel_order(symbol = Settings.Symbol, orderId = stopLoss["orderId"])
            except Exception as ex:    
                exceptions.append("Couldn't cancel buttom stop-loss because of")     
                exceptions.append(ex)
                print("___________Couldn't cancel buttom stop-loss___________")
                print(ex)
                return
            else: 
                print("\nSuccessfully canceled stop loss!\n")
 
                
            attempt = 0
            success = False
            while attempt<3 and success == False:
                try: 
                    print("Trying to place takeProfit.......")
                    takeProfit = client.create_order(
                        symbol = Settings.Symbol, 
                        side=enums.SIDE_SELL,
                        type=enums.ORDER_TYPE_STOP_LOSS_LIMIT, 
                        timeInForce =enums.TIME_IN_FORCE_FOK, 
                        quantity = quantityInBaseToSell,
                        price = takeProfitPrice,
                        stopPrice = round((takeProfitPrice+Settings.SafeDealRangeAmount),Settings.TickPriceRounding),
                        newOrderRespType = enums.ORDER_RESP_TYPE_FULL)
                except Exception as ex:
                    exceptions.append("Couldn't place take profit instantly because of")
                    exceptions.append(ex)
                    print("_____________Something went wrong when trying to place takeProfit______________")
                    print(ex)
                    attempt += 1 
                else:
                    print("Have successfully placed takeProfit order!!!!")
                    success = True 
                    highestRichedPrice = currentPrice

            if success == False:
                result = closeMainOrder()
                if result == True:
                    print("Successfully closed main order and there are no active stopLosses or takeProtits")
                    raise Exception
                else:
                    exit()

        elif currentPrice >= (takeProfitPrice+Settings.SafeDealRangeAmount+Settings.AmountNotToMakeStopOrderExecuteInstantly) and doingJob == True:
            if highestRichedPrice == 0 or ((currentPrice-highestRichedPrice)/highestRichedPrice) >= Settings.SignificantChangeInHighestPriceInRelationPrevious:
                print("\n\nNew highest price was riched!!!")
                if highestRichedPrice == 0:
                    if closeStopLoss() != True:
                        return 
                elif takeProfit != None:
                    try:
                        client.cancel_order(symbol = Settings.Symbol,orderId = takeProfit["orderId"])
                    except Exception as ex:
                        exceptions.append("Couldn't cancel takeProfit and move it up because of")
                        exceptions.append(ex)
                        print("__________Couldn't cancel takeProfit and move it up!!!!!________")
                        print(ex)
                        return
                    else:
                        print("----------\nSuccessfully cancled previous take profit\n----------")

                try:
                    price = round((currentPrice-Settings.SafeDealRangeAmount-Settings.AmountNotToMakeStopOrderExecuteInstantly),Settings.TickPriceRounding)
                    stopPrice = round((currentPrice-Settings.AmountNotToMakeStopOrderExecuteInstantly),Settings.TickPriceRounding)
                    takeProfit = client.create_order(
                    symbol = Settings.Symbol, 
                    side=enums.SIDE_SELL,
                    type=enums.ORDER_TYPE_STOP_LOSS_LIMIT, 
                    timeInForce =enums.TIME_IN_FORCE_FOK, 
                    quantity = quantityInBaseToSell,
                    price = price,
                    stopPrice = stopPrice,
                    newOrderRespType = enums.ORDER_RESP_TYPE_FULL)
                except Exception as ex:
                    exceptions.append("Couldn't move TakeProfit because of")
                    exceptions.append(ex)
                    print("__________Couldn't move TakeProfit!!!!!__________")
                    print(ex)
                    result = closeMainOrder()
                    if result == True:
                        raise Exception
                    else:
                        print("\n_______There is an open order for UpStrategy that should be manually sold_______\n")
                        exit()
                else:
                    print("Successully moved take profit to {} with trigger at {}\n------------\n\n".format(price,stopPrice))
                    success = True
                    highestRichedPrice = currentPrice   


    elif inPosition == True and doingJob == True and strategy == 1:
        if currentPrice<=(takeProfitPrice-Settings.SafeDealRangeAmount) and takeProfit == None and currentPrice > (takeProfitPrice-Settings.SafeDealRangeAmount-Settings.AmountNotToMakeStopOrderExecuteInstantly):
            try:
                print("trying to cancel stop loss.......")
                client.cancel_margin_order(symbol = Settings.Symbol, isIsolated=isIsolated,orderId = stopLoss["orderId"] )
            except Exception as ex:
                exceptions.append("Couldn't cancel stop-loss because of")
                exceptions.append(ex)
                print("\n{}\n".format(ex))
                print(exc_info()[2])
                print("\n__________Couldn't cancel stop-loss___________")
                return
            else: 
                print("\nSuccessfully canceled stop loss!\n")

            try: 
                print("\nTrying to place take profit")
                takeProfit = client.create_margin_order(
                    symbol = Settings.Symbol, 
                    isIsolated = isIsolated,
                    side=enums.SIDE_BUY,
                    type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,  
                    quantity = quantityInBaseToBuy,
                    price = takeProfitPrice,
                    stopPrice = round(takeProfitPrice-Settings.SafeDealRangeAmount,Settings.TickPriceRounding),
                    newOrderRespType = enums.ORDER_RESP_TYPE_FULL,
                    timeInForce = enums.TIME_IN_FORCE_FOK)
            except Exception as ex:
                exceptions.append("Couldn't place take profit because of")
                exceptions.append(ex)
                print("\n{}\n".format(ex))
                print(exc_info()[2])
                print("_____________Something went wrong when trying to place takeProfit______________")
                closeMainOrder()
                raise ex
            else:
                print("Take profit was successfully placed\n")
                lowestRichedPrice = currentPrice
                #takeProfit = client.get_margin_order(symbol = Settings.Symbol, isIsolated = "True",orderId = takeProfit["orderId"])

        elif currentPrice <= (takeProfitPrice-Settings.SafeDealRangeAmount-Settings.AmountNotToMakeStopOrderExecuteInstantly):
            if  lowestRichedPrice == 0 or ((lowestRichedPrice - currentPrice)/lowestRichedPrice) >= Settings.SignificantChangeInHighestPriceInRelationPrevious:
                print("\nNew lowest price was riched!!!")
                if takeProfit != None:
                    try:
                        print("\nTrying to cancel takeProfit and later move it down\n")
                        client.cancel_margin_order(symbol = Settings.Symbol,isIsolated = isIsolated,orderId = takeProfit["orderId"])
                    except Exception as ex:
                        exceptions.append("Couldn't cancel takeProfit and move it down becuase of")
                        exceptions.append(ex)
                        print("__________Couldn't cancel takeProfit and move it down!!!!!________")
                        print(ex)
                        return
                    else:
                        print("\n----------\nSuccessfully cancled previous take profit\n----------")
                elif lowestRichedPrice == 0:
                    try:
                        print("trying to cancel stop loss.......")
                        client.cancel_margin_order(symbol = Settings.Symbol, isIsolated=isIsolated,orderId = stopLoss["orderId"] )
                    except Exception as ex:
                        exceptions.append("Couldn't cancel stop-loss becuase of")
                        exceptions.append(ex)
                        print("\n{}\n".format(ex))
                        print(exc_info()[2])
                        print("\n__________Couldn't cancel stop-loss___________")
                        return
                    else: 
                        print("\nSuccessfully canceled stop loss!\n")

                try:
                    takeProfit = client.create_margin_order(
                    symbol = Settings.Symbol, 
                    isIsolated = isIsolated,
                    side=enums.SIDE_BUY,
                    type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,  
                    quantity = quantityInBaseToBuy,
                    price = round((currentPrice+Settings.SafeDealRangeAmount+Settings.AmountNotToMakeStopOrderExecuteInstantly),Settings.TickPriceRounding),
                    stopPrice = round((currentPrice+Settings.AmountNotToMakeStopOrderExecuteInstantly),Settings.TickPriceRounding),
                    newOrderRespType = enums.ORDER_RESP_TYPE_FULL,
                    timeInForce = enums.TIME_IN_FORCE_FOK)
                except Exception as ex:
                    exceptions.append("Couldn't move down/place takeProfit because of")
                    exceptions.append(ex)
                    print("\n{}\n".format(ex))
                    print(exc_info()[2])
                    print("__________Couldn't move down/place takeProfit !!!!________")
                    print("Need to urgently close the deal!!!!!!!!!!!")
                    closeMainOrder()
                    raise ex
                else:
                    print("Successully moved take profit to {}\n------------\n\n".format(takeProfit['price']))
                    lowestRichedPrice = currentPrice
                    #takeProfit = client.get_margin_order(symbol = Settings.Symbol, isIsolated = "True",orderId = takeProfit["orderId"])
           
def borrowFunds():
    try:
        borrowOrder = client.create_margin_loan(asset = Settings.BaseCurrency, amount = "{}".format(quantityInBase), isIsolated = isIsolated, symbol = Settings.Symbol)  
    except exc.BinanceAPIException as ex:
        exceptions.append("Couldn't borrow funds")
        print("___________Something went wrong when borrowing {}__________".format(Settings.BaseCurrency))
        print("\n{}\n".format(ex))
        raise ex
    except Exception as ex:
        exceptions.append("Couldn't borrow funds")
        print("___________Something went wrong when borrowing {}__________".format(Settings.BaseCurrency))
        print("\n{}\n".format(ex))
        print(exc_info()[2])
        return False
    else:      
        print("----------\nBorrowed {}{}\n----------".format(quantityInBase,Settings.BaseCurrency))
        return True

def repayLoan():
    global repayed 
    if repayed == False:
        success = False 
        attempt = 0 
        while success == False and attempt < 3:
            try:    
                print("\nTrying to pay the loan back\n")
                amountToRepay = math.ceil(((quantityInBase+quantityInBase*Settings.BorrowComissionRate))*pow(10,Settings.BaseCurrencyMinAmountRounding))/pow(10,Settings.BaseCurrencyMinAmountRounding)
                repayLoanOrder = client.repay_margin_loan(asset=Settings.BaseCurrency, amount='{}'.format(amountToRepay), isIsolated = isIsolated, symbol = Settings.Symbol)
            except Exception as ex:
                print(ex)
                print("______Couldn't instantly repay the loan!!!!!________")
                attempt+=1
            else:
                print("Successfully payed the loan back!!!\n")
                repayed = True 
                return True
        if success == False:
            print("______Should repay manually!!!!!______")
            exit()

def executeMainOrder():
    global enteringPrice
    global quantityInQoute
    global stopLossPrice
    global takeProfitPrice
    global exceptions
    global quantityInBase
    global quantityInBaseToSell
    global quantityInBaseToBuy 

    rate = getCurrentExchangeRate(Settings.Symbol)
    if rate == None:
        return False
    quantityInBase = round((Settings.TradingAmountInQuote/rate), Settings.BaseCurrencyMinAmountRounding)

    if strategy == 1: 
        if borrowFunds() == False:
            return False
        quantityInBaseToBuy = math.ceil(((quantityInBase+quantityInBase*Settings.BorrowComissionRate)/(1-Settings.FeeRate))*pow(10,Settings.BaseCurrencyMinAmountRounding))/pow(10,Settings.BaseCurrencyMinAmountRounding)
        print("\nQuantity in Base to buy = {}\n".format(quantityInBaseToBuy))

    if placeMainOrder() == True:
        success = False 
        while success == False:
            try:
                if strategy == 0:
                    mainOrderInfo = client.get_order(symbol = Settings.Symbol, orderId = mainOrder['orderId'])
                else:
                    mainOrderInfo = client.get_margin_order(symbol = Settings.Symbol, isIsolated = isIsolated, orderId = mainOrder["orderId"])
            except Exception as ex:
                exceptions.append("Couldn't get Main Order Info")
                print(ex)
                print("\n_______Couldn't get Main Order Info_______\n")
                continue

            print("Main Order Status: {}".format(mainOrderInfo['status']))
            if mainOrderInfo['status'] == "FILLED":
                enteringPrice = float(mainOrderInfo['cummulativeQuoteQty'])/float(mainOrderInfo['executedQty'])
                print("\n------------\nMain order average fill price = {}\n".format(enteringPrice))
                print("Main order amount in base = {}\n------------\n".format(mainOrderInfo['executedQty']))
                quantityInQoute = quantityInBase*enteringPrice
                if strategy == 0:
                    takeProfitPrice = round((enteringPrice*(1+Settings.ProfitDealRange)),Settings.TickPriceRounding)
                    print("\nTake profit price = {}, Take profit trigger price = {}\n".format(takeProfitPrice, round(takeProfitPrice+Settings.SafeDealRangeAmount,Settings.TickPriceRounding)))
                    stopLossPrice = round((enteringPrice*(1-Settings.LossDealRange)),Settings.TickPriceRounding)
                    print("Stop loss price = {}, Stop Price = {}\n".format(stopLossPrice,round(stopLossPrice + Settings.SafeDealRangeAmount,Settings.TickPriceRounding)))
                    executedQty = float(mainOrderInfo['executedQty'])
                    quantityInBaseToSell = math.floor((executedQty-executedQty*0.001)*pow(10,Settings.BaseCurrencyMinAmountRounding))/pow(10,Settings.BaseCurrencyMinAmountRounding)
                    print("\nQuantity in Base to sell = {}".format(quantityInBaseToSell))
                else:
                    takeProfitPrice = round((enteringPrice*(1-Settings.ProfitDealRange)),Settings.TickPriceRounding)
                    print("\nTake profit price = {}, Take profit trigger price = {}\n".format(takeProfitPrice,round(takeProfitPrice-Settings.SafeDealRangeAmount,Settings.TickPriceRounding)))
                    stopLossPrice = round((enteringPrice*(1+Settings.LossDealRange)),Settings.TickPriceRounding)
                    print("Stop loss price = {}, Stop Price = {}\n".format(stopLossPrice,(round(stopLossPrice-Settings.SafeDealRangeAmount,Settings.TickPriceRounding))))
                return True
            elif mainOrderInfo['status'] == "EXPIRED":
                print("\n_________WTF MZF__________\n")
                print("Main order status: EXPIRED\n")
                closeAllOpenOrders()
                exit()
            elif mainOrderInfo['status'] == "CANCELED":
                print("\n______Something weird is going on with main order status________\n")
                closeAllOpenOrders()
                exit()
            else:
                pass

    else:
        print("\n_____Main order hasn't been executed!!______\n")
        exceptions.append("Main order hasn't been executed!!")
        return False

def placeMainOrder():
    global mainOrder
    try:
        if strategy == 0:
            mainOrder = client.order_market_buy(symbol = Settings.Symbol, quantity = quantityInBase)
        else:
            mainOrder = client.create_margin_order(
                symbol = Settings.Symbol, 
                isIsolated = isIsolated,
                side=enums.SIDE_SELL,
                type=enums.ORDER_TYPE_MARKET, 
                quantity = quantityInBase,      
                newOrderRespType = enums.ORDER_RESP_TYPE_FULL)
    except Exception as ex:
        exceptions.append("Couldn't put main order because of")
        exceptions.append(ex)
        print(ex)
        print("\n_____Couldn't put main order______\n")
        return False
    else:
        print("\nMain order has been put successfully!!!\n")
        return True 

def closeMainOrder(cancelAllorders = False):
    global forcedCloseOrder
    global forcedClosure
    global exceptions
    if cancelAllorders == True:
        closeAllOpenOrders()

    print("\nTrying to close main order...\n")
    while True:
        try:
            if strategy == 0:
                forcedCloseOrder = client.order_market_sell(symbol = Settings.Symbol, quantity = round(quantityInBaseToSell,Settings.TickPriceRounding))
            else:
                forcedCloseOrder = client.create_margin_order(
                    symbol = Settings.Symbol, 
                    isIsolated = isIsolated,
                    side=enums.SIDE_BUY,
                    type=enums.ORDER_TYPE_MARKET, 
                    quantity = round(quantityInBaseToBuy,Settings.BaseCurrencyMinAmountRounding),
                    newOrderRespType = enums.ORDER_RESP_TYPE_FULL)
                if repayLoan() == False:
                    raise Exception
        except Exception as ex:
            exceptions.append("Couldn't close the main order because of")
            exceptions.append(ex)
            print("\n"+str(ex))
            print("\nCouldn't close the main order\nSymbol = {}; QuantityInBase = {};".format(Settings.Symbol,(quantityInBaseToSell if strategy == 0 else quantityInBaseToBuy)))
            if getForcedCloseOrderStatus() != "FILLED":
                continue
            else:
                print("\nForced Close was executed even though the error occured when were placing the order.\n")
                forcedClosure = True
                return True
        else:
            print("\nSuccessfully closed MainOrder\n")
            forcedClosure = True
            return True

def checkMainOrder():
    status = None
    success = False
    attempt = 0 
    while attempt < 3 and success == False:
        try:
            if strategy == 0:
                order = client.get_order(symbol = Settings.Symbol, orderId = mainOrder['orderId'])
            else:
                order = client.get_margin_order(symbol = Settings.Symbol,isIsolated =isIsolated, orderId = mainOrder['orderId'])
        except Exception as ex:
            print("\n"+str(ex))
            print("_________Couldn't instantly get main order status__________")
            attempt += 1 
        else:
            success = True
    if success == False:
        print("\n________Couldn't get main order status for 3 times!!!\n")
        return None        
        
    status = order['status']
    print("\nMain order status: {}\n".format(status))
    return status

def checkTakeProfitStatus():
    status = None 
    if strategy ==0:
        order = client.get_order(symbol = Settings.Symbol, orderId = takeProfit['orderId'])
    else:
        order = client.get_margin_order(symbol = Settings.Symbol,isIsolated = isIsolated, orderId = takeProfit['orderId'])
    status = order['status']
    print("\nTakeProfit order status: {}\n".format(status))
    return status

def cancelTakeProfit():
    global exceptions
    global takeProfit
    try: 
        client.cancel_order(symbol = Settings.Symbol, orderId = takeProfit["orderId"])
        takeProfit = None
    except Exception as ex:
        exceptions.append("Couldn't cancel take profit")
        print(ex)
        print("\n_____Couldn't cancel take profit_____\n")
        return False
    else:
        print("\nSuccessfully canceled take profit\n")
        return True 

def placeStopLossOrder():
    global stopLoss
    global inPosition
    try:
        if strategy ==0:
            stopLoss = client.create_order(
                symbol = Settings.Symbol, 
                side=enums.SIDE_SELL,
                type=enums.ORDER_TYPE_STOP_LOSS_LIMIT, 
                timeInForce =enums.TIME_IN_FORCE_FOK, 
                quantity = quantityInBaseToSell,
                price = stopLossPrice,
                stopPrice = round(stopLossPrice + Settings.SafeDealRangeAmount,Settings.TickPriceRounding),
                newOrderRespType = enums.ORDER_RESP_TYPE_FULL)
        else:
            stopLoss = client.create_margin_order(
                symbol = Settings.Symbol, 
                isIsolated = isIsolated,
                side=enums.SIDE_BUY,
                type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,  
                timeInForce = enums.TIME_IN_FORCE_FOK,
                quantity = quantityInBaseToBuy,
                price = stopLossPrice,
                stopPrice = round(stopLossPrice-Settings.SafeDealRangeAmount,Settings.TickPriceRounding),
                newOrderRespType = enums.ORDER_RESP_TYPE_FULL)
    except Exception as ex:
        exceptions.append("Couln't create stop loss because of")
        exceptions.append(ex)
        print("\n_____________Something went wrong when creating stop loss_______________")
        print("Error message:"+ex.message)
        closeMainOrder()
        return False
    else:
        print("\nSuccesfully put stopLoss with price = {} and stopPrice = {}!!!\n".format(stopLossPrice, (round(stopLossPrice + Settings.SafeDealRangeAmount,Settings.TickPriceRounding) if strategy == 0 else round(stopLossPrice-Settings.SafeDealRangeAmount,Settings.TickPriceRounding) )))
        inPosition = True
        return True 

def checkStopLossStatus():
    status = None
    if strategy ==0:
        order = client.get_order(symbol = Settings.Symbol, orderId = stopLoss['orderId'])
    else:
        order = client.get_margin_order(symbol = Settings.Symbol,isIsolated =isIsolated, orderId = stopLoss['orderId'])
    status = order['status']
    print("\nStopLoss order status: {}\n".format(status))
    return status

def closeStopLoss():
    global exceptions
    attempt = 0
    success = False
    while attempt<3 and success != True:
        try:
            print("\nTrying to cancel stopLoss..........")
            if strategy == 0:
                client.cancel_order(symbol = Settings.Symbol, orderId = stopLoss["orderId"])
            else:
                client.cancel_margin_order(symbol = Settings.Symbol,isIsolated = isIsolated, orderId = stopLoss['orderId'])
        except Exception as ex:
            exceptions.append("Couldn't cancel stop-loss because of")
            exceptions.append(ex)
            print("___________Couldn't cancel stop-loss___________")
            print(ex)
            attempt+=1
        else: 
            print("Successfully canceled stop loss!\n")
            success = True
            return True

    if success == False:
        return False

def closeAllOpenOrders():
    print("\nClosing all open orders.")
    if strategy == 0:
        openOrders = client.get_open_orders(symbol = Settings.Symbol)
    else:
        openOrders = client.get_open_margin_orders(symbol = Settings.Symbol, isIsolated = isIsolated)

    for order in openOrders:
        if strategy == 0:
            client.cancel_order(symbol = Settings.Symbol, orderId = order["orderId"])
        else:
            client.cancel_margin_order(symbol = Settings.Symbol, isIsolated = isIsolated, orderId = order["orderId"])
    print("Successfully closed all open orders.\n")

def checkForPriceBreakThrough(currentPrice):
    if takeProfit != None:
        if strategy == 0:
            if float(takeProfit['price'])-Settings.StopLossTakeProfitPassedByCheckAmount >= currentPrice:
                return True
            else:
                return False
        else:
            if float(takeProfit['price'])+Settings.StopLossTakeProfitPassedByCheckAmount <= currentPrice:
                return True
            else:
                return False
    elif stopLoss != None:
        if strategy == 0:
            if float(stopLoss["price"])-Settings.StopLossTakeProfitPassedByCheckAmount >= currentPrice:
                return True
            else:
                return False
        else:
            if float(stopLoss["price"])+Settings.StopLossTakeProfitPassedByCheckAmount <= currentPrice:
                return True
            else:
                return False
    else:
        return False

def checkForStuckPrice(timeChange, priceChange = 0):
    if timeChange>Settings.StuckPriceTimeout and priceChange == 0:
        exceptions.append("The price has stuck")
        print("\n______The price has stuck_______\n")
        return True
    else:
        return False         

def checkForOverstayInDeal(startTime, priceChange):
    global exceptions
    currentTime = time()
    print(f"\nTime Passed = {currentTime-startTime};\n\n----------")
    if (currentTime - startTime) >Config.FirstOverstayInDealTimeout and ((priceChange>0.2) if strategy == 0 else (priceChange<-0.2)):
        exceptions.append(f"Staying in the deal for more than {Config.FirstOverstayInDealTimeout} seconds")
        print(f"\n_______Staying in the deal for more than {Config.FirstOverstayInDealTimeout} seconds_______\n")
        return True
    elif (currentTime - startTime) >Config.SecondOverstayInDealTimeout:
        exceptions.append(f"Staying in the deal for more than {Config.SecondOverstayInDealTimeout} seconds")
        print(f"\n_______Staying in the deal for more than {Config.SecondOverstayInDealTimeout} seconds_______\n")
        return True
    else:
        return False

async def gettingCurrentOrderInfo():
    print("We are in gettingCurrentOrderInfo():")
    global openOrders
    global doingJob
    global takeProfit
    global exceptions
    circleCounter = 0
    attempt = 0 
    success = False
    try:
        asyncClient2 = await AsyncClient.create(api_key = Settings.API_KEY, api_secret = Settings.API_SECRET)
    except Exception as ex:
        exceptions.append("Couldn't connect AsyncClient2 because of")
        exceptions.append(ex)
        print("\n_____A problem occured while trying to connect AsyncClient2_____")
        attempt +=1
    else:
        print("\nSuccessfully connected AsyncClient2\n")
        success = True
    
    if success == False:
        print("\n\n_______Couldn't connect asyncClient2________\n\n")
        if mainOrder == None:

            await closeConnection()
        else:
            status = checkMainOrder()
            if status == "FILLED":
                if closeMainOrder == True:
                    await closeConnection()
                else:
                    exit()
            else:
                await closeConnection()

    while doingJob:

        if takeProfit != None:
            success = False 
            attempt = 0
            order = None
            while success != True and attempt<3:
                try:
                    if strategy == 0:
                        order = await asyncClient2.get_order(symbol=Settings.Symbol,orderId=takeProfit["orderId"])
                    else: 
                        order = await asyncClient2.get_margin_order(symbol=Settings.Symbol,isIsolated = isIsolated,orderId=takeProfit["orderId"])
                except Exception as ex:
                    exceptions.append("Couldn't instantly get take profit info because of")
                    exceptions.append(ex)
                    print("\n______Couldn't get take profit info_______\n")
                    print(ex)
                    attempt+=1
                else:
                    success = True
                    
            if success == False:
                continue 
            
            if order["status"] == "FILLED" and doingJob:
                print("\nTake profit has been filled!!!!!\n")
                if strategy == 1:
                    repayLoan()
                await closeConnection()
                break
            elif order['status'] == "EXPIRED" and forcedCloseOrder == None:
                print("Take profit status:{}".format(order['status']))
                
                exceptions.append("Take Profit Expired")
                if closeMainOrder() == False:
                    exit()
                await closeConnection()
                break
        elif stopLoss != None :
            success = False 
            attempt = 0 
            order = None
            while attempt <3 and success == False:
                try:
                    if strategy == 0:
                        order = await asyncClient2.get_order(symbol=Settings.Symbol,orderId=stopLoss["orderId"])
                    else:
                        order = await asyncClient2.get_margin_order(symbol=Settings.Symbol,isIsolated = isIsolated, orderId=stopLoss["orderId"])
                except Exception as ex:
                    exceptions.append("Couldn't instantly get stop loss info becuase of")
                    exceptions.append(ex)
                    print("_______Couldn't get stop loss info_______")
                    attempt +=1
                else:
                    success = True
                
            if success ==  False:
                continue
           
            if order["status"] == "FILLED":
                print("\nStopLoss status: {}".format(order['status']))
                print("\nStop loss has been filled!!!!!\n")
                if strategy == 1:
                    repayLoan()
                await closeConnection()
                break
            elif (order["status"] == "EXPIRED" or order["status"] == "CANCELED") and forcedCloseOrder == None:
                if takeProfit == None and forcedClosure == False:
                    print("\nStopLoss status: {}".format(order['status']))
                    exceptions.append("StopLoss has expired")
                    closeMainOrder()
                    await closeConnection()
                    break

        success = False
        attempt = 0
        while success ==False and attempt<3:
            try:
                if strategy ==0:
                    openOrders = await asyncClient2.get_open_orders(symbol = Settings.Symbol) 
                else:
                    openOrders = await asyncClient2.get_open_margin_orders(symbol = Settings.Symbol, isIsolated = isIsolated)
            except Exception as ex:
                exceptions.append("Couldn't recieve the open orders because of")
                exceptions.append(ex)
                print("______Couldn't recieve the open orders_______")
                attempt+=1
            else:
                success = True

        if success == False:
            closeMainOrder()
            await closeConnection()
            await asyncClient2.close_connection()
            print("AsyncClient2 has been closed")
            raise exc.BinanceRequestException
        
        if openOrders == [] and doingJob:
            if takeProfit != None and doingJob:
                status = checkTakeProfitStatus()
                if status == "FILLED":
                    if strategy ==1:
                        repayLoan()
                    await closeConnection()
                    break
                elif status == "EXPIRED":
                    closeMainOrder()
                    exceptions.append("Take Profit Expired")
                    await closeConnection()
                    break
                elif status == "NEW":
                    pass
            elif stopLoss != None and doingJob:
                status = checkStopLossStatus()
                if status == "FILLED":
                    if strategy == 1:
                        repayLoan()
                    await closeConnection()
                    break
                elif status == "EXPIRED":
                    closeMainOrder()
                    exceptions.append("Stop Loss Expired")
                    await closeConnection()
                    break
                elif status == "NEW":
                    pass
            elif mainOrder != None:
                print("\nNeither stopLoss nor takeProfit order has been put yet\n")
            else:
                print("\nMain order has not been put yet\n")
        if circleCounter >= 2:
            print("\nOpen Order Info:")
            for order in openOrders:
                print("------------")
                if((float(order["price"])>enteringPrice) if strategy == 0 else (float(order["price"])<enteringPrice)):
                    print("Take Profit:")
                else:
                    print("Stop Loss:")
                print(order)
            print("------------")
            print("")
            circleCounter = 0
        else:
            circleCounter+=1
        await asyncio.sleep(0.5)
    await asyncClient2.close_connection()
    print("\nAsyncClient2 has successully been closed\n")

def getCurrentExchangeRate(pair):
    try:
        info = client.get_ticker(symbol = pair)['lastPrice']
    except Exception as ex:
        exceptions.append("Couldn't recieve current exchange")
        print(ex)
        print("\n_____Couldn't recieve current exchange for {}\n".format(pair))
        return None
    else:
        print("\nCurrent exchange for {} = {}\n".format(pair, info ))
        return float(info)

def getSpread(symbol):
    try:
        info = client.get_orderbook_ticker(symbol = symbol)
        spread = round((float(info['askPrice'])-float(info['bidPrice'])),Settings.TickPriceRounding)
    except Exception as ex:
        print(ex)
        print(f"\n_________Couldn't get {symbol} spread_________\n")
        return -1 
    else:
        print(f"\nSpread = {spread:.8f}")
        return spread

def getForcedCloseOrderStatus():
    try:
        status = None
        if strategy ==0:
            order = client.get_order(symbol = Settings.Symbol, orderId = forcedCloseOrder['orderId'])
        else:
            order = client.get_margin_order(symbol = Settings.Symbol,isIsolated =isIsolated, orderId = forcedCloseOrder['orderId'])
        status = order['status']
        print("\nForced Close order status: {}\n".format(status))
        return status
    except Exception as ex:
        print("\n"+str(ex))
        print("\n_________Couldn't get forced closure status!!! Likely because it wasn't placed__________\n")
        return None

def printLastPrices(symbol): 
    try:
        info = client.get_symbol_ticker(symbol = symbol)
        print("\nPrice for {} = {}\n".format(symbol, info['price']))
    except Exception as ex:
        print(ex)
        print("Couldn't get last price for {}".format(symbol))

def restoreGlobals():
    global currentPrice 
    global highestRichedPrice 
    global lowestRichedPrice
    global takeProfitPrice 
    global stopLossPrice 
    global enteringPrice 
    global openOrders 
    global doingJob 
    global client 
    global inPosition 
    global quantityInBase 
    global quantityInBaseToSell
    global quantityInBaseToBuy
    global mainOrder 
    global stopLoss 
    global followingStopLoss 
    global takeProfit 
    global startedFollowing 
    global issue
    global forcedClosure
    global forcedCloseOrder
    global exceptions
    global quantityInQoute 
    global strategy
    global trailingTakeProfitSet
    global repayed
    global Settings
    global isIsolated
    trailingTakeProfitSet = False
    currentPrice = 0
    highestRichedPrice = 0
    lowestRichedPrice = 0 
    takeProfitPrice = 0 
    stopLossPrice = 0
    enteringPrice = 0
    openOrders = {}
    doingJob = True
    client = None
    inPosition = False
    quantityInBase = 0
    mainOrder = None
    stopLoss = None 
    followingStopLoss = None
    takeProfit = None
    startedFollowing = False
    issue = Issue.NoIssue
    forcedClosure = False
    forcedCloseOrder = None
    exceptions = []
    quantityInQoute = 0
    quantityInBaseToSell = 0
    quantityInBaseToBuy = 0 
    strategy = 0
    repayed = False
    Settings = None
    isIsolated = "TRUE"

async def closeConnection():
    print("\nWe are in closeConnection():\n")
    closeAllOpenOrders()
    global doingJob
    doingJob = False
    printLastPrices(symbol = Settings.Symbol)
    await asyncio.sleep(2)
    printLastPrices(symbol = Settings.Symbol)

async def spaceDivider():
    while doingJob:
        print(".")
        await asyncio.sleep(0.5)

async def main(mainClient,config, strat = 0, isolated = True):
    restoreGlobals()
    global client 
    global exceptions
    global strategy
    global Settings
    global isIsolated
    Settings = config
    strategy = strat
    returnDict = {
    "mainOrderId":0,
    "tradingAmountInBase":0,
    "tradingAmountInQuote":0,
    "enteredPrice":0,
    "stopLossPrice":0,
    "takeProfitPrice":0,
    "closedPrice":0,
    "closedBy":0,
    "updatedSpread":0,
    "issues": exceptions
    }    
    isIsolated = "TRUE" if isolated == True else "FALSE"
    print("We are in main(mainClient):")
    client = mainClient
    check1 = False
    check2 = False
    check3 = False
    currentSpread = round(getSpread(symbol=Settings.Symbol),Settings.TickPriceRounding)
    returnDict['updatedSpread'] = currentSpread
    if currentSpread == -1:
        exceptions.append("Couldn't get the spread")
        print("\n___________Couldn't get the spred___________\n")
        return returnDict              
    if currentSpread > (Settings.InitialSpread)*config.MaxIncreaseInSpreadMultiplier:
        exceptions.append(f"Spread has increased to {currentSpread:.8f} from {Settings.InitialSpread:.8f}")
        print(f"\n___________Spread has increased to {currentSpread:.8f} from {Settings.InitialSpread:.8f}____________\n\n")
        return returnDict        
    check1 = executeMainOrder()
    print(f"\nSpread has increased by {currentSpread/Settings.InitialSpread}\n")
    #print("\nTime taken to execute main order = {}\n".format(time2-time1))
    if check1 == False:
        printLastPrices(symbol = Settings.Symbol)
        return returnDict

    check2 = placeStopLossOrder()
    #print("\nTime taken to execute stop loss = {}\n".format(time2-time1))
    try: 
        if check1 and check2:
            task1 = asyncio.create_task(getCurrentPrice())
            task2 = asyncio.create_task(gettingCurrentOrderInfo())
            #task3 = asyncio.create_task(spaceDivider())
            await task1 
            await task2
    except Exception as ex:
        exceptions.append(ex)
        print(exc_info()[2])
        print(ex)
        closeMainOrder(cancelAllorders=True)
    finally:
        closeAllOpenOrders()

    closedPrice = 0
    closedBy = ""
    if forcedClosure == True:
        if strategy == 0:
            info = client.get_order(symbol = Settings.Symbol, orderId = forcedCloseOrder["orderId"])
        else:
            info = client.get_margin_order(symbol = Settings.Symbol,isIsolated =isIsolated, orderId = forcedCloseOrder["orderId"])
        closedPrice = float(info['cummulativeQuoteQty'])/float(info['executedQty'])
        closedBy = "Forced Closure"
    elif takeProfit != None:
        if strategy == 0:
            info = client.get_order(symbol = Settings.Symbol, orderId = takeProfit["orderId"])
        else:
            info = client.get_margin_order(symbol = Settings.Symbol, isIsolated =isIsolated, orderId = takeProfit["orderId"])
        closedPrice = float(info['cummulativeQuoteQty'])/float(info['executedQty'])
        closedBy = "Take Profit"
    elif stopLoss != None:
        if strategy == 0:
            info = client.get_order(symbol = Settings.Symbol, orderId = stopLoss["orderId"])
        else:
            info = client.get_margin_order(symbol = Settings.Symbol,isIsolated = isIsolated, orderId = stopLoss["orderId"])
        if float(info['executedQty']) == 0:
            closedPrice = 0
        else:
            closedPrice = float(info['cummulativeQuoteQty'])/float(info['executedQty'])
            closedBy = "Stop Loss"
    else:
        closedPrice = 0
    
    if closedPrice == 0:
        if strategy == 0:
            info = client.get_order(symbol = Settings.Symbol, orderId = trailingTakeProfit["orderId"])
        else:
            info = client.get_margin_order(symbol = Settings.Symbol,isIsolated = isIsolated, orderId = trailingTakeProfit["orderId"])
        closedPrice = float(info['cummulativeQuoteQty'])/float(info['executedQty'])
        closedBy = "Traililng Take Profit"


    if mainOrder == None:
        mainOrderId = 0
    else:
        mainOrderId = mainOrder['orderId']
        returnDict['mainOrderId'] = mainOrderId 
        returnDict['tradingAmountInBase'] = quantityInBase 
        returnDict['tradingAmountInQuote'] = quantityInQoute 
        returnDict['enteringPrice'] = enteringPrice 
        returnDict['stopLossPrice'] = stopLossPrice
        returnDict['takeProfitPrice'] = takeProfitPrice
        returnDict['closedPrice'] = closedPrice
        returnDict['closedBy'] = closedBy
        returnDict['exceptions'] = exceptions
    print("\n================")
    print("The deal is done!")
    print("================\n")
    return returnDict

if __name__ == "__main__":
    config = Config()
    client = Client(config.API_KEY,config.API_SECRET)
    config.setSymbol("IOTXUSDT")
    asyncio.run(main(mainClient=client,config=config, strat = 1, isolated=False))
    

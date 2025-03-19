import asyncio
import logging
import math
from enum import Enum
from time import time

from binance import AsyncClient, BinanceSocketManager, enums
from binance import exceptions as exc
from binance.client import Client

from config import Config


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
strategy = 0
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
    while not success and attempt < 3:
        try:
            asyncClient1 = await AsyncClient.create()
        except Exception as e:
            exceptions.append("Couldn't create AsyncClient1")
            logging.error(e)
            attempt += 1
        else:
            logging.info("Successfully connected AsyncClient1")
            success = True
    if not success:
        logging.error("Couldn't connect AsyncClient1 after retries")
        raise Exception
    socketManager = BinanceSocketManager(asyncClient1)
    klineSocket = socketManager.trade_socket(symbol=Settings.Symbol)
    startRecievingPricesTime = time()
    async with klineSocket as soc:
        while doingJob:
            if not doingJob:
                await asyncClient1.close_connection()
                return
            time1 = time()
            result = await soc.recv()
            time2 = time()
            newPrice = float(result["p"])
            logging.info(f"New market price = {newPrice}")
            priceChange = 0
            if inPosition and newPrice > enteringPrice:
                priceChange = round(
                    ((newPrice - enteringPrice) / enteringPrice) * 100, 3
                )
                logging.info(f"+{priceChange}% from entering price")
            elif inPosition and newPrice < enteringPrice:
                priceChange = round(
                    ((newPrice - enteringPrice) / enteringPrice) * 100, 3
                )
                logging.info(f"{priceChange}% from entering price")
            elif inPosition:
                logging.info("0% from entering price")
            logging.info("Strategy - Up" if strategy == 0 else "Strategy - Down")
            currentPrice = newPrice
            priceBrokeThrough = checkForPriceBreakThrough(newPrice)
            if priceBrokeThrough and doingJob:
                if takeProfit is not None:
                    status = checkTakeProfitStatus()
                    if status != "FILLED" and forcedCloseOrder is None:
                        exceptions.append("Price went through takeProfit")
                        logging.warning("Price went through takeProfit")
                        if not closeMainOrder():
                            logging.error(
                                "Couldn't close base asset for a buy->sell flow"
                            )
                            raise SystemExit
                        await closeConnection()
                        break
                    else:
                        if strategy == 1 and doingJob:
                            repayLoan()
                        await closeConnection()
                        await asyncClient1.close_connection()
                        return
                else:
                    status = checkStopLossStatus()
                    if status != "FILLED" and forcedCloseOrder is None:
                        exceptions.append("Price went through stopLoss")
                        logging.warning("Price went through stopLoss")
                        if not closeMainOrder():
                            logging.error(
                                "Couldn't close base asset for a buy->sell flow"
                            )
                            raise SystemExit
                        await closeConnection()
                        break
                    else:
                        if strategy == 1 and doingJob:
                            repayLoan()
                        await closeConnection()
                        await asyncClient1.close_connection()
                        return
            if not doingJob:
                await asyncClient1.close_connection()
                return
            try:
                analyzePriceAndCurrentPosition()
            except Exception as e:
                logging.error(e)
                exceptions.append(e)
                if not forcedClosure:
                    closeMainOrder()
                await closeConnection()
                await asyncClient1.close_connection()
                return
            if checkForStuckPrice(time2 - time1, priceChange) or checkForOverstayInDeal(
                startRecievingPricesTime, priceChange
            ):
                closeMainOrder(cancelAllorders=True)
                await closeConnection()
                await asyncClient1.close_connection()
    await asyncClient1.close_connection()


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
    if inPosition and doingJob and strategy == 0:
        if (
            currentPrice > (takeProfitPrice + Settings.SafeDealRangeAmount)
            and takeProfit is None
            and currentPrice
            < (
                takeProfitPrice
                + Settings.AmountNotToMakeStopOrderExecuteInstantly
                + Settings.SafeDealRangeAmount
            )
        ):
            try:
                logging.info("Trying to cancel stopLoss")
                client.cancel_order(symbol=Settings.Symbol, orderId=stopLoss["orderId"])
            except Exception as e:
                exceptions.append("Couldn't cancel buttom stop-loss")
                exceptions.append(e)
                logging.error("Couldn't cancel stop-loss")
                return
            attempt = 0
            success = False
            while attempt < 3 and not success:
                try:
                    logging.info("Trying to place takeProfit")
                    tp_price = takeProfitPrice
                    tp_stop = round(
                        takeProfitPrice + Settings.SafeDealRangeAmount,
                        Settings.TickPriceRounding,
                    )
                    takeProfit_order = client.create_order(
                        symbol=Settings.Symbol,
                        side=enums.SIDE_SELL,
                        type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                        timeInForce=enums.TIME_IN_FORCE_FOK,
                        quantity=quantityInBaseToSell,
                        price=tp_price,
                        stopPrice=tp_stop,
                        newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                    )
                    takeProfit = takeProfit_order
                except Exception as e2:
                    exceptions.append("Couldn't place take profit instantly")
                    exceptions.append(e2)
                    logging.error(e2)
                    attempt += 1
                else:
                    logging.info("Placed takeProfit order")
                    success = True
                    highestRichedPrice = currentPrice
            if not success:
                result = closeMainOrder()
                if result:
                    logging.info("Closed main order due to failed takeProfit placement")
                    raise Exception
                else:
                    raise SystemExit
        elif currentPrice >= (
            takeProfitPrice
            + Settings.SafeDealRangeAmount
            + Settings.AmountNotToMakeStopOrderExecuteInstantly
        ):
            if (
                highestRichedPrice == 0
                or ((currentPrice - highestRichedPrice) / highestRichedPrice)
                >= Settings.SignificantChangeInHighestPriceInRelationPrevious
            ):
                logging.info("New highest price reached")
                if highestRichedPrice == 0:
                    if not closeStopLoss():
                        return
                elif takeProfit is not None:
                    try:
                        client.cancel_order(
                            symbol=Settings.Symbol, orderId=takeProfit["orderId"]
                        )
                    except Exception as e:
                        exceptions.append("Couldn't cancel takeProfit and move it up")
                        exceptions.append(e)
                        logging.error("Couldn't cancel/adjust takeProfit")
                        return
                    logging.info("Canceled previous take profit")
                try:
                    price = round(
                        (
                            currentPrice
                            - Settings.SafeDealRangeAmount
                            - Settings.AmountNotToMakeStopOrderExecuteInstantly
                        ),
                        Settings.TickPriceRounding,
                    )
                    stop_price = round(
                        (
                            currentPrice
                            - Settings.AmountNotToMakeStopOrderExecuteInstantly
                        ),
                        Settings.TickPriceRounding,
                    )
                    takeProfit_order = client.create_order(
                        symbol=Settings.Symbol,
                        side=enums.SIDE_SELL,
                        type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                        timeInForce=enums.TIME_IN_FORCE_FOK,
                        quantity=quantityInBaseToSell,
                        price=price,
                        stopPrice=stop_price,
                        newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                    )
                    takeProfit = takeProfit_order
                except Exception as e:
                    exceptions.append("Couldn't move TakeProfit up")
                    exceptions.append(e)
                    logging.error("Couldn't move TakeProfit up")
                    result = closeMainOrder()
                    if result:
                        raise Exception
                    else:
                        logging.error("Manually sell required for UpStrategy")
                        raise SystemExit
                logging.info("Moved take profit up")
                highestRichedPrice = currentPrice
    elif inPosition and doingJob and strategy == 1:
        if (
            currentPrice <= (takeProfitPrice - Settings.SafeDealRangeAmount)
            and takeProfit is None
            and currentPrice
            > (
                takeProfitPrice
                - Settings.SafeDealRangeAmount
                - Settings.AmountNotToMakeStopOrderExecuteInstantly
            )
        ):
            try:
                logging.info("Cancel stop loss for short strategy")
                client.cancel_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=isIsolated,
                    orderId=stopLoss["orderId"],
                )
            except Exception as e:
                exceptions.append("Couldn't cancel stop-loss for short strategy")
                exceptions.append(e)
                logging.error(e)
                return
            logging.info("Canceled stop loss")
            try:
                tp_order = client.create_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=isIsolated,
                    side=enums.SIDE_BUY,
                    type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                    quantity=quantityInBaseToBuy,
                    price=takeProfitPrice,
                    stopPrice=round(
                        takeProfitPrice - Settings.SafeDealRangeAmount,
                        Settings.TickPriceRounding,
                    ),
                    newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                    timeInForce=enums.TIME_IN_FORCE_FOK,
                )
                takeProfit = tp_order
            except Exception as e:
                exceptions.append("Couldn't place take profit for short strategy")
                exceptions.append(e)
                logging.error(e)
                closeMainOrder()
                raise e
            logging.info("Short strategy take profit placed")
            lowestRichedPrice = currentPrice
        elif currentPrice <= (
            takeProfitPrice
            - Settings.SafeDealRangeAmount
            - Settings.AmountNotToMakeStopOrderExecuteInstantly
        ):
            if (
                lowestRichedPrice == 0
                or ((lowestRichedPrice - currentPrice) / lowestRichedPrice)
                >= Settings.SignificantChangeInHighestPriceInRelationPrevious
            ):
                logging.info("New lowest price reached for short strategy")
                if takeProfit is not None:
                    try:
                        client.cancel_margin_order(
                            symbol=Settings.Symbol,
                            isIsolated=isIsolated,
                            orderId=takeProfit["orderId"],
                        )
                    except Exception as e:
                        exceptions.append(
                            "Couldn't cancel takeProfit for short strategy"
                        )
                        exceptions.append(e)
                        logging.error(e)
                        return
                    logging.info("Canceled previous take profit for short strategy")
                elif lowestRichedPrice == 0:
                    try:
                        client.cancel_margin_order(
                            symbol=Settings.Symbol,
                            isIsolated=isIsolated,
                            orderId=stopLoss["orderId"],
                        )
                    except Exception as e:
                        exceptions.append(
                            "Couldn't cancel stop-loss for short strategy"
                        )
                        exceptions.append(e)
                        logging.error(e)
                        return
                    logging.info("Canceled stop loss for short strategy")
                try:
                    tp_order = client.create_margin_order(
                        symbol=Settings.Symbol,
                        isIsolated=isIsolated,
                        side=enums.SIDE_BUY,
                        type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                        quantity=quantityInBaseToBuy,
                        price=round(
                            (
                                currentPrice
                                + Settings.SafeDealRangeAmount
                                + Settings.AmountNotToMakeStopOrderExecuteInstantly
                            ),
                            Settings.TickPriceRounding,
                        ),
                        stopPrice=round(
                            (
                                currentPrice
                                + Settings.AmountNotToMakeStopOrderExecuteInstantly
                            ),
                            Settings.TickPriceRounding,
                        ),
                        newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                        timeInForce=enums.TIME_IN_FORCE_FOK,
                    )
                    takeProfit = tp_order
                except Exception as e:
                    exceptions.append("Couldn't move down/place takeProfit for short")
                    exceptions.append(e)
                    logging.error(e)
                    closeMainOrder()
                    raise e
                logging.info("Moved take profit down for short strategy")
                lowestRichedPrice = currentPrice


def borrowFunds():
    try:
        client.create_margin_loan(
            asset=Settings.BaseCurrency,
            amount=f"{quantityInBase}",
            isIsolated=isIsolated,
            symbol=Settings.Symbol,
        )
    except exc.BinanceAPIException as e:
        exceptions.append("Couldn't borrow funds for short strategy")
        logging.error(e)
        raise e
    except Exception as e:
        exceptions.append("Couldn't borrow funds for short strategy")
        logging.error(e)
        return False
    logging.info(f"Borrowed {quantityInBase}{Settings.BaseCurrency} for short strategy")
    return True


def repayLoan():
    global repayed
    if not repayed:
        success = False
        attempt = 0
        while not success and attempt < 3:
            try:
                amt = math.ceil(
                    (quantityInBase + quantityInBase * Settings.BorrowComissionRate)
                    * pow(10, Settings.BaseCurrencyMinAmountRounding)
                ) / pow(10, Settings.BaseCurrencyMinAmountRounding)
                client.repay_margin_loan(
                    asset=Settings.BaseCurrency,
                    amount=f"{amt}",
                    isIsolated=isIsolated,
                    symbol=Settings.Symbol,
                )
            except Exception as e:
                logging.error(e)
                attempt += 1
            else:
                logging.info("Successfully paid the loan back")
                repayed = True
                return True
        if not success:
            logging.error("Should repay manually")
            raise SystemExit


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
    if rate is None:
        return False
    quantity = Settings.TradingAmountInQuote / rate
    quantityInBase = round(quantity, Settings.BaseCurrencyMinAmountRounding)
    if strategy == 1:
        if not borrowFunds():
            return False
        q = (quantityInBase + quantityInBase * Settings.BorrowComissionRate) / (
            1 - Settings.FeeRate
        )
        quantityInBaseToBuy = math.ceil(
            q * pow(10, Settings.BaseCurrencyMinAmountRounding)
        ) / pow(10, Settings.BaseCurrencyMinAmountRounding)
        logging.info(f"Quantity in Base to buy = {quantityInBaseToBuy}")
    if placeMainOrder():
        while True:
            try:
                if strategy == 0:
                    mainOrderInfo = client.get_order(
                        symbol=Settings.Symbol, orderId=mainOrder["orderId"]
                    )
                else:
                    mainOrderInfo = client.get_margin_order(
                        symbol=Settings.Symbol,
                        isIsolated=isIsolated,
                        orderId=mainOrder["orderId"],
                    )
            except Exception as e:
                exceptions.append("Couldn't get Main Order Info")
                logging.error(e)
                continue
            status = mainOrderInfo["status"]
            logging.info(f"Main Order Status: {status}")
            if status == "FILLED":
                enteringPrice_local = float(
                    mainOrderInfo["cummulativeQuoteQty"]
                ) / float(mainOrderInfo["executedQty"])
                enteringPrice_local = round(
                    enteringPrice_local, Settings.TickPriceRounding
                )
                enteringPrice_local = float(enteringPrice_local)
                enteringPrice = enteringPrice_local
                logging.info(f"Main order average fill price = {enteringPrice}")
                logging.info(
                    f"Main order amount in base = {mainOrderInfo['executedQty']}"
                )
                quantityInQoute_local = quantityInBase * enteringPrice
                quantityInQoute_local = round(
                    quantityInQoute_local, Settings.TickPriceRounding
                )
                quantityInQoute_local = float(quantityInQoute_local)
                quantityInQoute = quantityInQoute_local
                if strategy == 0:
                    takeProfit_local = enteringPrice * (1 + Settings.ProfitDealRange)
                    takeProfit_local = round(
                        takeProfit_local, Settings.TickPriceRounding
                    )
                    takeProfitPrice = takeProfit_local
                    stopLoss_local = enteringPrice * (1 - Settings.LossDealRange)
                    stopLoss_local = round(stopLoss_local, Settings.TickPriceRounding)
                    stopLossPrice = stopLoss_local
                    executedQty = float(mainOrderInfo["executedQty"])
                    val = executedQty - executedQty * 0.001
                    val2 = math.floor(
                        val * pow(10, Settings.BaseCurrencyMinAmountRounding)
                    )
                    quantityInBaseToSell_local = val2 / pow(
                        10, Settings.BaseCurrencyMinAmountRounding
                    )
                    quantityInBaseToSell = quantityInBaseToSell_local
                    logging.info(f"Quantity in Base to sell = {quantityInBaseToSell}")
                else:
                    takeProfit_local = enteringPrice * (1 - Settings.ProfitDealRange)
                    takeProfit_local = round(
                        takeProfit_local, Settings.TickPriceRounding
                    )
                    takeProfitPrice = takeProfit_local
                    stopLoss_local = enteringPrice * (1 + Settings.LossDealRange)
                    stopLoss_local = round(stopLoss_local, Settings.TickPriceRounding)
                    stopLossPrice = stopLoss_local
                return True
            elif status == "EXPIRED":
                logging.error("Main order status: EXPIRED")
                closeAllOpenOrders()
                raise SystemExit
            elif status == "CANCELED":
                logging.error("Main order was canceled unexpectedly")
                closeAllOpenOrders()
                raise SystemExit
    else:
        logging.error("Main order hasn't been executed")
        exceptions.append("Main order hasn't been executed")
        return False


def placeMainOrder():
    global mainOrder
    try:
        if strategy == 0:
            mainOrder_local = client.order_market_buy(
                symbol=Settings.Symbol, quantity=quantityInBase
            )
            mainOrder = mainOrder_local
        else:
            mainOrder_local = client.create_margin_order(
                symbol=Settings.Symbol,
                isIsolated=isIsolated,
                side=enums.SIDE_SELL,
                type=enums.ORDER_TYPE_MARKET,
                quantity=quantityInBase,
                newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
            )
            mainOrder = mainOrder_local
    except Exception as e:
        exceptions.append("Couldn't place main order")
        exceptions.append(e)
        logging.error(e)
        return False
    logging.info("Main order placed successfully")
    return True


def closeMainOrder(cancelAllorders=False):
    global forcedCloseOrder
    global forcedClosure
    global exceptions
    if cancelAllorders:
        closeAllOpenOrders()
    logging.info("Trying to close main order")
    while True:
        try:
            if strategy == 0:
                forcedCloseOrder_local = client.order_market_sell(
                    symbol=Settings.Symbol,
                    quantity=round(quantityInBaseToSell, Settings.TickPriceRounding),
                )
                forcedCloseOrder = forcedCloseOrder_local
            else:
                forcedCloseOrder_local = client.create_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=isIsolated,
                    side=enums.SIDE_BUY,
                    type=enums.ORDER_TYPE_MARKET,
                    quantity=round(
                        quantityInBaseToBuy, Settings.BaseCurrencyMinAmountRounding
                    ),
                    newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                )
                forcedCloseOrder = forcedCloseOrder_local
                repayLoan()
        except Exception as e:
            exceptions.append("Couldn't close the main order")
            exceptions.append(e)
            logging.error(e)
            if getForcedCloseOrderStatus() != "FILLED":
                continue
            else:
                logging.info("Forced Close was executed despite the error")
                forcedClosure = True
                return True
        else:
            logging.info("Successfully closed MainOrder")
            forcedClosure = True
            return True


def checkMainOrder():
    attempt = 0
    success = False
    order = None
    while attempt < 3 and not success:
        try:
            if strategy == 0:
                order_local = client.get_order(
                    symbol=Settings.Symbol, orderId=mainOrder["orderId"]
                )
                order = order_local
            else:
                order_local = client.get_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=isIsolated,
                    orderId=mainOrder["orderId"],
                )
                order = order_local
        except Exception as e:
            logging.error(e)
            attempt += 1
        else:
            success = True
    if not success:
        return None
    status = order["status"]
    logging.info(f"Main order status: {status}")
    return status


def checkTakeProfitStatus():
    if strategy == 0:
        order = client.get_order(symbol=Settings.Symbol, orderId=takeProfit["orderId"])
    else:
        order = client.get_margin_order(
            symbol=Settings.Symbol,
            isIsolated=isIsolated,
            orderId=takeProfit["orderId"],
        )
    status = order["status"]
    logging.info(f"TakeProfit order status: {status}")
    return status


def cancelTakeProfit():
    global takeProfit
    try:
        client.cancel_order(symbol=Settings.Symbol, orderId=takeProfit["orderId"])
        takeProfit = None
    except Exception as e:
        exceptions.append("Couldn't cancel take profit")
        logging.error(e)
        return False
    logging.info("Canceled take profit")
    return True


def placeStopLossOrder():
    global stopLoss
    global inPosition
    try:
        if strategy == 0:
            sl = client.create_order(
                symbol=Settings.Symbol,
                side=enums.SIDE_SELL,
                type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=enums.TIME_IN_FORCE_FOK,
                quantity=quantityInBaseToSell,
                price=stopLossPrice,
                stopPrice=round(
                    stopLossPrice + Settings.SafeDealRangeAmount,
                    Settings.TickPriceRounding,
                ),
                newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
            )
            stopLoss = sl
        else:
            sl = client.create_margin_order(
                symbol=Settings.Symbol,
                isIsolated=isIsolated,
                side=enums.SIDE_BUY,
                type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=enums.TIME_IN_FORCE_FOK,
                quantity=quantityInBaseToBuy,
                price=stopLossPrice,
                stopPrice=round(
                    stopLossPrice - Settings.SafeDealRangeAmount,
                    Settings.TickPriceRounding,
                ),
                newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
            )
            stopLoss = sl
    except Exception as e:
        exceptions.append("Couldn't create stop loss")
        exceptions.append(e)
        logging.error("Couldn't create stop loss")
        closeMainOrder()
        return False
    logging.info("StopLoss placed")
    inPosition = True
    return True


def checkStopLossStatus():
    if strategy == 0:
        order = client.get_order(symbol=Settings.Symbol, orderId=stopLoss["orderId"])
    else:
        order = client.get_margin_order(
            symbol=Settings.Symbol,
            isIsolated=isIsolated,
            orderId=stopLoss["orderId"],
        )
    status = order["status"]
    logging.info(f"StopLoss order status: {status}")
    return status


def closeStopLoss():
    global exceptions
    attempt = 0
    success = False
    while attempt < 3 and not success:
        try:
            if strategy == 0:
                client.cancel_order(symbol=Settings.Symbol, orderId=stopLoss["orderId"])
            else:
                client.cancel_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=isIsolated,
                    orderId=stopLoss["orderId"],
                )
        except Exception as e:
            exceptions.append("Couldn't cancel stop-loss")
            exceptions.append(e)
            logging.error(e)
            attempt += 1
        else:
            logging.info("Canceled stop loss")
            success = True
            return True
    return False


def closeAllOpenOrders():
    logging.info("Closing all open orders")
    if strategy == 0:
        orders = client.get_open_orders(symbol=Settings.Symbol)
    else:
        orders = client.get_open_margin_orders(
            symbol=Settings.Symbol, isIsolated=isIsolated
        )
    for o in orders:
        if strategy == 0:
            client.cancel_order(symbol=Settings.Symbol, orderId=o["orderId"])
        else:
            client.cancel_margin_order(
                symbol=Settings.Symbol, isIsolated=isIsolated, orderId=o["orderId"]
            )
    logging.info("Closed all open orders")


def checkForPriceBreakThrough(cp):
    if takeProfit is not None:
        if strategy == 0:
            if (
                float(takeProfit["price"])
                - Settings.StopLossTakeProfitPassedByCheckAmount
                >= cp
            ):
                return True
            return False
        else:
            if (
                float(takeProfit["price"])
                + Settings.StopLossTakeProfitPassedByCheckAmount
                <= cp
            ):
                return True
            return False
    elif stopLoss is not None:
        if strategy == 0:
            if (
                float(stopLoss["price"])
                - Settings.StopLossTakeProfitPassedByCheckAmount
                >= cp
            ):
                return True
            return False
        else:
            if (
                float(stopLoss["price"])
                + Settings.StopLossTakeProfitPassedByCheckAmount
                <= cp
            ):
                return True
            return False
    return False


def checkForStuckPrice(timeChange, priceChange=0):
    if timeChange > Settings.StuckPriceTimeout and priceChange == 0:
        exceptions.append("Price has stuck")
        logging.warning("Price has stuck")
        return True
    return False


def checkForOverstayInDeal(startTime, priceChange):
    global exceptions
    currTime = time()
    logging.info(f"Time Passed = {currTime - startTime}")
    if (currTime - startTime) > Config.FirstOverstayInDealTimeout and (
        (priceChange > 0.2) if strategy == 0 else (priceChange < -0.2)
    ):
        exceptions.append("Staying in the deal beyond first overstay threshold")
        logging.warning("Staying in the deal beyond first overstay threshold")
        return True
    elif (currTime - startTime) > Config.SecondOverstayInDealTimeout:
        exceptions.append("Staying in the deal beyond second overstay threshold")
        logging.warning("Staying in the deal beyond second overstay threshold")
        return True
    return False


async def gettingCurrentOrderInfo():
    global openOrders
    global doingJob
    global takeProfit
    global exceptions
    circleCounter = 0
    attempt = 0
    success = False
    asyncClient2 = None
    try:
        asyncClient2_local = await AsyncClient.create(
            api_key=Settings.API_KEY, api_secret=Settings.API_SECRET
        )
        asyncClient2 = asyncClient2_local
    except Exception as e:
        exceptions.append("Couldn't connect AsyncClient2")
        exceptions.append(e)
        logging.error(e)
        attempt += 1
    else:
        logging.info("Connected AsyncClient2")
        success = True
    if not success:
        logging.error("Couldn't connect asyncClient2")
        if mainOrder is None:
            await closeConnection()
        else:
            st = checkMainOrder()
            if st == "FILLED":
                if closeMainOrder():
                    await closeConnection()
                else:
                    raise SystemExit
            else:
                await closeConnection()
    while doingJob:
        if takeProfit is not None:
            s2 = False
            a2 = 0
            order = None
            while not s2 and a2 < 3:
                try:
                    if strategy == 0:
                        o = await asyncClient2.get_order(
                            symbol=Settings.Symbol, orderId=takeProfit["orderId"]
                        )
                        order = o
                    else:
                        o = await asyncClient2.get_margin_order(
                            symbol=Settings.Symbol,
                            isIsolated=isIsolated,
                            orderId=takeProfit["orderId"],
                        )
                        order = o
                except Exception as e:
                    exceptions.append("Couldn't get take profit info")
                    exceptions.append(e)
                    logging.error(e)
                    a2 += 1
                else:
                    s2 = True
            if not s2:
                continue
            if order["status"] == "FILLED" and doingJob:
                logging.info("Take profit has been filled")
                if strategy == 1:
                    repayLoan()
                await closeConnection()
                break
            elif order["status"] == "EXPIRED" and forcedCloseOrder is None:
                exceptions.append("Take Profit Expired")
                if not closeMainOrder():
                    raise SystemExit
                await closeConnection()
                break
        elif stopLoss is not None:
            s2 = False
            a2 = 0
            order = None
            while a2 < 3 and not s2:
                try:
                    if strategy == 0:
                        o = await asyncClient2.get_order(
                            symbol=Settings.Symbol, orderId=stopLoss["orderId"]
                        )
                        order = o
                    else:
                        o = await asyncClient2.get_margin_order(
                            symbol=Settings.Symbol,
                            isIsolated=isIsolated,
                            orderId=stopLoss["orderId"],
                        )
                        order = o
                except Exception as e:
                    exceptions.append("Couldn't get stop loss info")
                    exceptions.append(e)
                    logging.error(e)
                    a2 += 1
                else:
                    s2 = True
            if not s2:
                continue
            if order["status"] == "FILLED":
                logging.info("StopLoss has been filled")
                if strategy == 1:
                    repayLoan()
                await closeConnection()
                break
            elif (
                order["status"] in ["EXPIRED", "CANCELED"] and forcedCloseOrder is None
            ):
                if takeProfit is None and not forcedClosure:
                    exceptions.append("StopLoss expired or canceled unexpectedly")
                    closeMainOrder()
                    await closeConnection()
                    break
        s3 = False
        a3 = 0
        while not s3 and a3 < 3:
            try:
                if strategy == 0:
                    oo = await asyncClient2.get_open_orders(symbol=Settings.Symbol)
                    openOrders = oo
                else:
                    oo = await asyncClient2.get_open_margin_orders(
                        symbol=Settings.Symbol, isIsolated=isIsolated
                    )
                    openOrders = oo
            except Exception as e:
                exceptions.append("Couldn't retrieve open orders")
                exceptions.append(e)
                logging.error(e)
                a3 += 1
            else:
                s3 = True
        if not s3:
            closeMainOrder()
            await closeConnection()
            await asyncClient2.close_connection()
            raise exc.BinanceRequestException
        if openOrders == [] and doingJob:
            if takeProfit is not None and doingJob:
                st = checkTakeProfitStatus()
                if st == "FILLED":
                    if strategy == 1:
                        repayLoan()
                    await closeConnection()
                    break
                elif st == "EXPIRED":
                    closeMainOrder()
                    exceptions.append("Take Profit Expired")
                    await closeConnection()
                    break
            elif stopLoss is not None and doingJob:
                st = checkStopLossStatus()
                if st == "FILLED":
                    if strategy == 1:
                        repayLoan()
                    await closeConnection()
                    break
                elif st == "EXPIRED":
                    closeMainOrder()
                    exceptions.append("Stop Loss Expired")
                    await closeConnection()
                    break
            elif mainOrder is not None:
                logging.info("Neither stopLoss nor takeProfit placed yet")
            else:
                logging.info("Main order has not been placed yet")
        if circleCounter >= 2:
            logging.info("Open Order Info:")
            for o in openOrders:
                logging.info("------------")
                check_price = float(o["price"])
                if (
                    (check_price > enteringPrice)
                    if strategy == 0
                    else (check_price < enteringPrice)
                ):
                    logging.info("Take Profit:")
                else:
                    logging.info("Stop Loss:")
                logging.info(o)
            logging.info("------------")
            circleCounter = 0
        else:
            circleCounter += 1
        await asyncio.sleep(0.5)
    await asyncClient2.close_connection()
    logging.info("AsyncClient2 closed")


def getCurrentExchangeRate(pair):
    try:
        info = client.get_ticker(symbol=pair)["lastPrice"]
    except Exception as e:
        exceptions.append("Couldn't get current exchange rate")
        logging.error(e)
        return None
    val = float(info)
    logging.info(f"Current exchange for {pair} = {val}")
    return val


def getSpread(symbol):
    try:
        info = client.get_orderbook_ticker(symbol=symbol)
        sp = round(
            float(info["askPrice"]) - float(info["bidPrice"]),
            Settings.TickPriceRounding,
        )
        logging.info(f"Spread = {sp}")
        return sp
    except Exception as e:
        logging.error(f"Couldn't get {symbol} spread: {e}")
        return -1


def getForcedCloseOrderStatus():
    try:
        if strategy == 0:
            order = client.get_order(
                symbol=Settings.Symbol, orderId=forcedCloseOrder["orderId"]
            )
        else:
            order = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=isIsolated,
                orderId=forcedCloseOrder["orderId"],
            )
        st = order["status"]
        logging.info(f"Forced Close order status: {st}")
        return st
    except Exception:
        logging.error("Couldn't get forced closure status")
        return None


def printLastPrices(symbol):
    try:
        info = client.get_symbol_ticker(symbol=symbol)
        logging.info(f"Price for {symbol} = {info['price']}")
    except Exception as e:
        logging.error(f"Couldn't get last price for {symbol}: {e}")


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
    logging.info("closeConnection")
    closeAllOpenOrders()
    global doingJob
    doingJob = False
    printLastPrices(symbol=Settings.Symbol)
    await asyncio.sleep(2)
    printLastPrices(symbol=Settings.Symbol)


async def spaceDivider():
    while doingJob:
        logging.debug(".")
        await asyncio.sleep(0.5)


async def main(mainClient, config, strat=0, isolated=True):
    restoreGlobals()
    global client
    global exceptions
    global strategy
    global Settings
    global isIsolated
    Settings = config
    strategy = strat
    returnDict = {
        "mainOrderId": 0,
        "tradingAmountInBase": 0,
        "tradingAmountInQuote": 0,
        "enteredPrice": 0,
        "stopLossPrice": 0,
        "takeProfitPrice": 0,
        "closedPrice": 0,
        "closedBy": 0,
        "updatedSpread": 0,
        "issues": exceptions,
    }
    isIsolated = "TRUE" if isolated else "FALSE"
    logging.info("Strategy main entry")
    client = mainClient
    s = getSpread(symbol=Settings.Symbol)
    currentSpread = round(s, Settings.TickPriceRounding)
    returnDict["updatedSpread"] = currentSpread
    if currentSpread == -1:
        exceptions.append("Couldn't get the spread")
        logging.error("Couldn't get the spread")
        return returnDict
    if currentSpread > (Settings.InitialSpread) * config.MaxIncreaseInSpreadMultiplier:
        msg = f"Spread increased to {currentSpread} from {Settings.InitialSpread}"
        exceptions.append(msg)
        logging.error(msg)
        return returnDict
    check1 = executeMainOrder()
    if not check1:
        printLastPrices(symbol=Settings.Symbol)
        return returnDict
    check2 = placeStopLossOrder()
    try:
        if check1 and check2:
            task1 = asyncio.create_task(getCurrentPrice())
            task2 = asyncio.create_task(gettingCurrentOrderInfo())
            await task1
            await task2
    except Exception as e:
        exceptions.append(e)
        logging.error(e)
        closeMainOrder(cancelAllorders=True)
    finally:
        closeAllOpenOrders()
    closedPrice = 0
    closedBy = ""
    if forcedClosure:
        if strategy == 0:
            info = client.get_order(
                symbol=Settings.Symbol, orderId=forcedCloseOrder["orderId"]
            )
        else:
            info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=isIsolated,
                orderId=forcedCloseOrder["orderId"],
            )
        cPrice = float(info["cummulativeQuoteQty"]) / float(info["executedQty"])
        closedPrice = cPrice
        closedBy = "Forced Closure"
    elif takeProfit is not None:
        if strategy == 0:
            info = client.get_order(
                symbol=Settings.Symbol, orderId=takeProfit["orderId"]
            )
        else:
            info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=isIsolated,
                orderId=takeProfit["orderId"],
            )
        cPrice = float(info["cummulativeQuoteQty"]) / float(info["executedQty"])
        closedPrice = cPrice
        closedBy = "Take Profit"
    elif stopLoss is not None:
        if strategy == 0:
            info = client.get_order(symbol=Settings.Symbol, orderId=stopLoss["orderId"])
        else:
            info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=isIsolated,
                orderId=stopLoss["orderId"],
            )
        if float(info["executedQty"]) == 0:
            closedPrice = 0
        else:
            cPrice = float(info["cummulativeQuoteQty"]) / float(info["executedQty"])
            closedPrice = cPrice
            closedBy = "Stop Loss"
    else:
        cPrice = 0
        if strategy == 0:
            info = client.get_order(
                symbol=Settings.Symbol, orderId=trailingTakeProfit["orderId"]
            )
        else:
            info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=isIsolated,
                orderId=trailingTakeProfit["orderId"],
            )
        cPrice = float(info["cummulativeQuoteQty"]) / float(info["executedQty"])
        closedPrice = cPrice
        closedBy = "Traililng Take Profit"
    if mainOrder is None:
        mainOrderId = 0
    else:
        mainOrderId = mainOrder["orderId"]
        returnDict["mainOrderId"] = mainOrderId
        returnDict["tradingAmountInBase"] = quantityInBase
        returnDict["tradingAmountInQuote"] = quantityInQoute
        returnDict["enteringPrice"] = enteringPrice
        returnDict["stopLossPrice"] = stopLossPrice
        returnDict["takeProfitPrice"] = takeProfitPrice
        returnDict["closedPrice"] = closedPrice
        returnDict["closedBy"] = closedBy
        returnDict["exceptions"] = exceptions
    logging.info("Deal is done")
    return returnDict


if __name__ == "__main__":
    config = Config()
    client = Client(config.API_KEY, config.API_SECRET)
    config.setSymbol("IOTXUSDT")
    asyncio.run(main(mainClient=client, config=config, strat=1, isolated=False))

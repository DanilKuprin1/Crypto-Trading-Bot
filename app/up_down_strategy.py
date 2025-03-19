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
    NO_ISSUE = 0
    MAIN_ORDER_NOT_PLACED = 1


current_price = 0
highest_reached_price = 0
lowest_reached_price = 0
take_profit_price = 0
stop_loss_price = 0
entering_price = 0
open_orders = {}
doing_job = True
client = None
in_position = False
trailing_take_profit_set = False
quantity_in_base = 0
quantity_in_base_to_sell = 0
quantity_in_base_to_buy = 0
quantity_in_quote = 0
main_order = None
stop_loss = None
following_stop_loss = None
take_profit = None
trailing_take_profit = None
started_following = False
issue = Issue.NO_ISSUE
forced_closure = False
forced_close_order = None
exceptions_list = []
strategy = 0
repaid = False
Settings = None
is_isolated = "TRUE"
times_price_unchanged = 0


async def get_current_price():
    global current_price, exceptions_list, doing_job
    attempt = 0
    success = False
    async_client = None
    while not success and attempt < 3:
        try:
            async_client = await AsyncClient.create()
        except Exception as excp:
            exceptions_list.append("Couldn't create AsyncClient1")
            logging.error(excp)
            attempt += 1
        else:
            logging.info("Successfully connected AsyncClient1")
            success = True
    if not success:
        logging.error("Couldn't connect AsyncClient1 after retries")
        raise Exception
    manager = BinanceSocketManager(async_client)
    socket = manager.trade_socket(symbol=Settings.Symbol)
    start_time = time()
    async with socket as soc:
        while doing_job:
            if not doing_job:
                await async_client.close_connection()
                return
            t1 = time()
            data = await soc.recv()
            t2 = time()
            new_price = float(data["p"])
            logging.info("New market price = %s", new_price)
            change_pct = 0
            if in_position and new_price > entering_price:
                change_pct = round(
                    ((new_price - entering_price) / entering_price) * 100, 3
                )
                logging.info("+%s%% from entering price", change_pct)
            elif in_position and new_price < entering_price:
                change_pct = round(
                    ((new_price - entering_price) / entering_price) * 100, 3
                )
                logging.info("%s%% from entering price", change_pct)
            elif in_position:
                logging.info("0%% from entering price")
            logging.info("Strategy - Up" if strategy == 0 else "Strategy - Down")
            current_price = new_price
            if price_breakthrough(new_price) and doing_job:
                handle_price_break()
                if doing_job and strategy == 1:
                    repay_loan()
                await close_connection()
                await async_client.close_connection()
                return
            if not doing_job:
                await async_client.close_connection()
                return
            try:
                analyze_price()
            except Exception as excp:
                logging.error(excp)
                exceptions_list.append(excp)
                if not forced_closure:
                    close_main_order()
                await close_connection()
                await async_client.close_connection()
                return
            if stuck_price(t2 - t1, change_pct) or overstayed_in_deal(
                start_time, change_pct
            ):
                close_main_order(cancel_all=True)
                await close_connection()
                await async_client.close_connection()
    await async_client.close_connection()


def analyze_price():
    global \
        take_profit, \
        stop_loss, \
        in_position, \
        highest_reached_price, \
        lowest_reached_price
    if in_position and doing_job and strategy == 0:
        if (
            current_price > take_profit_price + Settings.SafeDealRangeAmount
            and take_profit is None
            and current_price
            < take_profit_price
            + Settings.AmountNotToMakeStopOrderExecuteInstantly
            + Settings.SafeDealRangeAmount
        ):
            try:
                logging.info("Trying to cancel stopLoss")
                client.cancel_order(
                    symbol=Settings.Symbol, orderId=stop_loss["orderId"]
                )
            except Exception as excp:
                exceptions_list.append("Couldn't cancel bottom stop-loss")
                exceptions_list.append(excp)
                logging.error("Couldn't cancel stop-loss")
                return
            attempt = 0
            placed = False
            while attempt < 3 and not placed:
                try:
                    logging.info("Trying to place takeProfit")
                    tp_price = take_profit_price
                    tp_stop = round(
                        take_profit_price + Settings.SafeDealRangeAmount,
                        Settings.TickPriceRounding,
                    )
                    order = client.create_order(
                        symbol=Settings.Symbol,
                        side=enums.SIDE_SELL,
                        type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                        timeInForce=enums.TIME_IN_FORCE_FOK,
                        quantity=quantity_in_base_to_sell,
                        price=tp_price,
                        stopPrice=tp_stop,
                        newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                    )
                    take_profit = order
                except Exception as excp2:
                    exceptions_list.append("Couldn't place take profit instantly")
                    exceptions_list.append(excp2)
                    logging.error(excp2)
                    attempt += 1
                else:
                    logging.info("Placed takeProfit order")
                    placed = True
                    highest_reached_price = current_price
            if not placed:
                if close_main_order():
                    logging.info("Closed main order due to failed takeProfit placement")
                    raise Exception
                raise SystemExit
        elif current_price >= (
            take_profit_price
            + Settings.SafeDealRangeAmount
            + Settings.AmountNotToMakeStopOrderExecuteInstantly
        ):
            if (
                highest_reached_price == 0
                or ((current_price - highest_reached_price) / highest_reached_price)
                >= Settings.SignificantChangeInHighestPriceInRelationPrevious
            ):
                logging.info("New highest price reached")
                if highest_reached_price == 0:
                    if not close_stop_loss():
                        return
                elif take_profit is not None:
                    try:
                        client.cancel_order(
                            symbol=Settings.Symbol, orderId=take_profit["orderId"]
                        )
                    except Exception as excp:
                        exceptions_list.append(
                            "Couldn't cancel takeProfit and move it up"
                        )
                        exceptions_list.append(excp)
                        logging.error("Couldn't cancel/adjust takeProfit")
                        return
                    logging.info("Canceled previous take profit")
                try:
                    price = round(
                        current_price
                        - Settings.SafeDealRangeAmount
                        - Settings.AmountNotToMakeStopOrderExecuteInstantly,
                        Settings.TickPriceRounding,
                    )
                    stop_price = round(
                        current_price
                        - Settings.AmountNotToMakeStopOrderExecuteInstantly,
                        Settings.TickPriceRounding,
                    )
                    order = client.create_order(
                        symbol=Settings.Symbol,
                        side=enums.SIDE_SELL,
                        type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                        timeInForce=enums.TIME_IN_FORCE_FOK,
                        quantity=quantity_in_base_to_sell,
                        price=price,
                        stopPrice=stop_price,
                        newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                    )
                    take_profit = order
                except Exception as excp:
                    exceptions_list.append("Couldn't move TakeProfit up")
                    exceptions_list.append(excp)
                    logging.error("Couldn't move TakeProfit up")
                    if close_main_order():
                        raise Exception
                    logging.error("Manual sell required for UpStrategy")
                    raise SystemExit
                logging.info("Moved take profit up")
                highest_reached_price = current_price
    elif in_position and doing_job and strategy == 1:
        if (
            current_price <= take_profit_price - Settings.SafeDealRangeAmount
            and take_profit is None
            and current_price
            > take_profit_price
            - Settings.SafeDealRangeAmount
            - Settings.AmountNotToMakeStopOrderExecuteInstantly
        ):
            try:
                logging.info("Cancel stop loss for short strategy")
                client.cancel_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=is_isolated,
                    orderId=stop_loss["orderId"],
                )
            except Exception as excp:
                exceptions_list.append("Couldn't cancel stop-loss for short strategy")
                exceptions_list.append(excp)
                logging.error(excp)
                return
            logging.info("Canceled stop loss")
            try:
                tp_order = client.create_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=is_isolated,
                    side=enums.SIDE_BUY,
                    type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                    quantity=quantity_in_base_to_buy,
                    price=take_profit_price,
                    stopPrice=round(
                        take_profit_price - Settings.SafeDealRangeAmount,
                        Settings.TickPriceRounding,
                    ),
                    newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                    timeInForce=enums.TIME_IN_FORCE_FOK,
                )
                take_profit = tp_order
            except Exception as excp:
                exceptions_list.append("Couldn't place take profit for short strategy")
                exceptions_list.append(excp)
                logging.error(excp)
                close_main_order()
                raise excp
            logging.info("Short strategy take profit placed")
            lowest_reached_price = current_price
        elif current_price <= (
            take_profit_price
            - Settings.SafeDealRangeAmount
            - Settings.AmountNotToMakeStopOrderExecuteInstantly
        ):
            if (
                lowest_reached_price == 0
                or ((lowest_reached_price - current_price) / lowest_reached_price)
                >= Settings.SignificantChangeInHighestPriceInRelationPrevious
            ):
                logging.info("New lowest price reached for short strategy")
                if take_profit is not None:
                    try:
                        client.cancel_margin_order(
                            symbol=Settings.Symbol,
                            isIsolated=is_isolated,
                            orderId=take_profit["orderId"],
                        )
                    except Exception as excp:
                        exceptions_list.append(
                            "Couldn't cancel takeProfit for short strategy"
                        )
                        exceptions_list.append(excp)
                        logging.error(excp)
                        return
                    logging.info("Canceled previous take profit for short strategy")
                elif lowest_reached_price == 0:
                    try:
                        client.cancel_margin_order(
                            symbol=Settings.Symbol,
                            isIsolated=is_isolated,
                            orderId=stop_loss["orderId"],
                        )
                    except Exception as excp:
                        exceptions_list.append(
                            "Couldn't cancel stop-loss for short strategy"
                        )
                        exceptions_list.append(excp)
                        logging.error(excp)
                        return
                    logging.info("Canceled stop loss for short strategy")
                try:
                    tp_order = client.create_margin_order(
                        symbol=Settings.Symbol,
                        isIsolated=is_isolated,
                        side=enums.SIDE_BUY,
                        type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                        quantity=quantity_in_base_to_buy,
                        price=round(
                            current_price
                            + Settings.SafeDealRangeAmount
                            + Settings.AmountNotToMakeStopOrderExecuteInstantly,
                            Settings.TickPriceRounding,
                        ),
                        stopPrice=round(
                            current_price
                            + Settings.AmountNotToMakeStopOrderExecuteInstantly,
                            Settings.TickPriceRounding,
                        ),
                        newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                        timeInForce=enums.TIME_IN_FORCE_FOK,
                    )
                    take_profit = tp_order
                except Exception as excp:
                    exceptions_list.append(
                        "Couldn't move down/place takeProfit for short"
                    )
                    exceptions_list.append(excp)
                    logging.error(excp)
                    close_main_order()
                    raise excp
                logging.info("Moved take profit down for short strategy")
                lowest_reached_price = current_price


def borrow_funds():
    try:
        client.create_margin_loan(
            asset=Settings.BaseCurrency,
            amount=str(quantity_in_base),
            isIsolated=is_isolated,
            symbol=Settings.Symbol,
        )
    except exc.BinanceAPIException as excp:
        exceptions_list.append("Couldn't borrow funds for short strategy")
        logging.error(excp)
        raise excp
    except Exception as excp:
        exceptions_list.append("Couldn't borrow funds for short strategy")
        logging.error(excp)
        return False
    logging.info(
        "Borrowed %s%s for short strategy", quantity_in_base, Settings.BaseCurrency
    )
    return True


def repay_loan():
    global repaid
    if not repaid:
        success = False
        attempt = 0
        while not success and attempt < 3:
            try:
                amt = math.ceil(
                    (quantity_in_base + quantity_in_base * Settings.BorrowComissionRate)
                    * pow(10, Settings.BaseCurrencyMinAmountRounding)
                ) / pow(10, Settings.BaseCurrencyMinAmountRounding)
                client.repay_margin_loan(
                    asset=Settings.BaseCurrency,
                    amount=str(amt),
                    isIsolated=is_isolated,
                    symbol=Settings.Symbol,
                )
            except Exception as excp:
                logging.error(excp)
                attempt += 1
            else:
                logging.info("Successfully paid the loan back")
                repaid = True
                return True
        logging.error("Should repay manually")
        raise SystemExit


def execute_main_order():
    global entering_price, quantity_in_quote, stop_loss_price, take_profit_price
    global \
        exceptions_list, \
        quantity_in_base, \
        quantity_in_base_to_sell, \
        quantity_in_base_to_buy
    rate = get_exchange_rate(Settings.Symbol)
    if rate is None:
        return False
    quant = Settings.TradingAmountInQuote / rate
    quantity_in_base = round(quant, Settings.BaseCurrencyMinAmountRounding)
    if strategy == 1:
        if not borrow_funds():
            return False
        calc = (quantity_in_base + quantity_in_base * Settings.BorrowComissionRate) / (
            1 - Settings.FeeRate
        )
        quantity_in_base_to_buy_local = math.ceil(
            calc * pow(10, Settings.BaseCurrencyMinAmountRounding)
        )
        quantity_in_base_to_buy_local /= pow(10, Settings.BaseCurrencyMinAmountRounding)
        quantity_in_base_to_buy = quantity_in_base_to_buy_local
        logging.info("Quantity in Base to buy = %s", quantity_in_base_to_buy)
    if place_main_order():
        while True:
            try:
                if strategy == 0:
                    info = client.get_order(
                        symbol=Settings.Symbol, orderId=main_order["orderId"]
                    )
                else:
                    info = client.get_margin_order(
                        symbol=Settings.Symbol,
                        isIsolated=is_isolated,
                        orderId=main_order["orderId"],
                    )
            except Exception as excp:
                exceptions_list.append("Couldn't get Main Order Info")
                logging.error(excp)
                continue
            status = info["status"]
            logging.info("Main Order Status: %s", status)
            if status == "FILLED":
                local_enter_price = float(info["cummulativeQuoteQty"]) / float(
                    info["executedQty"]
                )
                local_enter_price = round(local_enter_price, Settings.TickPriceRounding)
                local_enter_price = float(local_enter_price)
                entering_price_local = local_enter_price
                entering_price = entering_price_local
                logging.info("Main order average fill price = %s", entering_price)
                logging.info("Main order amount in base = %s", info["executedQty"])
                local_quote = quantity_in_base * entering_price
                local_quote = round(local_quote, Settings.TickPriceRounding)
                quantity_in_quote_local = float(local_quote)
                quantity_in_quote = quantity_in_quote_local
                if strategy == 0:
                    tp_local = entering_price * (1 + Settings.ProfitDealRange)
                    tp_local = round(tp_local, Settings.TickPriceRounding)
                    take_profit_price = tp_local
                    sl_local = entering_price * (1 - Settings.LossDealRange)
                    sl_local = round(sl_local, Settings.TickPriceRounding)
                    stop_loss_price = sl_local
                    executed_qty = float(info["executedQty"])
                    val = executed_qty - executed_qty * 0.001
                    val2 = math.floor(
                        val * pow(10, Settings.BaseCurrencyMinAmountRounding)
                    )
                    quantity_in_base_to_sell_local = val2 / pow(
                        10, Settings.BaseCurrencyMinAmountRounding
                    )
                    quantity_in_base_to_sell = quantity_in_base_to_sell_local
                    logging.info(
                        "Quantity in Base to sell = %s", quantity_in_base_to_sell
                    )
                else:
                    tp_local = entering_price * (1 - Settings.ProfitDealRange)
                    tp_local = round(tp_local, Settings.TickPriceRounding)
                    take_profit_price = tp_local
                    sl_local = entering_price * (1 + Settings.LossDealRange)
                    sl_local = round(sl_local, Settings.TickPriceRounding)
                    stop_loss_price = sl_local
                return True
            if status == "EXPIRED":
                logging.error("Main order status: EXPIRED")
                close_all_orders()
                raise SystemExit
            if status == "CANCELED":
                logging.error("Main order was canceled unexpectedly")
                close_all_orders()
                raise SystemExit
    else:
        logging.error("Main order hasn't been executed")
        exceptions_list.append("Main order hasn't been executed")
        return False


def place_main_order():
    global main_order
    try:
        if strategy == 0:
            local_order = client.order_market_buy(
                symbol=Settings.Symbol, quantity=quantity_in_base
            )
            main_order = local_order
        else:
            local_order = client.create_margin_order(
                symbol=Settings.Symbol,
                isIsolated=is_isolated,
                side=enums.SIDE_SELL,
                type=enums.ORDER_TYPE_MARKET,
                quantity=quantity_in_base,
                newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
            )
            main_order = local_order
    except Exception as excp:
        exceptions_list.append("Couldn't place main order")
        exceptions_list.append(excp)
        logging.error(excp)
        return False
    logging.info("Main order placed successfully")
    return True


def close_main_order(cancel_all=False):
    global forced_close_order, forced_closure, exceptions_list
    if cancel_all:
        close_all_orders()
    logging.info("Trying to close main order")
    while True:
        try:
            if strategy == 0:
                local_order = client.order_market_sell(
                    symbol=Settings.Symbol,
                    quantity=round(
                        quantity_in_base_to_sell, Settings.TickPriceRounding
                    ),
                )
                forced_close_order = local_order
            else:
                local_order = client.create_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=is_isolated,
                    side=enums.SIDE_BUY,
                    type=enums.ORDER_TYPE_MARKET,
                    quantity=round(
                        quantity_in_base_to_buy, Settings.BaseCurrencyMinAmountRounding
                    ),
                    newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
                )
                forced_close_order = local_order
                repay_loan()
        except Exception as excp:
            exceptions_list.append("Couldn't close the main order")
            exceptions_list.append(excp)
            logging.error(excp)
            if forced_close_order_status() != "FILLED":
                continue
            logging.info("Forced Close was executed despite the error")
            forced_closure = True
            return True
        else:
            logging.info("Successfully closed MainOrder")
            forced_closure = True
            return True


def forced_close_order_status():
    try:
        if strategy == 0:
            ord_info = client.get_order(
                symbol=Settings.Symbol, orderId=forced_close_order["orderId"]
            )
        else:
            ord_info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=is_isolated,
                orderId=forced_close_order["orderId"],
            )
        st = ord_info["status"]
        logging.info("Forced Close order status: %s", st)
        return st
    except Exception:
        logging.error("Couldn't get forced closure status")
        return None


def place_stop_loss():
    global stop_loss, in_position
    try:
        if strategy == 0:
            sl = client.create_order(
                symbol=Settings.Symbol,
                side=enums.SIDE_SELL,
                type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=enums.TIME_IN_FORCE_FOK,
                quantity=quantity_in_base_to_sell,
                price=stop_loss_price,
                stopPrice=round(
                    stop_loss_price + Settings.SafeDealRangeAmount,
                    Settings.TickPriceRounding,
                ),
                newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
            )
            stop_loss = sl
        else:
            sl = client.create_margin_order(
                symbol=Settings.Symbol,
                isIsolated=is_isolated,
                side=enums.SIDE_BUY,
                type=enums.ORDER_TYPE_STOP_LOSS_LIMIT,
                timeInForce=enums.TIME_IN_FORCE_FOK,
                quantity=quantity_in_base_to_buy,
                price=stop_loss_price,
                stopPrice=round(
                    stop_loss_price - Settings.SafeDealRangeAmount,
                    Settings.TickPriceRounding,
                ),
                newOrderRespType=enums.ORDER_RESP_TYPE_FULL,
            )
            stop_loss = sl
    except Exception as excp:
        exceptions_list.append("Couldn't create stop loss")
        exceptions_list.append(excp)
        logging.error("Couldn't create stop loss")
        close_main_order()
        return False
    logging.info("StopLoss placed")
    in_position = True
    return True


def close_stop_loss():
    attempt = 0
    canceled = False
    while attempt < 3 and not canceled:
        try:
            if strategy == 0:
                client.cancel_order(
                    symbol=Settings.Symbol, orderId=stop_loss["orderId"]
                )
            else:
                client.cancel_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=is_isolated,
                    orderId=stop_loss["orderId"],
                )
        except Exception as excp:
            exceptions_list.append("Couldn't cancel stop-loss")
            exceptions_list.append(excp)
            logging.error(excp)
            attempt += 1
        else:
            logging.info("Canceled stop loss")
            canceled = True
            return True
    return False


def close_all_orders():
    logging.info("Closing all open orders")
    if strategy == 0:
        orders = client.get_open_orders(symbol=Settings.Symbol)
    else:
        orders = client.get_open_margin_orders(
            symbol=Settings.Symbol, isIsolated=is_isolated
        )
    for o in orders:
        if strategy == 0:
            client.cancel_order(symbol=Settings.Symbol, orderId=o["orderId"])
        else:
            client.cancel_margin_order(
                symbol=Settings.Symbol, isIsolated=is_isolated, orderId=o["orderId"]
            )
    logging.info("Closed all open orders")


def price_breakthrough(cp):
    if take_profit is not None:
        if strategy == 0:
            return (
                float(take_profit["price"])
                - Settings.StopLossTakeProfitPassedByCheckAmount
                >= cp
            )
        return (
            float(take_profit["price"]) + Settings.StopLossTakeProfitPassedByCheckAmount
            <= cp
        )
    if stop_loss is not None:
        if strategy == 0:
            return (
                float(stop_loss["price"])
                - Settings.StopLossTakeProfitPassedByCheckAmount
                >= cp
            )
        return (
            float(stop_loss["price"]) + Settings.StopLossTakeProfitPassedByCheckAmount
            <= cp
        )
    return False


def stuck_price(interval, change=0):
    if interval > Settings.StuckPriceTimeout and change == 0:
        exceptions_list.append("Price has stuck")
        logging.warning("Price has stuck")
        return True
    return False


def overstayed_in_deal(start_t, change_pct):
    now = time()
    logging.info("Time Passed = %s", now - start_t)
    if now - start_t > Config.FirstOverstayInDealTimeout and (
        (change_pct > 0.2) if strategy == 0 else (change_pct < -0.2)
    ):
        exceptions_list.append("Staying in the deal beyond first overstay threshold")
        logging.warning("Staying in the deal beyond first overstay threshold")
        return True
    if now - start_t > Config.SecondOverstayInDealTimeout:
        exceptions_list.append("Staying in the deal beyond second overstay threshold")
        logging.warning("Staying in the deal beyond second overstay threshold")
        return True
    return False


def handle_price_break():
    global exceptions_list
    if take_profit is not None:
        status = take_profit_status()
        if status != "FILLED" and forced_close_order is None:
            exceptions_list.append("Price went through takeProfit")
            logging.warning("Price went through takeProfit")
            if not close_main_order():
                logging.error("Couldn't close base asset for a buy->sell flow")
                raise SystemExit
        else:
            return
    else:
        status = stop_loss_status()
        if status != "FILLED" and forced_close_order is None:
            exceptions_list.append("Price went through stopLoss")
            logging.warning("Price went through stopLoss")
            if not close_main_order():
                logging.error("Couldn't close base asset for a buy->sell flow")
                raise SystemExit
        else:
            return


def take_profit_status():
    if strategy == 0:
        order = client.get_order(symbol=Settings.Symbol, orderId=take_profit["orderId"])
    else:
        order = client.get_margin_order(
            symbol=Settings.Symbol,
            isIsolated=is_isolated,
            orderId=take_profit["orderId"],
        )
    st = order["status"]
    logging.info("TakeProfit order status: %s", st)
    return st


def stop_loss_status():
    if strategy == 0:
        order = client.get_order(symbol=Settings.Symbol, orderId=stop_loss["orderId"])
    else:
        order = client.get_margin_order(
            symbol=Settings.Symbol, isIsolated=is_isolated, orderId=stop_loss["orderId"]
        )
    st = order["status"]
    logging.info("StopLoss order status: %s", st)
    return st


async def getting_current_order_info():
    global open_orders, doing_job, take_profit, exceptions_list
    attempts = 0
    success = False
    async_client = None
    try:
        async_client_local = await AsyncClient.create(
            api_key=Settings.API_KEY, api_secret=Settings.API_SECRET
        )
        async_client = async_client_local
    except Exception as excp:
        exceptions_list.append("Couldn't connect AsyncClient2")
        exceptions_list.append(excp)
        logging.error(excp)
        attempts += 1
    else:
        logging.info("Connected AsyncClient2")
        success = True
    if not success:
        logging.error("Couldn't connect asyncClient2")
        if main_order is None:
            await close_connection()
        else:
            st = check_main_order()
            if st == "FILLED":
                if close_main_order():
                    await close_connection()
                else:
                    raise SystemExit
            else:
                await close_connection()
    counter = 0
    while doing_job:
        if take_profit is not None:
            got_info = False
            count_a2 = 0
            order_data = None
            while not got_info and count_a2 < 3:
                try:
                    if strategy == 0:
                        o = await async_client.get_order(
                            symbol=Settings.Symbol, orderId=take_profit["orderId"]
                        )
                        order_data = o
                    else:
                        o = await async_client.get_margin_order(
                            symbol=Settings.Symbol,
                            isIsolated=is_isolated,
                            orderId=take_profit["orderId"],
                        )
                        order_data = o
                except Exception as excp:
                    exceptions_list.append("Couldn't get take profit info")
                    exceptions_list.append(excp)
                    logging.error(excp)
                    count_a2 += 1
                else:
                    got_info = True
            if not got_info:
                continue
            if order_data["status"] == "FILLED" and doing_job:
                logging.info("Take profit has been filled")
                if strategy == 1:
                    repay_loan()
                await close_connection()
                break
            if order_data["status"] == "EXPIRED" and forced_close_order is None:
                exceptions_list.append("Take Profit Expired")
                if not close_main_order():
                    raise SystemExit
                await close_connection()
                break
        elif stop_loss is not None:
            got_info = False
            count_a2 = 0
            order_data = None
            while count_a2 < 3 and not got_info:
                try:
                    if strategy == 0:
                        o = await async_client.get_order(
                            symbol=Settings.Symbol, orderId=stop_loss["orderId"]
                        )
                        order_data = o
                    else:
                        o = await async_client.get_margin_order(
                            symbol=Settings.Symbol,
                            isIsolated=is_isolated,
                            orderId=stop_loss["orderId"],
                        )
                        order_data = o
                except Exception as excp:
                    exceptions_list.append("Couldn't get stop loss info")
                    exceptions_list.append(excp)
                    logging.error(excp)
                    count_a2 += 1
                else:
                    got_info = True
            if not got_info:
                continue
            if order_data["status"] == "FILLED":
                logging.info("StopLoss has been filled")
                if strategy == 1:
                    repay_loan()
                await close_connection()
                break
            if (
                order_data["status"] in ["EXPIRED", "CANCELED"]
                and forced_close_order is None
            ):
                if take_profit is None and not forced_closure:
                    exceptions_list.append("StopLoss expired or canceled unexpectedly")
                    close_main_order()
                    await close_connection()
                    break
        got_orders = False
        count_a3 = 0
        while not got_orders and count_a3 < 3:
            try:
                if strategy == 0:
                    oo = await async_client.get_open_orders(symbol=Settings.Symbol)
                    open_orders = oo
                else:
                    oo = await async_client.get_open_margin_orders(
                        symbol=Settings.Symbol, isIsolated=is_isolated
                    )
                    open_orders = oo
            except Exception as excp:
                exceptions_list.append("Couldn't retrieve open orders")
                exceptions_list.append(excp)
                logging.error(excp)
                count_a3 += 1
            else:
                got_orders = True
        if not got_orders:
            close_main_order()
            await close_connection()
            await async_client.close_connection()
            raise exc.BinanceRequestException
        if not open_orders and doing_job:
            if take_profit is not None and doing_job:
                st = take_profit_status()
                if st == "FILLED":
                    if strategy == 1:
                        repay_loan()
                    await close_connection()
                    break
                if st == "EXPIRED":
                    close_main_order()
                    exceptions_list.append("Take Profit Expired")
                    await close_connection()
                    break
            elif stop_loss is not None and doing_job:
                st = stop_loss_status()
                if st == "FILLED":
                    if strategy == 1:
                        repay_loan()
                    await close_connection()
                    break
                if st == "EXPIRED":
                    close_main_order()
                    exceptions_list.append("Stop Loss Expired")
                    await close_connection()
                    break
            elif main_order is not None:
                logging.info("Neither stopLoss nor takeProfit placed yet")
            else:
                logging.info("Main order has not been placed yet")
        if counter >= 2:
            logging.info("Open Order Info:")
            for o in open_orders:
                logging.info("------------")
                chk_price = float(o["price"])
                if (
                    (chk_price > entering_price)
                    if strategy == 0
                    else (chk_price < entering_price)
                ):
                    logging.info("Take Profit:")
                else:
                    logging.info("Stop Loss:")
                logging.info(o)
            logging.info("------------")
            counter = 0
        else:
            counter += 1
        await asyncio.sleep(0.5)
    await async_client.close_connection()
    logging.info("AsyncClient2 closed")


def check_main_order():
    attempt = 0
    success = False
    ord_data = None
    while attempt < 3 and not success:
        try:
            if strategy == 0:
                o = client.get_order(
                    symbol=Settings.Symbol, orderId=main_order["orderId"]
                )
                ord_data = o
            else:
                o = client.get_margin_order(
                    symbol=Settings.Symbol,
                    isIsolated=is_isolated,
                    orderId=main_order["orderId"],
                )
                ord_data = o
        except Exception as excp:
            logging.error(excp)
            attempt += 1
        else:
            success = True
    if not success:
        return None
    st = ord_data["status"]
    logging.info("Main order status: %s", st)
    return st


def get_exchange_rate(pair):
    try:
        price = client.get_ticker(symbol=pair)["lastPrice"]
    except Exception as excp:
        exceptions_list.append("Couldn't get current exchange rate")
        logging.error(excp)
        return None
    val = float(price)
    logging.info("Current exchange for %s = %s", pair, val)
    return val


def get_spread(symbol):
    try:
        info = client.get_orderbook_ticker(symbol=symbol)
        sp = round(
            float(info["askPrice"]) - float(info["bidPrice"]),
            Settings.TickPriceRounding,
        )
        logging.info("Spread = %s", sp)
        return sp
    except Exception as excp:
        logging.error("Couldn't get %s spread: %s", symbol, excp)
        return -1


def print_last_prices(symbol):
    try:
        info = client.get_symbol_ticker(symbol=symbol)
        logging.info("Price for %s = %s", symbol, info["price"])
    except Exception as excp:
        logging.error("Couldn't get last price for %s: %s", symbol, excp)


def restore_globals():
    global \
        current_price, \
        highest_reached_price, \
        lowest_reached_price, \
        take_profit_price, \
        stop_loss_price
    global \
        entering_price, \
        open_orders, \
        doing_job, \
        client, \
        in_position, \
        quantity_in_base, \
        quantity_in_base_to_sell
    global \
        quantity_in_base_to_buy, \
        main_order, \
        stop_loss, \
        following_stop_loss, \
        take_profit, \
        started_following
    global \
        issue, \
        forced_closure, \
        forced_close_order, \
        exceptions_list, \
        quantity_in_quote, \
        strategy
    global trailing_take_profit_set, repaid, Settings, is_isolated
    trailing_take_profit_set = False
    current_price = 0
    highest_reached_price = 0
    lowest_reached_price = 0
    take_profit_price = 0
    stop_loss_price = 0
    entering_price = 0
    open_orders = {}
    doing_job = True
    client = None
    in_position = False
    quantity_in_base = 0
    main_order = None
    stop_loss = None
    following_stop_loss = None
    take_profit = None
    started_following = False
    issue = Issue.NO_ISSUE
    forced_closure = False
    forced_close_order = None
    exceptions_list = []
    quantity_in_quote = 0
    quantity_in_base_to_sell = 0
    quantity_in_base_to_buy = 0
    strategy = 0
    repaid = False
    Settings = None
    is_isolated = "TRUE"


async def close_connection():
    logging.info("closeConnection")
    close_all_orders()
    global doing_job
    doing_job = False
    print_last_prices(Settings.Symbol)
    await asyncio.sleep(2)
    print_last_prices(Settings.Symbol)


async def space_divider():
    while doing_job:
        logging.debug(".")
        await asyncio.sleep(0.5)


async def main(mainClient, config, strat=0, isolated=True):
    restore_globals()
    global client, exceptions_list, strategy, Settings, is_isolated
    Settings = config
    strategy = strat
    client = mainClient
    is_isolated = "TRUE" if isolated else "FALSE"
    result = {
        "mainOrderId": 0,
        "tradingAmountInBase": 0,
        "tradingAmountInQuote": 0,
        "enteredPrice": 0,
        "stopLossPrice": 0,
        "takeProfitPrice": 0,
        "closedPrice": 0,
        "closedBy": 0,
        "updatedSpread": 0,
        "issues": exceptions_list,
    }
    sp = get_spread(symbol=Settings.Symbol)
    current_spread = round(sp, Settings.TickPriceRounding)
    result["updatedSpread"] = current_spread
    if current_spread == -1:
        exceptions_list.append("Couldn't get the spread")
        logging.error("Couldn't get the spread")
        return result
    if current_spread > Settings.InitialSpread * config.MaxIncreaseInSpreadMultiplier:
        msg = f"Spread increased to {current_spread} from {Settings.InitialSpread}"
        exceptions_list.append(msg)
        logging.error(msg)
        return result
    if not execute_main_order():
        print_last_prices(Settings.Symbol)
        return result
    if not place_stop_loss():
        return result
    try:
        task_price = asyncio.create_task(get_current_price())
        task_orders = asyncio.create_task(getting_current_order_info())
        await task_price
        await task_orders
    except Exception as excp:
        exceptions_list.append(excp)
        logging.error(excp)
        close_main_order(cancel_all=True)
    finally:
        close_all_orders()
    closed_price = 0
    closed_by = ""
    if forced_closure:
        if strategy == 0:
            info = client.get_order(
                symbol=Settings.Symbol, orderId=forced_close_order["orderId"]
            )
        else:
            info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=is_isolated,
                orderId=forced_close_order["orderId"],
            )
        c_price = float(info["cummulativeQuoteQty"]) / float(info["executedQty"])
        closed_price = c_price
        closed_by = "Forced Closure"
    elif take_profit is not None:
        if strategy == 0:
            info = client.get_order(
                symbol=Settings.Symbol, orderId=take_profit["orderId"]
            )
        else:
            info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=is_isolated,
                orderId=take_profit["orderId"],
            )
        c_price = float(info["cummulativeQuoteQty"]) / float(info["executedQty"])
        closed_price = c_price
        closed_by = "Take Profit"
    elif stop_loss is not None:
        if strategy == 0:
            info = client.get_order(
                symbol=Settings.Symbol, orderId=stop_loss["orderId"]
            )
        else:
            info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=is_isolated,
                orderId=stop_loss["orderId"],
            )
        if float(info["executedQty"]) == 0:
            closed_price = 0
        else:
            c_price = float(info["cummulativeQuoteQty"]) / float(info["executedQty"])
            closed_price = c_price
            closed_by = "Stop Loss"
    else:
        if strategy == 0:
            info = client.get_order(
                symbol=Settings.Symbol, orderId=trailing_take_profit["orderId"]
            )
        else:
            info = client.get_margin_order(
                symbol=Settings.Symbol,
                isIsolated=is_isolated,
                orderId=trailing_take_profit["orderId"],
            )
        c_price = float(info["cummulativeQuoteQty"]) / float(info["executedQty"])
        closed_price = c_price
        closed_by = "Traililng Take Profit"
    if main_order is not None:
        result["mainOrderId"] = main_order["orderId"]
        result["tradingAmountInBase"] = quantity_in_base
        result["tradingAmountInQuote"] = quantity_in_quote
        result["enteringPrice"] = entering_price
        result["stopLossPrice"] = stop_loss_price
        result["takeProfitPrice"] = take_profit_price
        result["closedPrice"] = closed_price
        result["closedBy"] = closed_by
        result["exceptions"] = exceptions_list
    logging.info("Deal is done")
    return result


if __name__ == "__main__":
    cfg = Config()
    cli = Client(cfg.API_KEY, cfg.API_SECRET)
    cfg.setSymbol("IOTXUSDT")
    asyncio.run(main(mainClient=cli, config=cfg, strat=1, isolated=False))

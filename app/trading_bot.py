import asyncio
import logging
import os
import signal
import sys
import time
from datetime import datetime
from random import randint
from time import sleep
from typing import Any, Dict

import openpyxl as xl
from binance import Client
from binance import exceptions as exc

from app.config import Config
from app.find_volitile_symbol import main as check_for_volatile_main
from app.up_down_strategy import main as up_down_strategy_main


class TradingBot:
    def __init__(self, config: Config):
        self.config = config
        self.client = Client(config.API_KEY, config.API_SECRET)
        self.wb = xl.load_workbook(self.config.FilePathToSave)
        self.ws_up = self.wb["Long"]
        self.ws_down = self.wb["Short"]
        self.col_map = {
            "main_order_id": "A",
            "start_date_time": "B",
            "start_acc_bal_base": "C",
            "start_acc_bal_quote": "D",
            "start_acc_bal_bnb": "E",
            "end_date_time": "F",
            "end_acc_bal_base": "G",
            "end_acc_bal_quote": "H",
            "end_acc_bal_bnb": "I",
            "symbol": "J",
            "trading_amount_in_quote": "K",
            "trading_amount_in_base": "L",
            "bnb_by_quote": "T",
            "base_by_quote": "Y",
            "entered_price": "AD",
            "stop_loss_at": "AE",
            "take_profit_at": "AF",
            "position_closed_at": "AG",
            "closed_by": "AH",
            "error_col": "AI",
            "profit_deal_range": "AK",
            "loss_deal_range": "AL",
            "initial_caught_change": "AM",
            "tick_price_col": "AN",
            "tick_price_to_price_col": "AO",
            "spread_col": "AP",
            "spread_before_deal_col": "AQ",
        }

    def run(self) -> None:
        logging.info("Bot starting. Process pid = %s", str(self._get_pid()))
        failed_connections = 0
        keep_running = True
        while keep_running:
            start_search_time = time.time()
            result = check_for_volatile_main(Config=self.config)
            if result == -1:
                failed_connections += 1
                logging.warning(
                    "Failed to get most volatile symbol. Attempt #%d",
                    failed_connections,
                )
                if failed_connections >= 5:
                    logging.error(
                        "Could not find a volatile symbol for 5 consecutive tries. Sleeping 120s."
                    )
                    sleep(120)
                    failed_connections = 0
                continue
            failed_connections = 0
            symbol, cur_price, price_change = result
            logging.info(
                "Took %.1f seconds to find symbol: %s",
                time.time() - start_search_time,
                symbol,
            )
            if not self.config.setSymbol(
                symbol=symbol, currentPrice=cur_price, priceChange=price_change
            ):
                logging.info("Skipping symbol %s due to config constraints.", symbol)
                continue
            has_cross = self._check_if_has_cross(symbol)
            is_isolated = False
            if has_cross is True:
                if self._is_borrow_allowed(
                    self.config.BaseCurrency, symbol, is_isolated=False
                ) and self._transfer_funds_to_cross_margin(
                    self.config.QuoteCurrency, self.config.AmountToTransfer
                ):
                    is_isolated = False
                else:
                    continue
            elif has_cross is False:
                if self._transfer_funds_to_isolated_margin(
                    self.config.QuoteCurrency, symbol, self.config.AmountToTransfer
                ):
                    if self._is_borrow_allowed(
                        self.config.BaseCurrency, symbol, is_isolated=True
                    ):
                        is_isolated = True
                    else:
                        self._write_down_bad_symbol(symbol)
                        self._transfer_all_funds_from_isolated_margin(
                            self.config.QuoteCurrency, symbol
                        )
                        continue
                else:
                    continue
            else:
                continue
            deal_count = 0
            while deal_count < self.config.MaxNumOfDealsForACoughtPair:
                user_input = self._safe_input(
                    "Do you wish to continue trading this pair? (y/n)", timeout=2
                )
                if user_input and user_input.lower() == "n":
                    logging.info("User aborted trading on %s.", symbol)
                    keep_running = False
                    break
                x = randint(0, 1)
                if x == 0:
                    self._execute_up_strategy()
                else:
                    self._execute_down_strategy(is_isolated)
                deal_count += 1
            if is_isolated:
                if not self._transfer_all_funds_from_isolated_margin(
                    self.config.QuoteCurrency, symbol
                ):
                    logging.error(
                        "Failed to transfer funds from isolated margin for symbol %s. Exiting.",
                        symbol,
                    )
                    break
            else:
                if not self._transfer_all_funds_from_cross_margin(
                    self.config.QuoteCurrency
                ):
                    logging.error(
                        "Failed to transfer funds from cross margin. Exiting."
                    )
                    break
            ans = self._safe_input(
                "Do you wish the strategy to continue? (y/n)", timeout=6
            )
            if ans and ans.lower() == "n":
                logging.info("User requested to stop the bot.")
                keep_running = False
        logging.info("Bot finished gracefully.")

    def _execute_up_strategy(self) -> None:
        logging.info("Going UP on symbol %s", self.config.Symbol)
        sheet = self.ws_up
        row = self._get_next_empty_row(sheet, start=3)
        self._write_initial_trade_info(sheet, row, is_long=True)
        try:
            start_time = time.time()
            response = asyncio.run(
                up_down_strategy_main(mainClient=self.client, config=self.config)
            )
            end_time = time.time()
            logging.info(
                "Completed 'UP' strategy in %.2f seconds.", (end_time - start_time)
            )
        except Exception as ex:
            logging.exception("Exception raised while executing UP strategy.")
            response = None
            issue_msg = str(ex)
        else:
            issue_msg = None
        self._write_final_trade_info(sheet, row, response, issue_msg)

    def _execute_down_strategy(self, is_isolated: bool) -> None:
        logging.info("Going DOWN on symbol %s", self.config.Symbol)
        sheet = self.ws_down
        row = self._get_next_empty_row(sheet, start=3)
        self._write_initial_trade_info(
            sheet, row, is_long=False, is_isolated=is_isolated
        )
        try:
            start_time = time.time()
            response = asyncio.run(
                up_down_strategy_main(
                    mainClient=self.client,
                    config=self.config,
                    strat=1,
                    isolated=is_isolated,
                )
            )
            end_time = time.time()
            logging.info(
                "Completed 'DOWN' strategy in %.2f seconds.", (end_time - start_time)
            )
        except exc.BinanceAPIException as ex:
            logging.error("BinanceAPIException encountered: %s", ex)
            logging.info("Will skip further trading on this pair.")
            response = None
            issue_msg = str(ex)
        except Exception as ex:
            logging.exception("Exception raised while executing DOWN strategy.")
            response = None
            issue_msg = str(ex)
        else:
            issue_msg = None
        self._write_final_trade_info(sheet, row, response, issue_msg)

    def _write_initial_trade_info(
        self,
        sheet: xl.worksheet.worksheet.Worksheet,
        row: int,
        is_long: bool,
        is_isolated: bool = False,
    ) -> None:
        for attempt in range(3):
            try:
                if is_long:
                    base_bal = float(
                        self.client.get_asset_balance(asset=self.config.BaseCurrency)[
                            "free"
                        ]
                    )
                    quote_bal = float(
                        self.client.get_asset_balance(asset=self.config.QuoteCurrency)[
                            "free"
                        ]
                    )
                else:
                    if is_isolated:
                        info = self.client.get_isolated_margin_account(
                            symbols=self.config.Symbol
                        )
                        base_bal = float(info["assets"][0]["baseAsset"]["free"])
                        quote_bal = float(info["assets"][0]["quoteAsset"]["free"])
                    else:
                        base_bal = self._get_cross_margin_asset_amount(
                            self.config.BaseCurrency
                        )
                        quote_bal = self._get_cross_margin_asset_amount(
                            self.config.QuoteCurrency
                        )
                bnb_bal = float(self.client.get_asset_balance(asset="BNB")["free"])
                sheet[self.col_map["start_date_time"] + str(row)].value = datetime.now()
                sheet[self.col_map["start_acc_bal_base"] + str(row)].value = base_bal
                sheet[self.col_map["start_acc_bal_quote"] + str(row)].value = quote_bal
                sheet[self.col_map["start_acc_bal_bnb"] + str(row)].value = bnb_bal
                sheet[
                    self.col_map["profit_deal_range"] + str(row)
                ].value = self.config.ProfitDealRange
                sheet[
                    self.col_map["loss_deal_range"] + str(row)
                ].value = self.config.LossDealRange
                sheet[
                    self.col_map["tick_price_to_price_col"] + str(row)
                ].value = self.config.TickPriceToCurrentPrice
                sheet[
                    self.col_map["initial_caught_change"] + str(row)
                ].value = self.config.InitialFluctuation
                sheet[self.col_map["symbol"] + str(row)].value = self.config.Symbol
                sheet[
                    self.col_map["tick_price_col"] + str(row)
                ].value = self.config.TickPrice
                sheet[
                    self.col_map["spread_col"] + str(row)
                ].value = self.config.InitialSpread
                bnb_ticker = (
                    self.client.get_ticker(symbol="BNBBUSD")["lastPrice"]
                    if is_long
                    else self.client.get_ticker(symbol="BNBUSDT")["lastPrice"]
                )
                base_ticker = self.client.get_ticker(symbol=self.config.Symbol)[
                    "lastPrice"
                ]
                sheet[self.col_map["bnb_by_quote"] + str(row)].value = bnb_ticker
                sheet[self.col_map["base_by_quote"] + str(row)].value = base_ticker
                self.wb.save(self.config.FilePathToSave)
            except Exception as ex:
                logging.error(
                    "Failed to write initial info to file (attempt %d): %s",
                    attempt + 1,
                    ex,
                )
                time.sleep(1)
            else:
                logging.info(
                    "Successfully wrote initial trade info to row %d for %s strategy.",
                    row,
                    "Long" if is_long else "Short",
                )
                return
        logging.critical("Exceeded max attempts to write initial trade info. Aborting.")
        raise RuntimeError("Could not write initial trade info to Excel.")

    def _write_final_trade_info(
        self,
        sheet: xl.worksheet.worksheet.Worksheet,
        row: int,
        response: Optional[Dict[str, Any]],
        issue_msg: Optional[str],
    ) -> None:
        for attempt in range(3):
            try:
                base_bal = float(
                    self.client.get_asset_balance(asset=self.config.BaseCurrency)[
                        "free"
                    ]
                )
                quote_bal = float(
                    self.client.get_asset_balance(asset=self.config.QuoteCurrency)[
                        "free"
                    ]
                )
                bnb_bal = float(self.client.get_asset_balance(asset="BNB")["free"])
                sheet[self.col_map["end_date_time"] + str(row)].value = datetime.now()
                sheet[self.col_map["end_acc_bal_base"] + str(row)].value = base_bal
                sheet[self.col_map["end_acc_bal_quote"] + str(row)].value = quote_bal
                sheet[self.col_map["end_acc_bal_bnb"] + str(row)].value = bnb_bal
                if issue_msg is None and response is not None:
                    sheet[
                        self.col_map["main_order_id"] + str(row)
                    ].value = response.get("mainOrderId")
                    sheet[
                        self.col_map["trading_amount_in_base"] + str(row)
                    ].value = response.get("tradingAmountInBase")
                    sheet[
                        self.col_map["trading_amount_in_quote"] + str(row)
                    ].value = response.get("tradingAmountInQuote")
                    sheet[
                        self.col_map["entered_price"] + str(row)
                    ].value = response.get("enteredPrice")
                    sheet[self.col_map["stop_loss_at"] + str(row)].value = response.get(
                        "stopLossPrice"
                    )
                    sheet[
                        self.col_map["take_profit_at"] + str(row)
                    ].value = response.get("takeProfitPrice")
                    sheet[
                        self.col_map["position_closed_at"] + str(row)
                    ].value = response.get("closedPrice")
                    sheet[self.col_map["closed_by"] + str(row)].value = response.get(
                        "closedBy"
                    )
                    sheet[
                        self.col_map["spread_before_deal_col"] + str(row)
                    ].value = response.get("updatedSpread")
                error_report = "Broke Program:"
                if issue_msg is not None:
                    error_report += f"\n{issue_msg}"
                error_report += "\nInternal Errors:\n"
                if response is not None and "issues" in response:
                    for err in response["issues"]:
                        error_report += f"{err}\n"
                sheet[self.col_map["error_col"] + str(row)].value = error_report
                self.wb.save(self.config.FilePathToSave)
            except Exception as ex:
                logging.error(
                    "Failed to write final info to file (attempt %d): %s",
                    attempt + 1,
                    ex,
                )
                time.sleep(1)
            else:
                logging.info("Successfully wrote final trade info to row %d.", row)
                return
        logging.critical("Exceeded max attempts to write final trade info. Aborting.")
        raise RuntimeError("Could not write final trade info to Excel.")

    def _get_next_empty_row(
        self, sheet: xl.worksheet.worksheet.Worksheet, start: int = 3
    ) -> int:
        row_idx = start
        while sheet["A" + str(row_idx)].value is not None:
            row_idx += 1
        return row_idx

    def _safe_input(self, prompt: str, timeout: int = 5) -> Optional[str]:
        def interrupted(signum, frame):
            raise TimeoutError("User input timed out.")

        old_handler = signal.signal(signal.SIGALRM, interrupted)
        signal.alarm(timeout)
        try:
            user_input = input(f"{prompt}\n")
        except TimeoutError:
            logging.info("User input timed out after %d seconds, continuing.", timeout)
            user_input = None
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
        return user_input

    def _check_if_has_cross(self, symbol: str) -> Optional[bool]:
        for attempt in range(3):
            try:
                self.client.get_margin_symbol(symbol=symbol)
                logging.info("Symbol %s has Cross Margin available.", symbol)
                return True
            except exc.BinanceAPIException:
                logging.info("Symbol %s does NOT have Cross Margin.", symbol)
                return False
            except Exception as ex:
                logging.error(
                    "Error checking cross margin for symbol %s: %s", symbol, ex
                )
                time.sleep(1)
        logging.critical(
            "Could not verify cross margin availability for %s after 3 attempts.",
            symbol,
        )
        return None

    def _is_borrow_allowed(self, asset: str, symbol: str, is_isolated: bool) -> bool:
        try:
            self.client.create_margin_loan(
                asset=asset,
                amount="0.00000001",
                isIsolated="TRUE" if is_isolated else "FALSE",
                symbol=symbol,
            )
            logging.info(
                "Borrowing is allowed for %s on symbol %s. isIsolated=%s",
                asset,
                symbol,
                is_isolated,
            )
            return True
        except exc.BinanceAPIException as ex:
            logging.error(
                "Borrow not allowed for %s on %s (isIsolated=%s). Error: %s",
                asset,
                symbol,
                is_isolated,
                ex,
            )
            return False
        except Exception:
            logging.exception(
                "Unexpected error in _is_borrow_allowed() for asset=%s, symbol=%s.",
                asset,
                symbol,
            )
            sys.exit(1)

    def _transfer_funds_to_isolated_margin(
        self, asset: str, symbol: str, amount: float
    ) -> bool:
        try:
            self.client.transfer_spot_to_isolated_margin(
                asset=asset, symbol=symbol, amount=amount
            )
            logging.info(
                "Transferred %.4f %s to Isolated Margin: %s", amount, asset, symbol
            )
            return True
        except exc.BinanceAPIException as ex:
            logging.error("Failed to transfer to isolated margin: %s", ex)
            if ex.code == -3052:
                logging.info(
                    "Isolated pair for %s is deactivated. Activating now...", symbol
                )
                if self._activate_isolated_pair(symbol):
                    try:
                        self.client.transfer_spot_to_isolated_margin(
                            asset=asset, symbol=symbol, amount=amount
                        )
                        logging.info(
                            "Transferred after activation: %.4f %s to %s",
                            amount,
                            asset,
                            symbol,
                        )
                        return True
                    except Exception as sub_ex:
                        logging.error("Failed second attempt transfer: %s", sub_ex)
                        return False
            return False
        except Exception as ex:
            logging.error("Unexpected error transferring to isolated margin: %s", ex)
            return False

    def _activate_isolated_pair(self, symbol: str) -> bool:
        try:
            self.client.enable_isolated_margin_account(symbol=symbol)
            logging.info("Isolated margin account enabled for symbol %s.", symbol)
            return True
        except exc.BinanceAPIException as ex:
            logging.error("Binance API error while enabling isolated margin: %s", ex)
            self._deactivate_bad_symbols()
            try:
                self.client.enable_isolated_margin_account(symbol=symbol)
                logging.info(
                    "Successfully enabled isolated margin after forced deactivation."
                )
                return True
            except Exception as ex2:
                logging.error(
                    "Still couldn't enable isolated margin for %s: %s", symbol, ex2
                )
                return False
        except Exception as ex:
            logging.error("Error enabling isolated margin for %s: %s", symbol, ex)
            return False

    def _deactivate_bad_symbols(self) -> None:
        bad_symbols = []
        try:
            with open("./IsolatedSymbolsBadList.txt", "r") as f:
                lines = f.readlines()
                for line in lines:
                    splitted = line.strip().split("-")
                    if len(splitted) == 2:
                        bad_symbols.append(splitted[1])
        except FileNotFoundError:
            logging.info("No IsolatedSymbolsBadList.txt found to deactivate.")
            return
        except Exception as ex:
            logging.error(
                "Something went wrong reading IsolatedSymbolsBadList.txt: %s", ex
            )
        for sym in bad_symbols:
            try:
                self.client.disable_isolated_margin_account(symbol=sym)
                logging.info("Disabled isolated margin for symbol %s.", sym)
            except Exception as ex:
                logging.error(
                    "Could not disable isolated margin for symbol %s: %s", sym, ex
                )
                self._transfer_all_funds_from_isolated_margin(
                    asset=sym.replace("USDT", ""), symbol=sym
                )

    def _transfer_all_funds_from_isolated_margin(self, asset: str, symbol: str) -> bool:
        try:
            amount = self._get_isolated_margin_asset_amount(symbol)
            self.client.transfer_isolated_margin_to_spot(
                asset=asset, symbol=symbol, amount=amount
            )
            logging.info(
                "Transferred all %s from isolated margin %s -> spot.", asset, symbol
            )
            return True
        except exc.BinanceAPIException as ex:
            logging.error("Binance API error transferring from isolated margin: %s", ex)
            if ex.code == -11015:
                logging.warning(
                    "Unpaid loan preventing transfer of %s from %s. Attempting to repay...",
                    asset,
                    symbol,
                )
                base_asset = symbol.replace("USDT", "")
                base_balance = self._get_spot_asset_amount(base_asset)
                if base_balance == 0:
                    adjusted = round(amount - 0.0001, 8)
                    logging.info("Adjusted transfer to avoid dust: %.8f", adjusted)
                    try:
                        self.client.transfer_isolated_margin_to_spot(
                            asset=asset, symbol=symbol, amount=adjusted
                        )
                        return True
                    except Exception as sub_ex:
                        logging.error(
                            "Still couldn't transfer after dust adjustment: %s", sub_ex
                        )
                        return False
                self._transfer_funds_to_isolated_margin(
                    base_asset, symbol, base_balance
                )
                if not self._repay_loan(
                    base_asset, symbol, base_balance, is_isolated=True
                ):
                    return False
                try:
                    self.client.transfer_isolated_margin_to_spot(
                        asset=asset, symbol=symbol, amount=amount
                    )
                    logging.info(
                        "Transferred all %s from isolated margin after loan repay.",
                        asset,
                    )
                    return True
                except Exception as sub_ex:
                    logging.error("Couldn't transfer after loan repay: %s", sub_ex)
                    return False
            return False
        except Exception as ex:
            logging.error("Unexpected error transferring from isolated margin: %s", ex)
            return False

    def _transfer_funds_to_cross_margin(self, asset: str, amount: float) -> bool:
        try:
            self.client.transfer_spot_to_margin(asset=asset, amount=amount)
            logging.info("Transferred %.4f %s to cross margin.", amount, asset)
            return True
        except Exception as ex:
            logging.error(
                "Could not transfer %.4f %s to cross margin: %s", amount, asset, ex
            )
            return False

    def _transfer_all_funds_from_cross_margin(self, asset: str) -> bool:
        try:
            amount = self._get_cross_margin_asset_amount(asset)
            self.client.transfer_margin_to_spot(asset=asset, amount=amount)
            logging.info(
                "Transferred all %s (%.8f) from cross margin to Spot.", asset, amount
            )
            return True
        except Exception as ex:
            logging.error("Error transferring all %s from cross margin: %s", asset, ex)
            return False

    def _repay_loan(
        self, asset: str, symbol: str, amount: float, is_isolated: bool
    ) -> bool:
        try:
            self.client.repay_margin_loan(
                asset=asset,
                amount=amount,
                isIsolated="TRUE" if is_isolated else "FALSE",
                symbol=symbol,
            )
            logging.info(
                "Repaid margin loan for asset=%s, symbol=%s, amount=%.8f.",
                asset,
                symbol,
                amount,
            )
            return True
        except Exception as ex:
            logging.error(
                "Failed to repay the loan for %s on %s: %s", asset, symbol, ex
            )
            return False

    def _write_down_bad_symbol(self, symbol: str) -> None:
        try:
            with open("./IsolatedSymbolsBadList.txt", "a") as f:
                now_str = datetime.now().strftime("%d:%H:%M")
                f.write(f"{now_str}-{symbol}\n")
            logging.info("Wrote down bad symbol: %s", symbol)
        except Exception as ex:
            logging.error("Could not write bad symbol %s to file: %s", symbol, ex)

    def _get_spot_asset_amount(self, asset: str) -> float:
        try:
            balance_info = self.client.get_asset_balance(asset=asset)
            free_amt = float(balance_info["free"])
            logging.info("Spot balance of %s = %.8f", asset, free_amt)
            return free_amt
        except Exception as ex:
            logging.error("Couldn't retrieve spot balance for %s: %s", asset, ex)
            return 0.0

    def _get_cross_margin_asset_amount(self, asset: str) -> float:
        try:
            cross_info = self.client.get_margin_account()
            for asset_info in cross_info["userAssets"]:
                if asset_info["asset"] == asset:
                    free_amt = float(asset_info["free"])
                    logging.info("Cross margin balance of %s = %.8f", asset, free_amt)
                    return free_amt
            return 0.0
        except Exception as ex:
            logging.error(
                "Couldn't retrieve cross margin balance for %s: %s", asset, ex
            )
            return 0.0

    def _get_isolated_margin_asset_amount(self, symbol: str) -> float:
        try:
            info = self.client.get_isolated_margin_account()
            for pair in info["assets"]:
                if pair["symbol"] == symbol:
                    quote_amt = float(pair["quoteAsset"]["free"])
                    logging.info(
                        "Isolated margin quote balance of %s = %.8f", symbol, quote_amt
                    )
                    return quote_amt
            return 0.0
        except Exception as ex:
            logging.error(
                "Couldn't retrieve isolated margin balance for %s: %s", symbol, ex
            )
            return 0.0

    @staticmethod
    def _get_pid() -> int:
        return os.getpid()

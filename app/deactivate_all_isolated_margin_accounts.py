import logging
import time

from binance import exceptions as exc
from binance.client import Client
from config import Config

config = Config()
client = Client(api_key=config.API_KEY, api_secret=config.API_SECRET)


def get_isolated_margin_asset_amount(symbol, return_quote_asset=True):
    try:
        cfg = Config()
        cl = Client(api_key=cfg.API_KEY, api_secret=cfg.API_SECRET)
        info = cl.get_isolated_margin_account()
        for asset_info in info["assets"]:
            balance = float(
                asset_info["quoteAsset" if return_quote_asset else "baseAsset"][
                    "netAsset"
                ]
            )
            return balance
    except Exception as ex:
        logging.error(ex)
        raise SystemExit
    raise SystemExit


def get_spot_asset_amount(asset):
    try:
        info = client.get_asset_balance(asset)
    except Exception as ex:
        logging.error(ex)
        raise SystemExit
    logging.info(f"{asset} balance = {info['free']}")
    return float(info["free"])


def transfer_funds_from_isolated_margin(asset, symbol):
    try:
        amount = get_isolated_margin_asset_amount(
            symbol=symbol, return_quote_asset=(asset == "USDT")
        )
        client.transfer_isolated_margin_to_spot(
            asset=asset, symbol=symbol, amount=amount
        )
    except Exception as ex:
        if asset != "USDT":
            logging.error(ex)
            base_asset = symbol.replace("USDT", "")
            base_asset_amount = get_spot_asset_amount(base_asset)
            transfer_funds_to_isolated_margin(base_asset, symbol, base_asset_amount)
            if not repay_loan(base_asset, symbol, base_asset_amount, True):
                logging.error(ex)
                return False
            if transfer_funds_from_isolated_margin(asset, symbol):
                return True
            return False
        return False
    logging.info(f"Successfully transferred all {asset} from Isolated to Spot")
    return True


def deactivate_bad_symbols():
    bad_symbols = []
    try:
        with open("./IsolatedSymbolsBadList.txt", "r") as file:
            for line in file:
                if line.strip():
                    _, symbol = line.split("-")
                    bad_symbols.append(symbol.strip())
    except Exception as ex:
        logging.error(ex)
    for symbol in bad_symbols:
        try:
            client.disable_isolated_margin_account(symbol=symbol)
        except Exception as ex:
            logging.error(ex)
        else:
            logging.info(f"Successfully disabled {symbol}")


def activate_isolated_pair(symbol):
    try:
        client.enable_isolated_margin_account(symbol=symbol)
    except exc.BinanceAPIException:
        deactivate_bad_symbols()
        try:
            client.enable_isolated_margin_account(symbol=symbol)
        except Exception as ex:
            logging.error(ex)
            return False
        return True
    except Exception as ex:
        logging.error(ex)
        return False
    logging.info("Successfully activated isolated pair")
    return True


def transfer_funds_to_isolated_margin(asset, symbol, amount):
    try:
        client.transfer_spot_to_isolated_margin(
            asset=asset, symbol=symbol, amount=amount
        )
    except exc.BinanceAPIException as ex:
        logging.error(ex)
        if not activate_isolated_pair(symbol):
            return False
        try:
            client.transfer_spot_to_isolated_margin(
                asset=asset, symbol=symbol, amount=amount
            )
        except Exception as err:
            logging.error(err)
            return False
        logging.info(f"Successfully transferred funds to Isolated Margin {symbol}")
        return True
    except Exception as ex:
        logging.error(ex)
        return False
    logging.info(f"Successfully transferred funds to Isolated Margin {symbol}")
    return True


def repay_loan(asset, symbol, amount, is_isolated):
    try:
        client.repay_margin_loan(
            asset=asset,
            amount=amount,
            isIsolated="TRUE" if is_isolated else "FALSE",
            symbol=symbol,
        )
    except Exception as ex:
        logging.error(ex)
        return False
    logging.info("Successfully paid the loan back")
    return True


info = client.get_isolated_margin_account()
current_time = time.localtime()
logging.info(f"Time now: {time.strftime('%H:%M:%S', current_time)}")

for pair in info["assets"]:
    if pair["enabled"]:
        try:
            client.disable_isolated_margin_account(symbol=pair["symbol"])
        except Exception as ex:
            logging.error(ex)
            transfer_funds_from_isolated_margin(
                pair["symbol"].replace("USDT", ""), pair["symbol"]
            )
            transfer_funds_from_isolated_margin("USDT", pair["symbol"])
            try:
                client.disable_isolated_margin_account(symbol=pair["symbol"])
                logging.info(f"Successfully disabled {pair['symbol']}")
            except Exception:
                pass
            logging.error(ex)
        else:
            logging.info(f"Successfully disabled {pair['symbol']}")

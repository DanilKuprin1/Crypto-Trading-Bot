import logging
import time

from binance import exceptions as exc
from binance.client import Client

from config import Config

config = Config()
client = Client(api_key=config.API_KEY, api_secret=config.API_SECRET)


def getIsolatedMarginAssetAmount(symbol, returnQuoteAsset=True):
    try:
        c = Config()
        cl = Client(api_key=c.API_KEY, api_secret=c.API_SECRET)
        info = cl.get_isolated_margin_account()
        for pair in info["assets"]:
            balance = float(
                pair["quoteAsset" if returnQuoteAsset else "baseAsset"]["netAsset"]
            )
            return balance
    except Exception as e:
        logging.error(e)
        raise SystemExit
    else:
        raise SystemExit


def getSpotAssetAmount(asset):
    try:
        info = client.get_asset_balance("DREP")
    except Exception as e:
        logging.error(e)
        raise SystemExit
    else:
        logging.info(f"{asset} balance = {info['free']}")
        return float(info["free"])


def transferFundsFromIsolatedMargin(asset, symbol):
    try:
        amount = getIsolatedMarginAssetAmount(
            symbol=symbol, returnQuoteAsset=(True if asset == "USDT" else False)
        )
        client.transfer_isolated_margin_to_spot(
            asset=asset, symbol=symbol, amount=amount
        )
    except Exception as e:
        if asset != "USDT":
            logging.error(e)
            baseAsset = symbol.replace("USDT", "")
            baseAssetAmount = getSpotAssetAmount(baseAsset)
            transferFundsToIsolatedMargin(baseAsset, symbol, baseAssetAmount)
            r = repayLoan(baseAsset, symbol, baseAssetAmount, True)
            if not r:
                logging.error(e)
                return False
            else:
                if transferFundsFromIsolatedMargin(asset, symbol):
                    return True
                return False
        else:
            return False
    else:
        logging.info(f"Successfully transferred all {asset} from Isolated to Spot")
        return True


def deactivateBadSymbols():
    badSybmols = []
    try:
        with open("./IsolatedSymbolsBadList.txt", "r") as f:
            lines = f.readlines()
            for line in lines:
                spl = line.split("-")
                sym = spl[1].replace("\n", "")
                badSybmols.append(sym)
    except Exception as e:
        logging.error(e)
    for s in badSybmols:
        try:
            client.disable_isolated_margin_account(symbol=s)
        except Exception as ex:
            logging.error(ex)
        else:
            logging.info(f"Successfully disabled {s}")


def activateIsolatedPair(symbol):
    try:
        client.enable_isolated_margin_account(symbol=symbol)
    except exc.BinanceAPIException:
        deactivateBadSymbols()
        try:
            client.enable_isolated_margin_account(symbol=symbol)
        except Exception as ex:
            logging.error(ex)
            return False
        else:
            return True
    except Exception as e:
        logging.error(e)
        return False
    else:
        logging.info("Successfully activated isolated pair")
        return True


def transferFundsToIsolatedMargin(asset, symbol, amount):
    try:
        client.transfer_spot_to_isolated_margin(
            asset=asset, symbol=symbol, amount=amount
        )
    except exc.BinanceAPIException as e:
        logging.error(e)
        if not activateIsolatedPair(symbol):
            return False
        else:
            try:
                client.transfer_spot_to_isolated_margin(
                    asset=asset, symbol=symbol, amount=amount
                )
            except Exception as ex:
                logging.error(ex)
                return False
            else:
                logging.info(
                    f"Successfully transferred funds to Isolated Margin {symbol}"
                )
                return True
    except Exception as e:
        logging.error(e)
        return False
    else:
        logging.info(f"Successfully transferred funds to Isolated Margin {symbol}")
        return True


def repayLoan(asset, symbol, amount, isIsolated):
    try:
        client.repay_margin_loan(
            asset=asset,
            amount=amount,
            isIsolated="TRUE" if isIsolated else "FALSE",
            symbol=symbol,
        )
    except Exception as e:
        logging.error(e)
        return False
    else:
        logging.info("Successfully paid the loan back")
        return True


info = client.get_isolated_margin_account()
t = time.localtime()
logging.info(f"Time now: {time.strftime('%H:%M:%S', t)}")
for pair in info["assets"]:
    if pair["enabled"]:
        try:
            client.disable_isolated_margin_account(symbol=pair["symbol"])
        except Exception as e:
            logging.error(e)
            transferFundsFromIsolatedMargin(
                pair["symbol"].replace("USDT", ""), pair["symbol"]
            )
            transferFundsFromIsolatedMargin("USDT", pair["symbol"])
            try:
                client.disable_isolated_margin_account(symbol=pair["symbol"])
                logging.info(f"Successfully disabled {pair['symbol']}")
            except Exception:
                pass
            logging.error(e)
        else:
            logging.info(f"Successfully disabled {pair['symbol']}")

import time
from datetime import datetime
from binance.client import Client
from config import Config

def check(client):
    chosen_symbols = set()
    attempt = 0
    success = False
    info = None
    while not success and attempt < 3:
        try:
            info = client.get_all_isolated_margin_symbols()
        except Exception as ex:
            print(ex)
            print("\n_____Couldn't get all isolated margin symbols_____\n")
            attempt += 1
        else:
            success = True
    if not success:
        return -1
    symbol_volumes = get_volumes()
    if symbol_volumes == -1:
        return -1
    bad_symbols_dict = get_bad_symbols()
    rewrite_bad_symbols(bad_symbols_dict)
    bad_symbols = set(bad_symbols_dict)
    for symb in info:
        if (
            symb["symbol"] in symbol_volumes
            and symb["symbol"].endswith("USDT")
            and symb["symbol"] not in bad_symbols
            and symbol_volumes[symb["symbol"]] > Config.MinPairVolumeInUSDTToTradeThePair
        ):
            chosen_symbols.add(symb["symbol"])
    past_tickers = {}
    while True:
        try:
            info = client.get_all_tickers()
        except Exception as ex:
            print(ex)
            return -1
        else:
            t = time.localtime()
            print(f"\nGot new tickers! Time now: {time.strftime('%H:%M:%S', t)}")
        if not past_tickers:
            for ticker in info:
                past_tickers[ticker["symbol"]] = float(ticker["price"])
            continue
        for ticker in info:
            old_price = past_tickers[ticker["symbol"]]
            new_price = float(ticker["price"])
            price_change = abs(old_price - new_price) / old_price
            if price_change > Config.MinRequiredChangeForStartingSettingPair:
                if (
                    ticker["symbol"] in chosen_symbols
                    and ticker["symbol"] not in bad_symbols
                    and ticker["symbol"] not in Config.UnpleasantPairs
                ):
                    print(
                        "\n\n---------------------------------------------\n\n"
                        f"The big one here: {ticker['symbol']}",
                        end=""
                    )
                    return ticker["symbol"], new_price, price_change
            past_tickers[ticker["symbol"]] = new_price
        time.sleep(Config.TimeBetweenGettingTickers)

def get_volumes():
    config = Config()
    client = Client(api_key=config.API_KEY, api_secret=config.API_SECRET)
    success = False
    attempt = 0
    while not success and attempt < 3:
        try:
            info = client.get_ticker()
        except:
            print("Couldn't instantly get 24h tickers!!!")
            attempt += 1
        else:
            success = True
    if not success:
        print("Still couldn't get 24hour tickets")
        return -1
    return {symb["symbol"]: float(symb["quoteVolume"]) for symb in info}

def write_down_bad_symbol(symbol):
    try:
        with open("./IsolatedSymbolsBadList.txt", "a") as f:
            now = datetime.now().strftime("%d:%H:%M")
            f.write(f"{now}-{symbol}\n")
    except Exception as ex:
        print(ex)
        print(f"Couldn't add {symbol} to BadList")

def get_bad_symbols():
    bad_symbols = {}
    try:
        with open("./IsolatedSymbolsBadList.txt", "r") as f:
            now_minutes = get_time_in_minutes(datetime.now().strftime("%d:%H:%M"))
            for line in f:
                if not line.strip():
                    continue
                time_str, symbol = line.strip().split("-")
                diff = now_minutes - get_time_in_minutes(time_str)
                if 0 <= diff <= 1440:
                    bad_symbols[symbol] = time_str
    except Exception as ex:
        print(ex)
        print("\n______Error occured while getting Bad Symbols from file______\n")
        exit()
    return bad_symbols

def rewrite_bad_symbols(bad_symbols):
    try:
        with open("./IsolatedSymbolsBadList.txt", "w") as f:
            for symbol, time_str in bad_symbols.items():
                f.write(f"{time_str}-{symbol}\n")
    except Exception as ex:
        print(ex)
        print(f"Couldn't add {symbol} to BadList")

def get_time_in_minutes(timestamp):
    d, h, m = map(float, timestamp.split(":"))
    return d * 24 * 60 + h * 60 + m

def main(config):
    try:
        client = Client(config.API_KEY, config.API_SECRET)
        return check(client)
    except Exception as ex:
        print(f"\n{ex}")
        print("______Something went wrong when trying to get most volatile________")
        return -1

if __name__ == "__main__":
    config = Config()
    while True:
        main(config)

from Config import Config
from binance.client import Client
import time
from datetime import datetime
from datetime import date


def check(client):
    chosenSymbols = set() 
    attempt = 0
    success = False
    info = None
    while success == False and attempt < 3:
        try:
            info = client.get_all_isolated_margin_symbols()
        except Exception as ex:
            print(ex)
            print("\n_____Couldn't get all isolated margin symbols_____\n")
            attempt += 1
        else:
            success = True
    if success == False:
        return -1

    symbolVolumes = getVolumes()
    if symbolVolumes == -1:
        return -1
    badSymbolsDictionary = getBadSymbols()
    rewriteBadSymbols(badSymbols=badSymbolsDictionary)
    badSymbols = set()
    for symbol in badSymbolsDictionary:
        badSymbols.add(symbol)

    for symb in info:
        if symb['symbol'] in symbolVolumes and symb["symbol"].endswith('USDT') and not(symb['symbol'] in badSymbols):
            if symbolVolumes[symb['symbol']]>Config.MinPairVolumeInUSDTToTradeThePair:
                chosenSymbols.add(symb['symbol'])
                continue
            
    pastTickers = {}
    while True:
        try:
            info = client.get_all_tickers()
        except Exception as ex:
            print(ex)
            return -1
        else:
            t = time.localtime()
            print(f"\nGot new tickers! Time now: {time.strftime('%H:%M:%S', t)}")

        if pastTickers == {}:
            for ticker in info:
                pastTickers[ticker["symbol"]] = float(ticker['price'])
            continue

        for ticker in info:
            priceChange = abs((pastTickers[ticker["symbol"]]-float(ticker["price"])))/pastTickers[ticker["symbol"]]
            if priceChange >(Config.MinRequiredChangeForStartingSettingPair):
                if ticker['symbol'] in chosenSymbols and not(ticker['symbol'] in badSymbols) and not(ticker["symbol"] in Config.UnpleasantPairs):
                    print("\n\n---------------------------------------------\n\nThe big one here: {}".format(ticker["symbol"]), end = "")
                    return (ticker["symbol"],float(ticker['price']),priceChange)
            pastTickers[ticker["symbol"]] = float(ticker['price'])
        time.sleep(Config.TimeBetweenGettingTickers)

def getVolumes():
    config = Config()
    client = Client(api_key=config.API_KEY, api_secret=config.API_SECRET)
    success = False
    attempt = 0
    while success == False and attempt<3:
        try:
            info = client.get_ticker()
        except:
            print("Couldn't instantly get 24h tickers!!!")
            attempt+=1
        else:
            success = True
    if success == False:
        print("Still couldn't get 24hour tickets")
        return -1
    
    symbolVolumes = {}
    for symb in info:
        symbolVolumes[symb['symbol']] = float(symb['quoteVolume'])
    return symbolVolumes

def writeDownBadSymbol(symbol):
    try:
        f = open("./IsolatedSymbolsBadList.txt","a")
        timeNow = datetime.now()
        timeToWrite = timeNow.strftime("%d:%H:%M")
        stringToWrite = timeToWrite + "-" + symbol + "\n"
        f.write(stringToWrite)
    except Exception as ex:
        print(ex)
        print("Couldn't add {} to BadList".format(symbol))
    finally:
        f.close()

def getBadSymbols():
    badSybmols = {}
    try:
        f = open("./IsolatedSymbolsBadList.txt","r")
        timeInMinutesNow = getTimeInMinutes(datetime.now().strftime("%d:%H:%M"))
        lines = f.readlines()
        for line in lines:
            if line == "\n":
                continue
            lineParts = line.split("-")
            symbolTimeInMinutes = getTimeInMinutes(lineParts[0])
            timeDifference = timeInMinutesNow-symbolTimeInMinutes
            if (timeDifference)<=1440 and (timeDifference)>=0:
                badSybmols[lineParts[1].replace("\n","")] = lineParts[0]
    except Exception as ex:
        print(ex)
        print("\n______Error occured while getting Bad Symbols from file______\n")
        exit()
    finally:
        f.close()
    return badSybmols

def rewriteBadSymbols(badSymbols):
        try:
            f = open("./IsolatedSymbolsBadList.txt","w")
            for symbol in badSymbols:
                stringToWrite = badSymbols[symbol] + "-" + symbol + "\n"
                f.write(stringToWrite)
        except Exception as ex:
            print(ex)
            print("Couldn't add {} to BadList".format(symbol))
        finally:
            f.close()

def getTimeInMinutes(time):
    timeNowSplitted = time.split(":")
    totalNowInMinutes = float(timeNowSplitted[0])*24*60
    totalNowInMinutes += float(timeNowSplitted[1])*60
    totalNowInMinutes += float(timeNowSplitted[2])
    return totalNowInMinutes


def main(Config):
    try:
        client = Client(Config.API_KEY,Config.API_SECRET)
        return check(client)
    except Exception as ex:
        print("\n"+str(ex))
        print("______Something went wrong when trying to get most volatile________")
        return -1



if __name__ == "__main__":
    config = Config()
    while True:
        main(Config=config)
from Config import Config
from binance.client import Client
import time
from binance import exceptions as exc

config = Config()
client = Client(api_key=config.API_KEY, api_secret=config.API_SECRET)

def getIsolatedMarginAssetAmount(symbol, returnQuoteAsset = True):
    try:
        config = Config()
        client = Client(api_key=config.API_KEY, api_secret=config.API_SECRET)
        info = client.get_isolated_margin_account()
        symbolBalanceInQuote = 0
        for pair in info['assets']:

                symbolBalanceInQuote =  float(pair['quoteAsset' if returnQuoteAsset else "baseAsset"]['netAsset'])
                return symbolBalanceInQuote
    except:
        print("\nCouldn't get {} balance\n".format(symbol))
        exit()
    else:
        print("\nSomething went wrong in /getIsolatedMarginAssetAmount(symbol, returnQuoteAsset = True)/\n")
        exit()

def getSpotAssetAmount(asset): 
    try:
        info = client.get_asset_balance("DREP")
    except Exception as ex:
        print("_____Couldn't get asset balance!!!_____")
        exit()
    else:
        print("{} balance = {}".format(asset,info['free']))
        return float(info["free"])

def transferFundsFromIsolatedMargin(asset,symbol):
    try:
        amount = getIsolatedMarginAssetAmount(symbol = symbol, returnQuoteAsset = (True if asset == "USDT" else False))
        transaction = client.transfer_isolated_margin_to_spot(asset=asset,symbol=symbol, amount=amount)
    except Exception as ex:
        if asset != "USDT":
            print(ex)
            print("Couldn't instantly transfer all quote asset, trying to close probable unclosed loan....\n")
            baseAsset = symbol.replace("USDT","")
            baseAssetAmount = getSpotAssetAmount(asset = baseAsset)
            transferFundsToIsolatedMargin(asset=baseAsset,symbol = symbol, amount = baseAssetAmount)
            if repayLoan(asset = baseAsset,symbol =symbol, amount = baseAssetAmount, isIsolated = True) == False:
                print(ex)
                print("\nCouldn't transfer funds from back isolated to spot\n\n------------------------------")
                return False
            else:
                if transferFundsFromIsolatedMargin(asset = asset, symbol = symbol) == True:
                    return True
                else: 
                    return False
        else:
            return False
    else:
        print("\nSuccessfully transfered all {} from Isolated to Spot\n".format(asset))
        return True

def deactivateBadSymbols():
    badSybmols = []
    try:
        f = open("./IsolatedSymbolsBadList.txt","r")
        lines = f.readlines()
        for line in lines:
            splitedLine = line.split("-")
            symbol = splitedLine[1].replace("\n","")
            badSybmols.append(symbol)
    except Exception as ex:
        print(ex)
        print("\n_______Something went wrong in /deactivateBadSymbols()/ while retrieving bad symbols from file_______\n")
    for symbol in badSybmols:
        try:
            client.disable_isolated_margin_account(symbol = symbol)
        except Exception as ex:
            print("\n"+str(ex))
            print(f"\n_____Couldn't disable isolated {symbol}______\n")
        else:
            print("Successfully disabled {}\n=========".format(symbol))

def activateIsolatedPair(symbol):
    try:
        client.enable_isolated_margin_account(symbol = symbol)
    except exc.BinanceAPIException as ex:
        deactivateBadSymbols()
        try:
            client.enable_isolated_margin_account(symbol = symbol)
        except:
            print(ex)
            print("\n_______Couldn't activate isolated pair_________\n")
            return False
        else:
            return True
    except Exception as ex:
        print(ex)
        print("\n_______Couldn't activate isolated pair_________\n")
        return False
    else:
        print("\nSuccessfully activated isolated pair\n")
        return True

def transferFundsToIsolatedMargin(asset, symbol, amount):
    try:
        client.transfer_spot_to_isolated_margin(asset=asset,symbol = symbol, amount = amount)
    except exc.BinanceAPIException as ex:
        print(ex)
        print(type(ex))
        print("\nCouldn't transfer because isolated pair is deactivated")
        if activateIsolatedPair(symbol=symbol) == False:
            return False
        else: 
            try:
                client.transfer_spot_to_isolated_margin(asset=asset ,symbol = symbol, amount = amount)
            except Exception as ex:
                print(ex)
                print("\nStill couldn't transfer!!!!______\n")
                return False
            else:
                print("\nSuccessfully transfered funds to Isolated Margin {}".format(symbol))
                return True
            
    except Exception as ex:
        print("\nCouldn't transfer funds to isolated {}\n".format(symbol))
        return False
    else:
        print("\nSuccessfully transfered funds to Isolated Margin {}".format(symbol))
        return True

def repayLoan(asset, symbol, amount, isIsolated):
    try:    
        repayLoanOrder = client.repay_margin_loan(asset=asset, amount = amount, isIsolated = ("TRUE" if isIsolated else "FALSE"), symbol = symbol)
    except Exception as ex:
        print(ex)
        print("______Couldn't repay the loan!!!!!________")
        print("______Should repay manually!!!!!______")
        return False
    else:
        print("Successfully payed the loan back!!!\n")
        return True

info = client.get_isolated_margin_account()
count = 0
t = time.localtime()
print(f"\nTime now:{time.strftime('%H:%M:%S', t)}\n")
for pair in info['assets']:
    if pair['enabled'] == True:
        try:
            client.disable_isolated_margin_account(symbol = pair['symbol'])
        except Exception as ex:
            print(ex)
            print(f"______Coudn't instantly disable {pair['symbol']}________")
            transferFundsFromIsolatedMargin(pair['symbol'].replace("USDT",""),pair['symbol'])
            transferFundsFromIsolatedMargin(asset="USDT",symbol = pair['symbol'])
            try:
                client.disable_isolated_margin_account(symbol = pair['symbol'])
                print("Successfully disabled {}\n=========".format(pair['symbol']))
            except:
                pass
            print("\n"+str(ex))
            print(f"\n_____Couldn't disable isolated {pair['symbol']}______\n")
        else:
            print("Successfully disabled {}\n=========\n\n\n\n\n".format(pair['symbol']))


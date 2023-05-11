from random import randint
from UpDownStrategy import main as upDownStrategyMainFunc
from CheckForVolatile import main as checkForVolatileMainFunc
from Config import Config
import asyncio
import openpyxl as xl
from binance import Client
from binance import exceptions as exc
from sys import exc_info
import signal
from time import time
from time import sleep
from datetime import datetime
from os import getpid

def interrupted(signum, frame):
    #"called when read times out"
    print('Time is out!')
    raise Exception

client = None

def main():
    global client
    config = Config()
    client = Client(config.API_KEY, config.API_SECRET)
    signal.signal(signal.SIGALRM, interrupted)
    flag = True 

    wb = xl.load_workbook(config.FilePathToSave)
    wsUp = wb["Long"]
    wsDown = wb["Short"]
    currentRow = 0
    mainOrderIdCol = 'A'
    startDateTimeCol = 'B'
    startAccBalBaseCol=  'C'
    startAccBalQouteCol = 'D'
    startAccBalBNBCol = 'E'
    endDateTimeCol = "F" 
    endAccBalBaseCol = "G"
    endAccBalQouteCol = "H"
    endAccBalBNBCol = 'I'
    symbolCol = "J"
    tradingAmountInQuoteCol = 'K'
    tradingAmountInBaseCol = 'L'
    BNBByQuoteCol = 'T'
    BaseByQuoteCol = 'Y'
    enteredPriceCol = 'AD'
    stopLossAtCol = 'AE'
    takeProfitAtCol = 'AF'
    positionClosedAtCol = 'AG'
    closedByCol = "AH"
    errorCol = 'AI'
    profitDealRangeCol = "AK"
    lossDealRangeCol = "AL"
    initialCaughtChangeCol = "AM"
    tickPriceCol = "AN"
    tickPriceToPriceCol = "AO"
    spreadCol = "AP"
    spreadBeforeTheDealCol = "AQ"

    amountInBase = 0
    amountInQuote = 0
    amountOfBNB = 0 
    recievedInfo = None
    issue = None
    isIsolated = False
    startSearchTime = time()
    failedConnections = 0 

    print(f"\nProgram pid = {getpid()}\n")
    
    while flag:
        config = Config()
        resultTuple = checkForVolatileMainFunc(Config = config)
        if resultTuple == -1:
            failedConnections+=1
            if failedConnections>=5:
                print("\n_________Couldn't get most volatile for 5 consecutive times_________\n")
                sleep(120)
                failedConnections = 0
            continue
        else:
            failedConnections = 0
        print(f"; Took {round((time()-startSearchTime),0) } seconds to find")
        if config.setSymbol(symbol=resultTuple[0], currentPrice= resultTuple[1], priceChange=resultTuple[2]) == False:
            continue
        symbol = resultTuple[0]
        result = checkIfHasCross(symbol = symbol)
        if checkIfHasCross(symbol = symbol) == True:
            
            if isBorrowAllowed(asset=config.BaseCurrency, symbol=config.Symbol, isIsolated=False) and transferFundsToCrossMargin(asset = config.QuoteCurrency,amount = config.AmountToTransfer):
                isIsolated = False
            else:
                continue
        elif result == False:
            if transferFundsToIsolatedMargin(asset = config.QuoteCurrency,symbol = symbol, amount = config.AmountToTransfer):
                if isBorrowAllowed(asset=config.BaseCurrency, symbol=config.Symbol, isIsolated=True):
                    isIsolated = True
                else:
                    writeDownBadSymbol(symbol = config.Symbol)
                    transferAllFundsFromIsolatedMargin(asset = config.QuoteCurrency,symbol = config.Symbol)
                    continue
            else:
                continue
        else:
            continue

        dealTime = 0
        firstDeal = True
        dealCount= 0
        while dealTime < Config.DealTime and dealCount <config.MaxNumOfDealsForACoughtPair:
            if firstDeal != True:
                ans = None
                signal.alarm(2)
                try:
                    ans = input('\n\nDo you wish to continue trading this pair?(y/n)\n\n')
                except:
                    print("\nKeep on going........\n\n\n")
                signal.alarm(0)

                if ans == "n" or ans == "N":
                    print("\nFinishing.")
                    flag = False
                elif ans != None:
                    print("\nKeep on going........\n\n\n")
                firstDeal = False
            x = randint(0,1)
            if x == 0:
                success = False
                attempt = 0
                while attempt<3 and success != True:
                    try:
                        if config.SavingToFile == True:

                            issue = None
                            for num in range(3,300):
                                if wsUp["B{}".format(num)].value == None:
                                    currentRow = "{}".format(num)
                                    break

                            amountInBase = client.get_asset_balance(asset = config.BaseCurrency)['free']
                            amountInQuote = client.get_asset_balance(asset = config.QuoteCurrency)['free']
                            amountOfBNB = client.get_asset_balance(asset = "BNB")['free']

                            wsUp[startDateTimeCol+currentRow].value = datetime.now()
                            wsUp[startAccBalBaseCol+currentRow].value = amountInBase
                            wsUp[startAccBalQouteCol+currentRow].value = amountInQuote
                            wsUp[startAccBalBNBCol+currentRow].value = amountOfBNB#
                            wsUp[profitDealRangeCol+currentRow].value = config.ProfitDealRange
                            wsUp[lossDealRangeCol+currentRow].value = config.LossDealRange
                            wsUp[tickPriceToPriceCol+currentRow].value = config.TickPriceToCurrentPrice
                            wsUp[initialCaughtChangeCol+currentRow].value = config.InitialFluctuation#
                            wsUp[symbolCol+currentRow].value = config.Symbol#
                            wsUp[tickPriceCol+currentRow].value = config.TickPrice
                            wsUp[spreadCol+currentRow].value = config.InitialSpread#
                            
                            
                        
                            wsUp[BNBByQuoteCol+currentRow].value = client.get_ticker(symbol = "BNBBUSD")['lastPrice']
                            wsUp[BaseByQuoteCol+currentRow].value = client.get_ticker(symbol = config.Symbol)['lastPrice']

                            wb.save(config.FilePathToSave)
                    except Exception as ex:
                        print("\n"+str(ex))
                        print("______Couldn't instantly write to a file_______")                        
                        attempt+=1
                    else:
                        print("Were able to successfully write to a file")
                        success = True
                if success == False:
                    print("\n_______Coudn't write info to file for 3 times_________\n")
                    exit()
 
                time1 = time()
                for n in range(0,60):
                    print(".")
                print("\n\nGoing UP!!! \n---------\n\n")
                try:
                    recievedInfo = asyncio.run(upDownStrategyMainFunc(mainClient=client,config=config))
                except Exception as ex:
                    print("\nThe program raised an exception\n")
                    print(exc_info()[2])
                    print("\n{}".format(ex))
                    issue = str(ex)
                time2 = time()

                success = False
                attempt = 0
                while attempt<3 and success != True:
                    try:
                        if config.SavingToFile == True:

                            amountInBase = client.get_asset_balance(asset = config.BaseCurrency)['free']
                            amountInQuote = client.get_asset_balance(asset = config.QuoteCurrency)['free']
                            amountOfBNB = client.get_asset_balance(asset = "BNB")['free']
                            
                            wsUp[endDateTimeCol+currentRow].value = datetime.now()
                            wsUp[endAccBalBaseCol+currentRow].value = amountInBase
                            wsUp[endAccBalQouteCol+currentRow].value = amountInQuote
                            wsUp[endAccBalBNBCol+currentRow].value = amountOfBNB

                            if issue == None:
                                wsUp[mainOrderIdCol+currentRow].value = recievedInfo['mainOrderId']
                                wsUp[tradingAmountInBaseCol+currentRow].value = recievedInfo['tradingAmountInBase']
                                wsUp[tradingAmountInQuoteCol+currentRow].value = recievedInfo["tradingAmountInQuote"]
                                wsUp[enteredPriceCol+currentRow].value = recievedInfo["enteredPrice"]
                                wsUp[stopLossAtCol+currentRow].value = recievedInfo['stopLossPrice']
                                wsUp[takeProfitAtCol+currentRow].value = recievedInfo['takeProfitPrice']
                                wsUp[positionClosedAtCol+currentRow].value = recievedInfo['closedPrice']
                                wsUp[closedByCol+currentRow].value = recievedInfo["closedBy"]
                                wsUp[spreadBeforeTheDealCol+currentRow].value = recievedInfo["updatedSpread"]

                            
                            errorReport = "Broke Program:"
                            if issue != None:
                                errorReport += "\n{}".format(issue)

                            errorReport +="\nInternal Errors:\n"
                            if recievedInfo != None:
                                for err in recievedInfo['issues']:
                                    errorReport+="{}\n".format(err)
                            wsUp[errorCol+currentRow].value = errorReport
                            
                            issue = None
                            wb.save(config.FilePathToSave)
                    except Exception as ex:
                        print("\n"+str(ex))
                        print("______Couldn't instantly write to a file_______")                        
                        attempt+=1
                    else:
                        print("Were able to successfully write to a file")
                        success = True
                if success == False:
                    print("\n_______Coudn't write info to file for 3 times_________\n")
                    exit()

                dealTime = time2-time1

            elif x == 1:
                success = False
                attempt = 0               
                while attempt<3 and success != True:
                    try:                
                        if config.SavingToFile == True:
                            if isIsolated == True:
                                info = client.get_isolated_margin_account(symbols=config.Symbol)
                                amountInBase = info['assets'][0]['baseAsset']['free']
                                amountInQuote = info['assets'][0]['quoteAsset']['free']
                                amountOfBNB = client.get_asset_balance(asset = "BNB")['free']
                            else:
                                amountInBase = getCrossMarginAssetAmount(config.BaseCurrency)
                                amountInQuote = getCrossMarginAssetAmount(config.QuoteCurrency)
                                amountOfBNB = getCrossMarginAssetAmount("BNB")

                            issue = None
                            for num in range(3,300):
                                if wsDown["A{}".format(num)].value == None:
                                    currentRow = "{}".format(num)
                                    break

                            wsDown[startDateTimeCol+currentRow].value = datetime.now()
                            wsDown[startAccBalBaseCol+currentRow].value = float(amountInBase)
                            wsDown[startAccBalQouteCol+currentRow].value = float(amountInQuote)
                            wsDown[startAccBalBNBCol+currentRow].value = float(amountOfBNB)
                            wsDown[profitDealRangeCol+currentRow].value = config.ProfitDealRange
                            wsDown[lossDealRangeCol+currentRow].value = config.LossDealRange
                            wsDown[tickPriceToPriceCol+currentRow].value = config.TickPriceToCurrentPrice
                            wsDown[initialCaughtChangeCol+currentRow].value = config.InitialFluctuation
                            wsDown[symbolCol+currentRow].value = config.Symbol
                            wsDown[tickPriceCol+currentRow].value = config.TickPrice
                            wsDown[spreadCol+currentRow].value = config.InitialSpread#                            

                            wsDown[BNBByQuoteCol+currentRow].value = client.get_ticker(symbol = ("BNB"+config.QuoteCurrency))['lastPrice']
                            wsDown[BaseByQuoteCol+currentRow].value = client.get_ticker(symbol = config.Symbol)['lastPrice']

                            wb.save(config.FilePathToSave)
                    except Exception as ex:
                        print("\n"+str(ex))
                        print("______Couldn't instantly write to a file_______")                        
                        attempt+=1
                    else:
                        print("Were able to successfully write to a file")
                        success = True
                if success == False:
                    print("\n_______Coudn't write info to file for 3 times_________\n")
                    exit()

                time1 = time()
                for n in range(0,60):
                    print(".")
                print("\n\nGoing Down!!! \n---------\n\n")
                try:
                    recievedInfo = asyncio.run(upDownStrategyMainFunc(mainClient=client,config=config,strat = 1, isolated = isIsolated))
                except exc.BinanceAPIException as ex:
                    print(ex)
                    print("\nFinishing trading this pair....\n")
                    break
                except Exception as ex:
                    print("\n\nStrategy wasn't finished properly")
                    print(exc_info()[2])
                    print("\n{}".format(ex))
                    issue = str(ex)
                time2 = time()
                success = False
                attempt = 0         
                while attempt<3 and success != True:
                    try:   
                        if config.SavingToFile == True:
                            if isIsolated ==True:
                                info = client.get_isolated_margin_account(symbols=config.Symbol)
                                amountInBase = info['assets'][0]['baseAsset']['free']
                                amountInQuote = info['assets'][0]['quoteAsset']['free']
                                amountOfBNB = client.get_asset_balance(asset = "BNB")['free']
                            else:
                                amountInBase = getCrossMarginAssetAmount(config.BaseCurrency)
                                amountInQuote = getCrossMarginAssetAmount(config.QuoteCurrency)
                                amountOfBNB = getCrossMarginAssetAmount("BNB")                        

                            wsDown[endDateTimeCol+currentRow].value = datetime.now()
                            wsDown[endAccBalBaseCol+currentRow].value = float(amountInBase)
                            wsDown[endAccBalQouteCol+currentRow].value = float(amountInQuote)
                            wsDown[endAccBalBNBCol+currentRow].value = float(amountOfBNB)
                            
                            if issue == None:
                                wsDown[mainOrderIdCol+currentRow].value = recievedInfo['mainOrderId']
                                wsDown[tradingAmountInBaseCol+currentRow].value = recievedInfo['tradingAmountInBase']
                                wsDown[tradingAmountInQuoteCol+currentRow].value = recievedInfo["tradingAmountInQuote"]
                                wsDown[enteredPriceCol+currentRow].value = recievedInfo["enteredPrice"]
                                wsDown[stopLossAtCol+currentRow].value = recievedInfo['stopLossPrice']
                                wsDown[takeProfitAtCol+currentRow].value = recievedInfo['takeProfitPrice']    
                                wsDown[positionClosedAtCol+currentRow].value = recievedInfo['closedPrice']
                                wsDown[closedByCol+currentRow].value = recievedInfo["closedBy"]
                                wsDown[spreadBeforeTheDealCol+currentRow].value = recievedInfo["updatedSpread"]

                            errorReport = "Broke Program:"
                            if issue != None:
                                errorReport += "\n{}".format(issue)

                            errorReport +="\nInternal Errors:\n"
                            if recievedInfo != None:
                                for err in recievedInfo['issues']:
                                    errorReport+="{}\n".format(err)
                            wsDown[errorCol+currentRow].value = errorReport
                            
                            issue = None
                            wb.save(config.FilePathToSave)
                    except Exception as ex:
                        print("\n"+str(ex))
                        print("______Couldn't instantly write to a file_______")
                        attempt+=1
                    else:
                        print("Were able to successfully write to a file")
                        success = True
                if success == False:
                    print("\n_______Coudn't write info to file for 3 times_________\n")
                    exit()                        
                dealTime =time2-time1
            dealCount+=1

        if isIsolated == True:
            if transferAllFundsFromIsolatedMargin(asset=config.QuoteCurrency,symbol =config.Symbol) == False:
                exit()
        else:
            if transferAllFundsFromCrossMargin(asset=config.QuoteCurrency) == False:
                exit()
            

        ans = None 
        print("\nWe are about to ask whether you want to continue\n")
        signal.alarm(6)
        try:
            ans = input('\n\nDo you wish the strategy to continue?(y/n)\n\n')
        except:
            print("\nKeep on going........\n\n\n")
        signal.alarm(0)

        if ans == "n" or ans == "N":
            print("\nFinishing.")
            flag = False
        elif ans != None:
            print("\nKeep on going........\n\n\n")
        startSearchTime = time()

def getSpotAssetAmount(asset): 
    try:
        info = client.get_asset_balance(asset = asset)
    except Exception as ex:
        print("_____Couldn't get asset balance!!!_____")
        exit()
    else:
        print("{} balance = {}".format(asset,info['free']))
        return float(info["free"])

def getCrossMarginAssetAmount(asset):
    try:
        crossMarginAccount = client.get_margin_account()
        for assetInfo in crossMarginAccount['userAssets']:
            if assetInfo['asset'] == asset:
                return float(assetInfo['free'])
    except Exception as ex:
        print(ex)
        print("Couldn't get crossMargin account")
        exit()
    else:
        exit()

def getIsolatedMarginAssetAmount(symbol, returnQuoteAsset = True):
    try:
        info = client.get_isolated_margin_account()
        symbolBalanceInQuote = 0
        for pair in info['assets']:
            if pair['symbol'] == symbol:
                symbolBalanceInQuote =  float(pair['quoteAsset']['free'])
                return symbolBalanceInQuote
    except Exception as ex:
        print(ex+str(ex))
        print("\nCouldn't get {} balance\n".format(symbol))
        exit()
    else:
        print("\nSomething went wrong in /getIsolatedMarginAssetAmount(symbol, returnQuoteAsset = True)/\n")
        exit()

def checkIfHasCross(symbol):
    success = False
    attempt = 0
    while success == False and attempt<3:
        try:
            info = client.get_margin_symbol(symbol=symbol)
        except exc.BinanceAPIException as ex:
            return False
        except Exception as ex:
            print('\nSomething went wrong in /def checkIfHasCross(symbol):/')
            print(ex)
            attempt+=1
        else:
            print("\nSymbol has Cross Margin!\n")
            return True
    if success == False: 
        print(f"\n____________Couldn't check whether {symbol} has Cross Margin____________\n")
        return None

def activateIsolatedPair(symbol):
    try:
        client.enable_isolated_margin_account(symbol = symbol)
    except exc.BinanceAPIException as ex:
        print("\n"+str(ex))
        print(f"Couldn't instantly enable isolated {symbol}")

        deactivateBadSymbols()
        try:
            client.enable_isolated_margin_account(symbol = symbol)
        except:
            print(ex)
            print("\n_______Couldn't activate isolated pair_________\n")
            return False
        else:
            print(f"\nSuccessfully activated isolated pair{symbol}\n")
            return True
    except Exception as ex:
        print(ex)
        print("\n_______Couldn't activate isolated pair_________\n")
        return False
    else:
        print("\nSuccessfully activated isolated pair\n")
        return True

def deactivateBadSymbols():
    badSybmols = []
    client = Client(api_key=Config.API_KEY, api_secret=Config.API_SECRET)
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
            print("\n")
            print(ex)
            print(f"Couldn't instantly disable isolated {symbol}")
            transferAllFundsFromIsolatedMargin(asset=symbol.replace("USDT",""),symbol = symbol)
            try:
                client.disable_isolated_margin_account(symbol = symbol)
            except Exception as ex:
                print("\n")
                print(ex)
                print(f"\n_____Couldn't disable isolated {symbol}______\n")
            else:
                print("Successfully disabled {}\n=========".format(symbol))
        else:
            print("Successfully disabled {}\n=========".format(symbol))
        sleep(0.5)

def transferFundsToIsolatedMargin(asset, symbol, amount):
    try:
        client.transfer_spot_to_isolated_margin(asset=asset,symbol = symbol, amount = amount)
    except exc.BinanceAPIException as ex:
        print(ex)
        if ex.code == -3052:
            print("Couldn't transfer because isolated pair is deactivated")
            if activateIsolatedPair(symbol=symbol) == False:
                return False
            else: 
                try:
                    client.transfer_spot_to_isolated_margin(asset=asset ,symbol = symbol, amount = amount)
                except Exception as ex:
                    print(ex)
                    print("\nCouldn't transfer funds to isolated {}\n".format(symbol))
                    return False
                else:
                    print("\nSuccessfully transfered funds to Isolated Margin {}".format(symbol))
                    return True
        else:
            print("\nCouldn't transfer funds to isolated {}\n".format(symbol))
            return False
    except Exception as ex:
        print("\nCouldn't transfer funds to isolated {}\n".format(symbol))
        return False
    else:
        print("\nSuccessfully transfered funds to Isolated Margin {}".format(symbol))
        return True

def transferAllFundsFromIsolatedMargin(asset,symbol):
    try:
        amount = getIsolatedMarginAssetAmount(symbol = symbol)
        transaction = client.transfer_isolated_margin_to_spot(asset=asset,symbol=symbol, amount=amount)
    except exc.BinanceAPIException as ex:
        print("\n"+str(ex))
        if ex.code == -11015:
            print("Couldn't transfer funds because there is an unpaid loan\n")
            baseAsset = symbol.replace("USDT","")
            baseAssetAmount = getSpotAssetAmount(asset = baseAsset)
            if baseAssetAmount == 0:
                adjustedAmount = round(round(amount,8) - 0.0001000,8)
                try:
                    transaction = client.transfer_isolated_margin_to_spot(asset=asset,symbol=symbol, amount=adjustedAmount)
                except Exception as ex:
                    print("\n"+str(ex))
                    print(f"_______Still couldn't transfer {asset} to Spot_______")
                    exit()
                else:
                    return True
            transferFundsToIsolatedMargin(asset=baseAsset,symbol = symbol, amount = baseAssetAmount)
            if repayLoan(asset = baseAsset,symbol =symbol, amount = baseAssetAmount, isIsolated = True) == False:
                print(ex)
                exit()
            else:
                try:
                    transaction = client.transfer_isolated_margin_to_spot(asset=asset,symbol=symbol, amount=amount)
                except Exception as ex:
                    print(ex)
                    print(f"\nStill couldn't close the transfer: {asset} from {symbol} account!")
                    return False
                else:
                    print("\nSuccessfully transfered all {} from Isolated to Spot\n".format(asset))
                    return True
                
        print("Couldn't instantly transfer all quote asset\n")
        return False
    except Exception as ex:
        print(ex)
        print("Couldn't instantly transfer all quote asset\n")
        return False
    else:
        print("\nSuccessfully transfered all {} from Isolated to Spot\n".format(asset))
        return True
        
def transferFundsToCrossMargin(asset, amount):
    try:
        transaction = client.transfer_spot_to_margin(asset='USDT', amount=Config.AmountToTransfer)
    except Exception as ex:
        print(ex)
        print("Couldn't transfer {}{} to cross margin account".format(amount,asset))
        return False
    else:
        print("\nSuccessfully transfered funds to Cross Asset {}".format(asset))
        return True

def transferAllFundsFromCrossMargin(asset):
    try:
        amount = getCrossMarginAssetAmount(asset = asset)
        transaction = client.transfer_margin_to_spot(asset=asset, amount=amount)
    except Exception as ex:
        print(ex)
        print("Couldn't do /def transferAllFundsFromCrossMargin(asset)/")
        return False
    else:
        print("\nSuccessfully transfered funds from Cross Asset {}\n\n------------------------------".format(asset))
        return True

def isBorrowAllowed(asset, symbol, isIsolated):
    try:
        borrowOrder = client.create_margin_loan(asset = asset, amount = "{}".format(0.00000001), isIsolated = ("TRUE" if isIsolated else "FALSE"), symbol = symbol)  
    except exc.BinanceAPIException as ex:
        print("\n{}\n".format(ex)) 
        print("\nBorrow is not allowed for {}".format(asset))
        return False
    except Exception as ex:
        print("___________Something went wrong checking for borrowing availability{}__________".format())
        print("\n{}\n".format(ex))
        print(exc_info()[2])
        exit()
    else:      
        print("\nBorrow for {} is allowed\n".format(asset))
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

def writeDownBadSymbol(symbol):
    try:
        f = open("./IsolatedSymbolsBadList.txt","a")
        timeNow = datetime.now()
        timeToWrite = timeNow.strftime("%d:%H:%M")
        stringToWrite = timeToWrite + "-" + symbol + "\n"
        f.write(stringToWrite)
        print(f"Have successfully writen down BadSymbol - {symbol}")
    except Exception as ex:
        print(ex)
        print("Couldn't add {} to BadList".format(symbol))
    finally:
        f.close()

if __name__ == "__main__":
    main()

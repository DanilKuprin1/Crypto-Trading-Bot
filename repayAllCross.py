from Config import Config
from binance.client import Client
from time import time 
from binance import exceptions as exc


def transferFundsToCrossMargin(asset, amount):
    try:
        transaction = client.transfer_spot_to_margin(asset=asset, amount=amount)
    except Exception as ex:
        print(ex)
        print("Couldn't transfer {}{} to cross margin account".format(amount,asset))
        return False
    else:
        print("\nSuccessfully transfered funds to Cross Asset {}".format(asset))
        return True


def repayLoan(asset, symbol, amount, isIsolated):
    try:    
        repayLoanOrder = client.repay_margin_loan(asset=asset, amount = amount, isIsolated = ("TRUE" if isIsolated else "FALSE"))
    except Exception as ex:
        print(ex)
        print("______Couldn't repay the loan!!!!!________")
        print("______Should repay manually!!!!!______")
        return False
    else:
        print("Successfully payed the loan back!!!\n")
        return True

client = Client(api_key=Config.API_KEY,api_secret=Config.API_SECRET)
info = client.get_margin_account()

userAssets = info['userAssets']
for asset in userAssets:
    print(asset['interest'])
    if round(float(asset["interest"]),8)>0:
        if transferFundsToCrossMargin(asset['asset'], amount = 0.00001) == False:
            continue
        else:
            repayLoan(asset = asset["asset"],symbol=(asset["asset"]+"USDT"),amount = 0.00001, isIsolated=False)



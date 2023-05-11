from Config import Config
from binance.client import Client
from time import time
from binance import exceptions as exc

client = Client(api_key=Config.API_KEY,api_secret=Config.API_SECRET)

info = client.get_margin_account()
print(info)
for asset in info['userAssets']:
    if float(asset["free"])>0:
        try:
            transaction = client.transfer_margin_to_spot(asset=asset["asset"], amount=asset['free'])
        except Exception as ex:
            print("\n"+str(ex))
            print(f"Couldn't transfer {asset['free']}{asset['asset']}")
        else:
            print(f"\nSuccessfully transfered {asset['free']}{asset['asset']}")



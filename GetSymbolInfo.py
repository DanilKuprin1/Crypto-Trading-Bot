import asyncio
from enum import Enum, unique
import json
from Config import Config
from binance.client import Client
from binance import AsyncClient, BinanceSocketManager
from binance import enums
import time
from binance import exceptions as exc




config = Config()
client = Client(config.API_KEY,config.API_SECRET)
info = client.get_symbol_info("CHESSUSDT")
info1 = json.dumps(info,sort_keys=True, indent=4)


with open("/Users/danilkuprin/Desktop/Speculation/code50_40/mainStrategy/{}.json".format("CHESSUSDT"),"w") as f:
    f.write(info1)
    

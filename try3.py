from Config import Config
from binance.client import Client
from time import time
from binance import exceptions as exc

totalTime = 0

for _ in range(0,50):
    time1 = time()
    client = Client(api_key=Config.API_KEY,api_secret=Config.API_SECRET)
    time2 = time()
    totalTime += time1-time2
    




from time import sleep, time

from binance.client import Client

from config import Config

totalTime = 0
numOfTimes = 0
for n in range(1, 180):
    time1 = time()
    client = Client(api_key=Config.API_KEY, api_secret=Config.API_SECRET)
    time2 = time()
    totalTime += time2 - time1
    numOfTimes += 1
    sleep(1)

print(f"Average time = {totalTime / numOfTimes}")

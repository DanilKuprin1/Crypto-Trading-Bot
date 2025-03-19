from time import sleep, time

from binance.client import Client
from config import Config

durations = []

for _ in range(179):
    start_time = time()
    client = Client(api_key=Config.API_KEY, api_secret=Config.API_SECRET)
    durations.append(time() - start_time)
    sleep(1)

average_time = sum(durations) / len(durations)
print(f"Average time = {average_time:.4f} seconds")

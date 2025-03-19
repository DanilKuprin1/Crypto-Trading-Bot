import json
import logging

from binance.client import Client

from config import Config


def main():
    try:
        c = Config()
        cl = Client(c.API_KEY, c.API_SECRET)
        info = cl.get_symbol_info("CHESSUSDT")
        data = json.dumps(info, sort_keys=True, indent=4)
        path = ""
        with open(path, "w") as f:
            f.write(data)
        logging.info(f"Symbol info written to {path}")
    except Exception as e:
        logging.error(f"Error: {e}")


if __name__ == "__main__":
    main()

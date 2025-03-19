import logging

from config import Config

from app.trading_bot import TradingBot

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def main() -> None:
    config = Config()
    bot = TradingBot(config)
    try:
        bot.run()
    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt caught. Shutting down gracefully.")
    except Exception as e:
        logging.exception("Unhandled exception in main: %s", e)
    finally:
        logging.info("Exiting.")


if __name__ == "__main__":
    main()

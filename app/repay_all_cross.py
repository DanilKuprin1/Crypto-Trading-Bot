import logging

from binance.client import Client

from config import Config


def transfer_funds_to_cross_margin(client: Client, asset: str, amount: float) -> bool:
    try:
        client.transfer_spot_to_margin(asset=asset, amount=amount)
        logging.info("Successfully transferred %f %s to cross margin.", amount, asset)
        return True
    except Exception as ex:
        logging.error("Failed to transfer %f %s to cross margin: %s", amount, asset, ex)
        return False


def repay_loan(
    client: Client, asset: str, symbol: str, amount: float, is_isolated: bool
) -> bool:
    try:
        client.repay_margin_loan(
            asset=asset,
            amount=amount,
            isIsolated=("TRUE" if is_isolated else "FALSE"),
        )
        logging.info(
            "Successfully repaid %f %s loan for symbol %s.", amount, asset, symbol
        )
        return True
    except Exception as ex:
        logging.error(
            "Failed to repay loan of %f %s for symbol %s: %s", amount, asset, symbol, ex
        )
        return False


def main() -> None:
    client = Client(api_key=Config.API_KEY, api_secret=Config.API_SECRET)
    try:
        margin_info = client.get_margin_account()
    except Exception as ex:
        logging.error("Could not retrieve margin account info: %s", ex)
        return
    user_assets = margin_info.get("userAssets", [])
    if not user_assets:
        logging.info("No user assets found in margin account.")
        return
    for asset_data in user_assets:
        asset_name = asset_data["asset"]
        try:
            interest = float(asset_data["interest"])
        except ValueError:
            logging.warning(
                "Could not parse interest for asset '%s'; skipping.", asset_name
            )
            continue
        if round(interest, 8) > 0:
            logging.info(
                "Asset %s has interest = %f. Attempting to repay loan...",
                asset_name,
                interest,
            )
            transferred = transfer_funds_to_cross_margin(client, asset_name, 0.00001)
            if not transferred:
                logging.warning(
                    "Transfer of %s to cross margin failed; cannot repay loan.",
                    asset_name,
                )
                continue
            repaid = repay_loan(client, asset_name, asset_name + "USDT", 0.00001, False)
            if repaid:
                logging.info("Repayment successful for asset %s.", asset_name)
            else:
                logging.warning(
                    "Repayment failed for asset %s. Manual intervention might be required.",
                    asset_name,
                )


if __name__ == "__main__":
    main()

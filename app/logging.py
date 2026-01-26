from dotenv import load_dotenv
import logging


def setup_logging() -> None:
    """Initialize application-wide logging configuration."""
    load_dotenv()
    log_format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    logging.basicConfig(level=logging.INFO, format=log_format)

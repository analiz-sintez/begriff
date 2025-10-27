import logging

import nachricht
from nachricht.messenger import create_router
from nachricht.bus import create_bus
from nachricht.llm import init_llm_client
from nachricht.i18n import init_catalog
from nachricht.config import combine
from nachricht.options import create_option_registry, discover_options

from .config import Config

logger = logging.getLogger(__name__)

try:
    from .userconfig import Config as UserConfig

    logger.info("Found the user config, putting it on top of the default one.")
    combine(Config, UserConfig)
except:
    logger.info("Found no user config, using solely the default one.")


def create_app():
    """Factory method required by `flask` CLI"""
    # intialize all modules to gather routes
    import app.telegram

    discover_options(option_registry)

    # create an app
    return nachricht.create_app(Config)


init_catalog("data/locale")

bus = create_bus(config=Config)
option_registry = create_option_registry(bus)
router = create_router(config=Config)

llm_client = init_llm_client(
    host=Config.LLM["host"],
    api_key=Config.LLM["api_key"],
    default_model=Config.LLM["models"]["default"],
)

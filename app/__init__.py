import core
from core.messenger import Router
from core.bus import create_bus
from core.llm import init_llm_client
from core.i18n import init_catalog
from .config import Config


def create_app():
    """Factory method required by `flask` CLI"""
    import app.telegram

    return core.create_app(Config)


init_catalog("data/locale")

router = Router(config=Config)
bus = create_bus(config=Config)

llm_client = init_llm_client(
    host=Config.LLM["host"],
    api_key=Config.LLM["api_key"],
    default_model=Config.LLM["models"]["default"],
)

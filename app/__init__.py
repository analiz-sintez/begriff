from core.messenger import Router
from core.bus import create_bus
from core.llm import init_llm_client
from .config import Config

router = Router(config=Config)
bus = create_bus(config=Config)

llm_client = init_llm_client(
    host=Config.LLM["host"],
    api_key=Config.LLM["api_key"],
    default_model=Config.LLM["models"]["default"],
)

from core.messenger import Router
from core.bus import create_bus
from .config import Config

router = Router(config=Config)
bus = create_bus(config=Config)

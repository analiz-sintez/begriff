from .service import (
    Signal,
    Bus,
    encode,
    decode,
    make_regexp,
)
from .saving_backends import dump_signal_to_log, dump_signal_to_db
from ..config import Config

if Config.SIGNALS["logging_backend"] == "db":
    bus = Bus(saving_backend=dump_signal_to_db)
elif Config.SIGNALS["logging_backend"] == "log":
    bus = Bus(saving_backend=dump_signal_to_log)
else:
    raise NotImplementedError(
        "Unknown config option for signals logging: %s"
        % Config.SIGNALS["logging_backend"]
    )

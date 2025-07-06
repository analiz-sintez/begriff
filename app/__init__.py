from core.bus import Bus, dump_signal_to_db, dump_signal_to_log
from .config import Config

if Config.SIGNALS["logging_backend"] == "db":
    bus = Bus(saving_backend=dump_signal_to_db)
elif Config.SIGNALS["logging_backend"] == "log":
    bus = Bus(saving_backend=dump_signal_to_log)
else:
    raise NotImplementedError(
        "Unknown config option for signals logging: %s"
        % Config.SIGNALS["logging_backend"]
    )

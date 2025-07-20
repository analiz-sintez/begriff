from .service import Signal, Bus, encode, decode, make_regexp, unoption
from .saving_backends import dump_signal_to_log, dump_signal_to_db

bus = None


def create_bus(config: object):
    global bus
    if config.SIGNALS["logging_backend"] == "db":
        bus = Bus(saving_backend=dump_signal_to_db, config=config)
    elif config.SIGNALS["logging_backend"] == "log":
        bus = Bus(saving_backend=dump_signal_to_log, config=config)
    else:
        raise NotImplementedError(
            "Unknown config option for signals logging: %s"
            % config.SIGNALS["logging_backend"]
        )
    return bus


def get_bus():
    return bus

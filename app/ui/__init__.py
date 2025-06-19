import asyncio
import logging
from dataclasses import dataclass, asdict
from typing import Callable, Type, List

logger = logging.getLogger(__name__)


@dataclass
class Signal:
    pass


class Bus:
    def __init__(self):
        self._slots = dict()

    @classmethod
    def signals(cls):
        """Recursively find all descendant classes."""
        descendants = set()
        subclasses = Signal.__subclasses__()
        for sub in subclasses:
            descendants.add(sub)
            descendants.update(get_all_descendants(sub))
        return descendants

    def register(self, signal_type: Type[Signal]):
        """Register a signal."""
        if not issubclass(signal_type, Signal):
            raise TypeError(
                "You should inherit your signals from Signal class."
                " It allows to track all the signals tree of the application."
            )
        if signal_type not in self._slots:
            self._slots[signal_type] = []
            logger.info(f"Registered signal type: {signal_type.__name__}")

    def on(self, signal_type: Type[Signal]):
        """Make a decorator which connects a signal to any slot."""

        def _wrapper(slot: Callable):
            self.connect(signal_type, slot)
            return slot

        return _wrapper

    def connect(self, signal_type: Type[Signal], slot: Callable):
        """
        Connect a signal to a slot: the slot will be called each time
        the signal is emitted, with signal parameters.
        """
        # remember the connection
        self.register(signal_type)
        if slot not in self._slots[signal_type]:
            self._slots[signal_type].append(slot)

    def _handle_task_result(self, task: asyncio.Task) -> None:
        """Callback to log exceptions from fire-and-forget tasks."""
        try:
            task.result()
        except asyncio.CancelledError:
            pass  # Not an error
        except Exception as e:
            logging.error(f"Exception in background task: {e}", exc_info=True)

    def emit(self, signal: Signal) -> List[asyncio.Task]:
        """
        Fire-and-forget: Schedules slots and returns immediately.
        Exceptions in slots will be logged, not raised.
        """
        logger.info(f"Emitting signal without waiting: {signal}")
        signal_type = type(signal)
        if signal_type in self._slots:
            tasks = [
                asyncio.create_task(slot(**asdict(signal)))
                for slot in self._slots[signal_type]
            ]
            for task in tasks:
                task.add_done_callback(self._handle_task_result)
            return tasks

    async def emit_and_wait(self, signal: Signal) -> None:
        """
        Schedules slots and waits for them all to complete.
        Raises the first exception encountered in a slot.
        """
        logger.info(f"Emitting signal with waiting: {signal}")
        signal_type = type(signal)
        if signal_type in self._slots:
            tasks = [
                asyncio.create_task(slot(**asdict(signal)))
                for slot in self._slots[signal_type]
            ]
            if tasks:
                # gather will propagate exceptions.
                await asyncio.gather(*tasks)


bus = Bus()

from dataclasses import dataclass
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.ui import Signal, Bus


@pytest.fixture
def bus():
    return Bus()


def test_register_signal(bus):
    class TestSignal(Signal):
        pass

    assert TestSignal not in bus._slots
    bus.register(TestSignal)
    assert TestSignal in bus._slots


def test_register_non_signal_should_raise_type_error(bus):
    with pytest.raises(TypeError):
        bus.register(object)


def test_connect_slot(bus):
    class TestSignal(Signal):
        pass

    slot = MagicMock()
    bus.connect(TestSignal, slot)

    assert slot in bus._slots[TestSignal]


def test_emit_signal_without_slots(bus):
    class TestSignal(Signal):
        pass

    signal = TestSignal()
    tasks = bus.emit(signal)

    assert not tasks


@pytest.mark.asyncio
async def test_emit_signal_with_slot(bus):
    class TestSignal(Signal):
        pass

    slot = AsyncMock()
    bus.connect(TestSignal, slot)

    signal = TestSignal()
    tasks = bus.emit(signal)

    assert tasks is not None
    await asyncio.gather(*tasks)
    slot.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_emit_and_wait_signal_with_slot(bus):
    class TestSignal(Signal):
        pass

    slot = AsyncMock()
    bus.connect(TestSignal, slot)

    signal = TestSignal()
    await bus.emit_and_wait(signal)

    slot.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_emit_signal_with_param(bus):
    @dataclass
    class TestSignal(Signal):
        param: int

    slot = AsyncMock()
    bus.connect(TestSignal, slot)

    signal = TestSignal(param=42)
    tasks = bus.emit(signal)

    assert tasks is not None
    await asyncio.gather(*tasks)
    slot.assert_awaited_once_with(param=42)

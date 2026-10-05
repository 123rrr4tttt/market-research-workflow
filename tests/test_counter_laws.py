from __future__ import annotations

from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws
from mrw_functorial_kit.shell.in_memory_counter import InMemoryCounter

_counter_idempotent: Idempotent[InMemoryCounter] = Idempotent(
    "read is idempotent", lambda counter: counter.read()
)
_counter_ordered: Ordered[InMemoryCounter] = Ordered(
    "increments commute",
    first=lambda counter: counter.increment(2),
    second=lambda counter: counter.increment(3),
    observe=lambda counter: counter.read(),
    commutes=True,
)
_counter_spec: PortLawSpec[InMemoryCounter] = PortLawSpec(
    idempotent=[_counter_idempotent], ordered=[_counter_ordered]
)
TestCounterLaws = port_laws("Counter", InMemoryCounter, _counter_spec)

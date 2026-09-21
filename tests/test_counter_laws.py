from functorial_kit import Idempotent, Ordered, PortLawSpec, port_laws
from mrw_functorial_kit.shell.in_memory_counter import InMemoryCounter

TestCounterLaws = port_laws(
    "Counter",
    InMemoryCounter,
    PortLawSpec(
        idempotent=[Idempotent("read is idempotent", lambda c: c.read())],
        ordered=[
            Ordered(
                "increments commute",
                first=lambda c: c.increment(2),
                second=lambda c: c.increment(3),
                observe=lambda c: c.read(),
                commutes=True,
            )
        ],
    ),
)

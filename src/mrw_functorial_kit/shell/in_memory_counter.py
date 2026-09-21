class InMemoryCounter:
    def __init__(self) -> None:
        self._value = 0

    def increment(self, by: int) -> None:
        self._value += by

    def read(self) -> int:
        return self._value

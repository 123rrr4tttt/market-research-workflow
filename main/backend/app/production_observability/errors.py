class ObservabilityValueError(ValueError):
    """Value contract failure in the production observability core."""


class ObservabilityTypeError(TypeError):
    """Closed-type contract failure in the production observability core."""


__all__ = ["ObservabilityTypeError", "ObservabilityValueError"]

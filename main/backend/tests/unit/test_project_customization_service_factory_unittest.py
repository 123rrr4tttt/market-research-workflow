from __future__ import annotations

import pytest

from app.project_customization.service import _factory_for


def test_project_customization_factory_rejects_invalid_plugin() -> None:
    class InvalidCustomization:
        pass

    factory = _factory_for(InvalidCustomization)

    with pytest.raises(
        TypeError,
        match="project customization class does not implement ProjectCustomization",
    ):
        factory()

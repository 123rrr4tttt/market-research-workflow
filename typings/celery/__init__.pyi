"""Typed public boundary for the locally installed Celery 5.4.0 package.

The declarations project the signatures used by MRW from Celery's native
``celery/app/base.py``, ``celery/app/task.py``, and ``celery/result.py``.
"""

from . import signals as signals
from .app.base import Celery as Celery
from .app.task import Context as Context, Task as Task

__version__: str

from collections.abc import Mapping
from typing import assert_type

from celery import Celery, Task, signals
from celery.result import AsyncResult, EagerResult

app = Celery("typed-probe", broker="memory://", backend="cache+memory://")

@app.task
def plain(value: str, count: int = 1) -> Mapping[str, object]:
    return {"value": value, "count": count}

@app.task(name="typed.configured")
def configured(value: int) -> str:
    return str(value)

@app.task(bind=True, name="typed.bound")
def bound(self: Task[[str], Mapping[str, object]], value: str) -> Mapping[str, object]:
    assert_type(self.request.id, str | None)
    self.update_state(state="PROGRESS", meta={"value": value})
    return {"value": value}

assert_type(plain.run("one"), Mapping[str, object])
assert_type(plain.delay("one", count=2), AsyncResult[Mapping[str, object]])
assert_type(plain.apply(args=("one",), kwargs={"count": 2}), EagerResult[Mapping[str, object]])
assert_type(plain.apply_async(args=("one", 2)), AsyncResult[Mapping[str, object]])
assert_type(configured.delay(1), AsyncResult[str])
assert_type(bound.delay("one"), AsyncResult[Mapping[str, object]])

plain_result = plain.delay("one")
assert_type(plain_result.id, str)
assert_type(plain_result.status, str)
assert_type(plain_result.result, Mapping[str, object] | BaseException | None)
assert_type(plain_result.get(), Mapping[str, object] | None)
assert_type(plain_result.get(propagate=False), Mapping[str, object] | BaseException | None)
assert_type(plain_result.ready(), bool)
assert_type(plain_result.successful(), bool)
assert_type(plain_result.failed(), bool)
plain_result.revoke(terminate=False)
plain.push_request(id="probe-id", hostname="probe-worker")
plain.pop_request()

assert_type(app.tasks[plain.name].name, str)
assert_type(app.conf.broker_url, str | None)
app.conf.update({"task_always_eager": True})

@signals.worker_process_init.connect(weak=False)
def worker_init(**kwargs: object) -> None:
    assert_type(kwargs, dict[str, object])

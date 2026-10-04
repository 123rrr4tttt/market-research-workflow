import json
import os
import plistlib
import sys
from pathlib import Path

root = Path('/Users/wangyiliang/market-research-workflow')
with (Path.home() / 'Library/LaunchAgents/com.mrw.local-worker.plist').open('rb') as source:
    config = plistlib.load(source)
os.environ.update(config.get('EnvironmentVariables', {}))
sys.path[:0] = [str(root/'src'), str(root/'main/backend'), '/Users/wangyiliang/Desktop/functorial-kit/python']
from app.celery_app import celery_app

with celery_app.connection_for_read() as connection:
    client = connection.channel().client
    queue = client.llen('celery')
    unacked = client.hlen('unacked')
inspect = celery_app.control.inspect(timeout=8)
ping = inspect.ping()
result = {'queue_length': queue, 'unacked': unacked, 'worker_ping': ping}
if os.environ.get('MRW_PROBE_REGISTRATION') == '1':
    registered = inspect.registered() or {}
    entries = [entry for tasks in registered.values() for entry in tasks]
    result['worker_observation_registered'] = any('task_worker_observation_probe' in entry for entry in entries)
    result['old_stage5_observation_registered'] = any('task_stage5' in entry for entry in entries)
    assert result['worker_observation_registered'] and not result['old_stage5_observation_registered'], result
print(json.dumps(result))
assert queue == 0 and unacked == 0 and ping, result

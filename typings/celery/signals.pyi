from celery.utils.dispatch.signal import Signal

worker_process_init: Signal
task_prerun: Signal
task_postrun: Signal
task_success: Signal
task_failure: Signal
task_retry: Signal
task_revoked: Signal

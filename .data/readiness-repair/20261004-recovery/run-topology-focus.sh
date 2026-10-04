#!/bin/zsh
cd /Users/wangyiliang/market-research-workflow
task_repo=/Users/wangyiliang/market-research-workflow
docker run --rm --name mrw-repair-topology-focus-20261004 \
  --network container:mrw-repair-test-db-20261004 --entrypoint python \
  -w "${task_repo}/main/backend" \
  -v "${task_repo}:${task_repo}:ro" \
  -v /Users/wangyiliang/Desktop/functorial-kit:/Users/wangyiliang/Desktop/functorial-kit:ro \
  -v /Users/wangyiliang/Desktop/科学/信息搜索框架:/Users/wangyiliang/Desktop/科学/信息搜索框架:ro \
  -e PYTHONPATH="${task_repo}/main/backend:${task_repo}/src:/Users/wangyiliang/Desktop/functorial-kit/python" \
  -e PYTHONPYCACHEPREFIX=/tmp/mrw-recovery-bytecode \
  -e HYPOTHESIS_STORAGE_DIRECTORY=/tmp/mrw-recovery-hypothesis \
  -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0="${task_repo}" \
  -e CRAWLER_LAZY_START_SCRAPYD=0 -e SCRAPYD_BASE_URL=http://127.0.0.1:6801 \
  -e OPENAI_API_KEY= -e DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:1/mrw_test_unavailable \
  -e SUCCESSOR_TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/mrw_test_runtime \
  -e SUCCESSOR_P3_C5_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/mrw_p3_c5_worker_test_repair_20261004 \
  -e MRW_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/mrw_test_runtime \
  -e INFORMATION_TOPOLOGY_TEST_DATABASE_URL=postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/mrw_test_runtime \
  -e INFORMATION_TOPOLOGY_TEST_SCHEMA=mrw_repair_topology \
  mrw-repair-tests-20261004:latest -m pytest /Users/wangyiliang/market-research-workflow/main/backend/tests/integration/test_information_topology_repository.py /Users/wangyiliang/market-research-workflow/main/backend/tests/integration/test_information_topology_retrieval_io.py -c /Users/wangyiliang/market-research-workflow/main/backend/pytest.ini -m 'not external' -q -p no:cacheprovider \
  > .data/readiness-repair/20261004-recovery/topology-pg-focused.log 2>&1
task_exit=$?
echo "$task_exit" > .data/readiness-repair/20261004-recovery/topology-pg-focused.exit
exit "$task_exit"

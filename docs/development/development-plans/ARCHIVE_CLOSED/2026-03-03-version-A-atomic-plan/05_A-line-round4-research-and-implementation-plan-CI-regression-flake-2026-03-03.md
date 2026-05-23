<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan/05_A-line-round4-research-and-implementation-plan-CI-regression-flake-2026-03-03.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan/05_A-line-round4-research-and-implementation-plan-CI-regression-flake-2026-03-03.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# A线第4轮：CI稳定性/回归可靠性/Flake治理（先检索再实现）

日期：2026-03-03
策略基线：默认参考 `feature/version-C-streamplus`（当前工作树受现有 worktree 占用限制，改动先在本工作目录落地）。

## 1) 调研结论

- 主门禁要保持“确定性优先”，不把已知 flaky 用例混入阻塞链路。
- flaky 用例必须“可观测 + 可追责”，不能只依赖重试掩盖信号。
- CI 改造应最小增量，可随时回滚。

## 2) 来源链接

- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
- https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows
- https://docs.pytest.org/en/stable/explanation/flaky.html
- https://playwright.dev/docs/test-retries
- https://martinfowler.com/articles/nonDeterminism.html
- https://testing.googleblog.com/2016/05/flaky-tests-at-google-and-how-we.html

## 3) 适用边界

- 当前仓库后端测试流（pytest + GitHub Actions）。
- 优先保证 nightly/PR 主链路稳定，不做大规模测试重构。

## 4) 落地步骤

1. `.github/workflows/backend-tests.yml`：
   - unit/integration lane 排除 flaky marker。
   - 新增 `flaky-observe` job（非阻塞、artifact 输出）。
2. `main/backend/pytest.ini`：新增 `flaky` marker。
3. `main/backend/scripts/flake_report.py`：junit -> markdown 摘要脚本。
4. `main/backend/tests/quarantine/README.md`：建立隔离规范入口。
5. 新增单测 `test_flake_report_unittest.py` 保障报告脚本可维护。

## 5) 风险与回滚

- 风险：flaky 标记被滥用后主门禁“假稳定”。
- 回滚：单次回退上述 5 处改动即可恢复前态。

## 6) 预期收益

- 主 CI lane 失败信号更纯净。
- flaky 噪声改为观察面板，便于后续治理与责任归档。

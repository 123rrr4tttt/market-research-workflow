<!-- docs-root-migration: content moved -->
> Status: content moved; target authoritative after Wave31 archive-closed batch.
> Previous compatibility source: `development/latest-dev-docs/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan/03_A-line-round3-stage1-research-CI-regression-flake-2026-03-03.md`
> Authoritative target: `docs/development/development-plans/ARCHIVE_CLOSED/2026-03-03-version-A-atomic-plan/03_A-line-round3-stage1-research-CI-regression-flake-2026-03-03.md`
> Migration batch: `development-plans-archive-closed-wave31-batch`
> Date: 2026-05-23

# A线第3轮-阶段1（先检索再开发）：CI稳定性 / 回归可靠性 / Flake治理

日期：2026-03-03
约束：本阶段仅联网调研与文档沉淀，不改业务代码。

---

## 一、调研摘要（给后续开发指令用）

本轮确认的共识：

1. **CI稳定性先于功能扩展**：先消除并发冲突、超时失控、缓存污染，再谈回归扩展。
2. **Flake必须显性化**：重试可作为过渡，但必须保留首轮失败信号并纳入门禁统计。
3. **回归可靠性核心在“确定性”**：固定环境、固定数据、控制外部依赖、去除隐式时序。
4. **治理要分层**：主干阻塞层（确定性）与噪声观察层（flake隔离）并行，避免互相拖垮。

---

## 二、来源链接（官方/成熟开源）

- GitHub Actions workflow syntax:
  https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions
- GitHub Actions concurrency:
  https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
- GitHub Actions cache:
  https://docs.github.com/en/actions/using-workflows/caching-dependencies-to-speed-up-workflows
- GitHub Actions reusable workflows:
  https://docs.github.com/en/actions/using-workflows/reusing-workflows
- pytest flaky tests:
  https://docs.pytest.org/en/stable/explanation/flaky.html
- Playwright retries:
  https://playwright.dev/docs/test-retries
- pytest-rerunfailures:
  https://pypi.org/project/pytest-rerunfailures/
- Martin Fowler nondeterminism in tests:
  https://martinfowler.com/articles/nonDeterminism.html

---

## 三、可落地步骤（A线下一阶段可直接执行）

### 3.1 CI 稳定性（P0）

- 在主 workflow 添加并发组与取消策略：
  - `concurrency.group: <workflow>-<branch>`
  - `cancel-in-progress: true`
- 为长任务加 `timeout-minutes`。
- 收敛 matrix 并发（`max-parallel`）并明确 `fail-fast` 策略。
- 缓存 key 基于 lockfile/hash，避免脏缓存复用。

### 3.2 回归可靠性（P0/P1）

- 固化测试运行环境（语言版本、镜像、依赖锁）。
- 固定随机种子与基准测试数据快照。
- 外部依赖分层：单测 mock、集测可控替身、E2E最小外部依赖。
- 去除固定 sleep，改为条件等待。

### 3.3 Flake治理（P0/P1）

- 建立 flaky 标记与隔离清单（quarantine）。
- 重试仅限已标记用例（默认不重试）。
- 报告拆分：first-run fail / retried-pass / hard-fail。
- 周维度输出 top flaky tests 与归因分类。

---

## 四、适用边界

- 适用于 GitHub Actions 为主的 CI 体系。
- 测试框架可异构（pytest/Playwright/Jest 等），治理方法可统一抽象。
- 若当前项目仍处快速试错早期，可先落最小门禁，不宜一次性加重全部阻塞规则。

---

## 五、风险与回滚

### 风险

1. 过早强门禁导致开发流速骤降。
2. 过度重试掩盖真实回归。
3. 隔离区扩大后，主干质量“看起来变好”但真实问题未减少。

### 回滚策略

- CI策略回滚：恢复上一版 workflow YAML。
- 重试回滚：全局 retries -> 0，仅保留统计埋点。
- 门禁回滚：阻塞规则降级为告警，不删观测数据。

---

## 六、建议原子任务表（供下一回合并行编排）

| 原子任务ID | 任务 | 产出 | 并行性 | 依赖 |
|---|---|---|---|---|
| A3-S1-T1 | 盘点现有 CI workflows 的并发/超时/缓存现状 | `ci-baseline-audit.md` | 可并行 | 无 |
| A3-S1-T2 | 定义 CI 稳定性最小策略模板（concurrency/timeout/cache） | `ci-stability-template.yml.md` | 可并行 | T1 |
| A3-S1-T3 | 设计 flake 统计口径与报告字段 | `flake-metrics-spec.md` | 可并行 | 无 |
| A3-S1-T4 | 建立 flaky 用例隔离清单格式与准入准出规则 | `flake-quarantine-policy.md` | 可并行 | T3 |
| A3-S1-T5 | 设计回归分层门禁（阻塞层/观察层） | `regression-gate-policy.md` | 可并行 | T1,T3 |
| A3-S1-T6 | 汇总为 A线第3轮-阶段2执行计划（只含可执行变更） | `A-line-round3-stage2-implementation-plan.md` | 串行收敛 | T2,T4,T5 |

---

## 七、知识池落盘位置

- `信息源库/CI-回归可靠性-Flake治理-最佳实践-2026-03-03.md`

本文件为 CURRENT_DEV 执行指令侧入口；知识池文件为后续复用沉淀入口。

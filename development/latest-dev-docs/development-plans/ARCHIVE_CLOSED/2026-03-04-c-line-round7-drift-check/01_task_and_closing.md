# C线 Round7（2026-03-04）— Contract Drift Check 最小增强

## 目标
- 延续 contract-first 路线，新增“可执行的漂移检测失败用例”，确保产物被篡改时门禁失败。

## 原子任务
- C7-A1：在 `pre_release` 产物校验单测中增加 drift 失败注入样例。
- C7-A2：执行单测，确认 pass-path 与 drift-fail-path 均可复现。

## 实现变更
- `main/backend/tests/unit/test_pre_release_report_bundle_unittest.py`
  - 新增 `test_pre_release_verify_detects_manifest_drift`
  - 逻辑：先生成 bundle，再篡改 `release-notes.md`，最后断言 verify 脚本失败（checksum mismatch）。

## 验证命令与结果
```bash
python3 -m pytest tests/unit/test_pre_release_report_bundle_unittest.py -q
```
结果：`2 passed`

## 风险
- 当前 drift 检测基于 sha256 文件完整性，不能覆盖“内容语义未变但格式变化导致差异”的白名单需求；后续如需白名单机制需单独设计。

## 回滚点
- 回滚文件：`main/backend/tests/unit/test_pre_release_report_bundle_unittest.py`
- 回滚方式：`git checkout -- main/backend/tests/unit/test_pre_release_report_bundle_unittest.py`

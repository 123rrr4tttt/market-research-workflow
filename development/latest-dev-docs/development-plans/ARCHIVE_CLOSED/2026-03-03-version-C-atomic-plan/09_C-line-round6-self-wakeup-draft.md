# C线第6轮自唤醒任务草案（待执行）

## R6-Goal
将 round5 的 artifact verify 能力推进到“strict 演练 + CI 接入 + 失败可诊断”。

## 四步执行框架
1. **先检索**：补充 GitHub Actions artifact 最佳实践（上传、保留期、下载后校验）并沉淀到知识池。
2. **再计划**：形成 round6 原子任务表（CI job 拆分、依赖、门禁、owner、产物）。
3. **后实现**：
   - 在 `.github/workflows/backend-tests.yml` 增加 pre-release artifact verify job（非破坏式先 warn-only）
   - 新增 strict 演练脚本（可本地复现失败用例）
4. **再封口**：输出 round6 closure + 更新 index/README。

## 原子任务建议
- C6-AT-01：知识池 round6 调研文档
- C6-AT-02：CI workflow 增量 job（artifact upload/download + verify）
- C6-AT-03：strict drill 脚本与示例假数据
- C6-AT-04：单测/脚本测试补齐
- C6-AT-05：封口文档与索引更新

## 门禁
- G1：workflow yaml 语法通过
- G2：本地 verifier 对“篡改文件”能正确失败
- G3：默认流水线不回归（quick pass）

# RAG Line Round3 - Metadata Filter Robustness Minimal Enhancement (2026-03-04)

## 目标
- 在不改变 `MinimalRAG` 公开接口的前提下，提升 `metadata_filter` 的过滤鲁棒性。
- 本次仅做最小增量：大小写兼容、列表匹配、空值过滤项容错。

## 原子任务
1. 增强 `main/backend/app/services/rag/minimal_rag.py` 中 `_metadata_match`。
2. 在 `main/backend/tests/unit/test_minimal_rag_unittest.py` 增加覆盖上述行为的单元测试。
3. 运行最小验证命令，确认新增行为可运行且无回归。

## 实现变更
- 文件：`main/backend/app/services/rag/minimal_rag.py`
  - 保持 `retrieve(..., metadata_filter=None)` 和 `answer(..., metadata_filter=None)` 接口不变。
  - `_metadata_match` 增强为：
    - 过滤值字符串按 `strip + casefold` 做大小写与首尾空白归一化。
    - 支持 metadata 值与 filter 值在“标量/列表”间的交集匹配（成员命中即匹配）。
    - `metadata_filter` 中空值（`None`、空字符串、仅空白、空集合）按“忽略该过滤项”处理。
    - metadata key 支持大小写不敏感回退匹配（如 `lang` 与 `Lang`）。
  - 新增私有 helper：`_is_empty_filter_value`、`_metadata_value_match`、`_normalize_value_tokens`。
- 文件：`main/backend/tests/unit/test_minimal_rag_unittest.py`
  - 新增 `test_minimal_rag_metadata_filter_robustness`，覆盖：
    - value 大小写兼容（`EN` 匹配 `en`）。
    - metadata 列表匹配标量 filter（`tags=[finance, ai]` 匹配 `AI`）。
    - filter 列表匹配标量 metadata（`lang=[en, zh]` 可命中 `ZH`）。
    - 空过滤值忽略（`{"source": ""}` 与无过滤行为一致）。

## 验证命令与结果
- 命令：`cd main/backend && python3 -m pytest tests/unit/test_minimal_rag_unittest.py -q`
- 结果：`3 passed in 0.02s`

## 风险
- 过滤语义较之前更宽松，可能返回此前因严格等值比较被排除的候选。
- key 大小写回退在极端场景下可能掩盖上游 key 命名不一致问题。

## 回滚点
- 代码回滚文件：
  - `main/backend/app/services/rag/minimal_rag.py`
  - `main/backend/tests/unit/test_minimal_rag_unittest.py`
- 若需快速回滚行为：恢复 `_metadata_match` 为严格 `metadata.get(k) == v` 比较，并移除新增鲁棒性测试。

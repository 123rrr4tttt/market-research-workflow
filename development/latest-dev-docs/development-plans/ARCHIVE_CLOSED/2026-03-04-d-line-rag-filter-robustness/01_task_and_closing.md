# D线 Round3（2026-03-04）— RAG 检索过滤鲁棒性增量

## 目标
- 在不改变 RAG 主流程接口的前提下，增强 `metadata_filter` 鲁棒性并验证。

## 原子任务
- D3-A1：在 `MinimalRAG` 过滤逻辑支持大小写无关 key/value、列表与标量互匹配、空值忽略。
- D3-A2：补充单测覆盖以上场景并执行验证。

## 实现变更
- `main/backend/app/services/rag/minimal_rag.py`
  - 过滤逻辑包含：
    - key case-insensitive 匹配
    - value 归一化（字符串去空白 + casefold）
    - list/tuple/set 与标量互匹配
    - 空过滤值（`None`/空串/空列表）自动忽略
- `main/backend/tests/unit/test_minimal_rag_unittest.py`
  - 新增/完善 `test_minimal_rag_metadata_filter_robustness` 覆盖上述鲁棒性场景。

## 验证命令与结果
```bash
python3 -m pytest tests/unit/test_minimal_rag_unittest.py -q
```
结果：`3 passed`

## 风险
- 目前 metadata filter 仍为“扁平匹配”，不支持深层嵌套对象路径过滤（如 `metadata.author.lang`）。

## 回滚点
- 回滚文件：
  - `main/backend/app/services/rag/minimal_rag.py`
  - `main/backend/tests/unit/test_minimal_rag_unittest.py`
- 回滚方式：`git checkout -- <files>`

#!/usr/bin/env bash
# Retired: the previous generator rewrote historical indexes across projects.
set -euo pipefail

cat >&2 <<'MESSAGE'
旧文档批量生成入口已退役。
当前文档从 docs/README.md 进入，开发说明在 docs/development/README.md。
本入口不再创建旧阶段目录或改写历史索引。
原脚本可从 Git 检查点查询：git show ee10a848:scripts/docs_only_workflow.sh
MESSAGE
exit 2

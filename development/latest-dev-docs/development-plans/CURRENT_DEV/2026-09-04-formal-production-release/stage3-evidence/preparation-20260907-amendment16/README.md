# 冻结前 Stage3 准备

本目录是合同16要求的只读准备结果，不是新候选验收。没有重跑v6 suites，没有创建容器、数据库或其他测试服务。

环境刷新见 `environment/assessment.v1.md`：Docker daemon仍不可达；Python3.11与PostgreSQL工具可用，专用DB尚未建立；Node22仅在指定路径未确认；签名与扫描工具存在明确PATH缺口。由原Stage1/2唯一环境owner固定预演root、资源名称、工具/依赖与隔离策略，再运行依赖它们的门禁。

门禁覆盖补充见 `gates/`。合同必需family与已有观察性job分别标识；每条命令须绑定最终预演root与环境。当前dirty源码的workflow改进只作为准备快照，不能作为新候选PASS。

外部准入见 `external-admission.v1.json`。公共API再次返回旧v6 SHA不存在、0runs、main未保护且有效规则为空。新候选SHA尚未提供；不得把旧SHA查询当新候选核验。尚待用户决定的四类事项是：接受候选的远端执行、目标分支强制规则、持久registry命名空间与发布范围、已有签名的信任策略或单独签名授权。每项含目标、scope、风险、owner及前置；本次未执行这些变更。

复用v6已有负面证据：秘密扫描346条历史发现仍需逐类裁决，不能称346个有效凭据；non-PyPI functorial-kit的strict审计覆盖需明确处置；DNS失败注入无法封锁native/subprocess连接。前端e2e需要专用可用后端，不能使用不可达代理获得完整验收。未来阶段保持未准入。

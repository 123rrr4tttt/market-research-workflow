# C线第7轮草案（strict 阻断 + 漂移检测）

## 目标
1. 做一次 strict 失败注入演练，验证阻断链路真实生效。
2. 在 CI 中新增 contract 漂移检测：产物集合变化必须同步修改 contract。
3. 输出“失败样本 + 恢复样本”双证据，避免仅 happy-path。

## 原子任务（草案）
- C7-AT-01：定义故障注入场景（obs.result=warn、manifest 缺项）
- C7-AT-02：补充 verifier 失败码与错误分类
- C7-AT-03：新增 CI job（contract drift check）
- C7-AT-04：补充单测（strict fail/pass 双分支）
- C7-AT-05：封口文档 + 回滚脚本

## 门禁
- G1：strict 注入失败必须阻断
- G2：恢复后 strict 必须通过
- G3：CI 漂移检测 job 为 required

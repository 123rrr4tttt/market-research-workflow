# R8.1-D 可验收最小交付（Security & Supply Chain）

## 范围
对应 reference pack 的 D 切片 Must 项，提供可审计基线清单。

## Must 基线

### 1) SBOM + 签名验签
- 构建产物生成 SPDX SBOM
- 产物签名后发布
- 验签失败阻断发布

### 2) CI 必经门禁
- secret scanning
- dependency scanning
- image scanning

### 3) 最小权限复核
- 角色最小化（RBAC）
- token 生命周期最小化
- 网络暴露面最小化

## 验收命令
```bash
python3 scripts/verify_r8_1_d.py
```

预期：输出 `R8.1-D verification passed` 且退出码 0。

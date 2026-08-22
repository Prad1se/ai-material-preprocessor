## 变更摘要 / Summary

## 原因 / Why

## 影响范围 / Impact

## 验证 / Verification

- [ ] 新行为包含测试，缺陷包含回归测试。/ New behavior has tests; defects have regression tests.
- [ ] 完整测试、Ruff、mypy 与 `git diff --check` 均通过。/ Full tests, Ruff, mypy, and `git diff --check` pass.
- [ ] 中文路径和包含空格的路径仍然安全。/ Chinese and space-containing paths remain safe.
- [ ] 未包含私人文件、凭据、生成结果或大型临时文件。/ No private files, credentials, generated outputs, or large temporary files are included.
- [ ] 原始素材不会被覆盖或删除。/ Original source files are never overwritten or deleted.
- [ ] 必要的文档与变更记录已经更新。/ Documentation and changelog are updated.

## 风险与回滚 / Risks and rollback

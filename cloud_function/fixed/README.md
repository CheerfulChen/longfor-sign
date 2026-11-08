# 华为云固定触发版

每日固定 TIMER，一次处理整批账号。使用与 Docker、基础脚本和随机云函数相同的 core/，支持独立 APP token、两套 UA、自动验证与日历复核。

默认无需 OBS，续期凭据保存于 /tmp；可选 OBS 以跨实例保存。代码包必须包含 core/，不能只上传 main.py。

[部署说明](../../docs/functiongraph.md) · [公共配置](../../docs/configuration.md) · [迁移说明](../../MIGRATION.md)

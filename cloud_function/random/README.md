# 华为云随机时间版

保留四账号每日随机计划与半小时检查，使用 OBS 保存任务、通知和续期凭据。业务部分调用同一份 core/，已同步独立 APP token、两套 UA、自动验证与日历复核。

保留已有 OBS 前缀和稳定账号标识，整包升级，勿删除当日记录。Python 3.9 运行依赖按包内 requirements.txt 更新。

[部署说明](../../docs/functiongraph.md) · [公共配置](../../docs/configuration.md) · [迁移说明](../../MIGRATION.md)

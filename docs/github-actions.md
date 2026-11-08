# GitHub Actions（保留，不推荐）

原工作流 `.github/workflows/daily-sign.yml` 继续保留，运行根目录 `main.py` 基础脚本，不会启动 Docker 面板，也不调用华为云随机调度器。

**不推荐作为长期自动签到的主要部署方式。** 建议使用自己的 Docker 服务，或选择华为云固定触发版 / 随机时间版。GitHub 官方说明，定时任务在高负载时可能延迟，严重时排队任务可能丢弃；公开仓库连续 60 天没有活动时，定时工作流会自动停用。见 [GitHub schedule 官方说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

## 继续使用

1. Fork 或使用自己的仓库，在 Settings → Secrets and variables → Actions 中添加 Repository secrets：`LONGFOR_TOKEN`、`LONGFOR_DXRISK_TOKEN`，以及可选的 `BARK_KEY`。
2. 多账号值使用基础脚本支持的逐行格式，token 与风控值顺序保持一致，详见 [基础版文档](basic.md)。同时支持公共 `*_JSON` 数组格式，非空时优先使用 JSON。
3. 可选的 APP Secrets：`LONGFOR_APP_TOKENS_JSON`、`LONGFOR_APP_DXRISK_TOKENS_JSON`。在 Repository variables 中设置 `SIGN_APP_ACCOUNT_IDS_JSON` 开启对应账号；账号标识、名称与两端 UA 数组也可按工作流变量配置，详见 [公共配置](configuration.md)。
4. 可选 Repository variable：`BARK_SERVER`，用于原有 Bark 服务器配置。
5. 在 Actions 中启用原签到工作流；Fork 后请检查定时工作流是否需要手动启用。可以通过 Run workflow 手动执行，这会真实签到。

现有工作流使用 `0 1 * * *`，即每日 UTC 01:00、北京时间 09:00；预定触发时间不保证实际准点开始。只修改 cron 即可改变预定时间，保留原有手动触发入口。

工作流安装根目录 `requirements.txt`、执行 `python main.py`，并按原设置上传验证码图片到运行产物。业务功能调用与 Docker 相同的公共核心，已支持独立 APP 凭据、UA 和自动验证；调度仍由 Actions 负责，不会启动网页面板。

同一批账号请选择一个运行入口；不要同时开启 Actions、固定云函数、随机云函数和 Docker 自动签到。

[返回 README](../README.md)

Actions 默认不跨 runner 保存新登录 token，`.state` 不能作为公开 artifact 上传。原 Secrets 失效时需要手动更新；这也是仍不推荐该部署方式的原因之一。

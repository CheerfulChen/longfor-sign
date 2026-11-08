# 版本与入口

所有运行入口统一调用 `core/` 的账号配置、登录续期、签到、验证码与结果复核逻辑。源码只维护一套，构建云函数 ZIP 时将同一份核心带入包中。

| 入口 | 调度方式 | 状态 |
| --- | --- | --- |
| Docker 管理面板 | 常驻服务，全天或指定时间段随机 | SQLite 数据卷 |
| 基础脚本 | 一次调用整批执行，定时器由用户配置 | 本地私有状态目录 |
| GitHub Actions（保留，不推荐） | 原定时与手动工作流 | runner 临时状态 |
| 华为云 fixed（旧调度方式） | 每日固定 TIMER，整批执行 | 可选 OBS，否则函数临时目录 |
| 华为云 random（新调度方式） | 半小时 TIMER，四账号每日随机计划 | 必需 OBS |

旧版/新版指调度方式，不再表示业务功能新旧。两种云函数都支持独立 APP 凭据、独立 UA、自动验证和日历复核。入口特有的面板、调度与状态后端分别维护。

```text
longfor-sign/
├── core/                         # 唯一的公共业务核心
├── server/                       # 管理面板与 SQLite 调度
├── cloud_function/
│   ├── fixed/                    # 固定触发入口
│   └── random/                   # 随机计划入口与兼容适配
├── scripts/build_functiongraph.py
├── .github/workflows/
│   ├── daily-sign.yml            # 保留，不推荐
│   └── ci.yml                    # 测试与导入包校验
├── tests/
├── main.py                       # 基础/Actions 入口
├── Dockerfile
└── compose.yaml
```

根目录旧的图像分析和 JS 研究文件保留供查阅；运行入口使用 core/captcha_support，不从旧实验脚本导入业务处理。

## 构建与发布

`python3 scripts/build_functiongraph.py --version dev` 在 dist/functiongraph 生成 fixed/random 各自的完整导入包、代码更新包及 SHA256SUMS。代码更新包包含根目录入口、core/ 和 requirements.txt。完整导入包在外层放 YAML 与它引用的 main.zip。

CI 对 Python 3.9 与 3.12 测试，并构建校验 ZIP。发布到 GitHub Releases 与镜像仓库仍需明确执行发布，不会因为本地提交代码就自动部署或发布。

升级前查看 [迁移说明](../MIGRATION.md)，备份各自状态。云函数、Actions 和 Docker 不要同时对同一批账号开启自动签到。

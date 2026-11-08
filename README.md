<div align="center">

<img src="docs/assets/logo.svg" width="120" height="120" alt="Longfor Sign Logo" />

# Longfor Sign

### 龙湖签到，从一个脚本到一套服务。

多账号 · 每日随机计划 · 小程序与 APP · 验证处理 · Bark 推送

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](docs/basic.md)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](docs/docker.md)
[![FunctionGraph](https://img.shields.io/badge/Huawei_Cloud-FunctionGraph-F66F6A?style=flat-square)](docs/functiongraph.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-70E3BB?style=flat-square)](LICENSE)

**[快速开始](#快速开始) · [部署方式](#选择部署方式) · [账号配置](docs/configuration.md) · [升级说明](MIGRATION.md) · [开发手记](docs/development-story.md)**

[使用反馈](https://github.com/CheerfulChen/longfor-sign/issues) · [版本发布](https://github.com/CheerfulChen/longfor-sign/releases)

</div>

---

Longfor Sign 从一个小程序签到脚本起步，现在可以在自己的服务器上通过 Docker 运行，也保留基础脚本、GitHub Actions 和两种华为云函数入口。

所有入口调用同一份 `core/`：账号登录续期、独立 APP 配置、默认 UA、验证码处理和签到日历复核统一维护。旧版与新版云函数区分的是调度方式，业务功能同步更新。

## 选择部署方式

| 方式 | 适合的场景 | 调度与数据 |
| --- | --- | --- |
| **Docker 管理面板** | 有常开的服务器或 NAS，希望在网页管理账号 | 全天或指定时段随机，SQLite 持久化数据卷 |
| **华为云固定触发版 fixed** | 每天固定时间启动，单次完成整批账号 | 每日 TIMER，可选 OBS 保存续期凭据 |
| **华为云随机时间版 random** | 四个账号在全天随机分散执行 | 半小时 TIMER，OBS 保存计划、凭据和通知进度 |
| **基础脚本** | 单次运行，或自行配置定时器 | 本地 `.state` 保存续期凭据 |
| **GitHub Actions（保留，不推荐）** | 沿用原有定时和手动工作流 | runner 临时状态，仍使用相同签到核心 |

同一批账号请选择一个自动调度入口，避免多个服务同时执行。入口特有的调度和存储差异见 [版本说明](docs/versions.md)。

## 快速开始

### Docker 管理面板

```bash
git clone https://github.com/CheerfulChen/longfor-sign.git
cd longfor-sign
cp .env.example .env.server
```

编辑 `.env.server`，设置至少 12 位的 `ADMIN_PASSWORD`；样例密码会被程序拒绝。随后：

```bash
docker compose up -d --build
```

浏览器打开 `http://127.0.0.1:8088`。登录后添加账号，在「计划与推送」选择全天随机或指定时段，设置账号最小间隔与 Bark Key。

远程服务器默认只监听本机地址，可用 SSH 隧道访问：

```bash
ssh -L 8088:127.0.0.1:8088 用户名@服务器地址
```

完整部署、HTTPS、备份和升级见 [Docker 指南](docs/docker.md)。

### 华为云函数

本地构建两个版本的完整导入包和代码更新包：

```bash
python3 scripts/build_functiongraph.py --version dev
```

产物位于 `dist/functiongraph/`，文件名以 `fixed` / `random` 区分。完整导入包包含 YAML 和它引用的源码 ZIP；代码更新包包含入口、公共核心及依赖清单。公开模板不含个人凭据。

华为云原生依赖继续使用独立 ZIP，经 OBS 上传后关联到函数。构建和关联步骤见[华为云依赖包说明](docs/functiongraph.md#构建依赖-zip通过-obs-关联)。

固定版每日触发一次，随机版每半小时检查。运行时、依赖层、OBS、委托和配置见 [华为云指南](docs/functiongraph.md)。

### 基础脚本

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
export LONGFOR_TOKEN='自己的小程序登录token'
export LONGFOR_DXRISK_TOKEN='该账号的小程序风控token'
python main.py
```

多账号、独立 APP 和 UA 配置见 [基础脚本](docs/basic.md) 与 [公共配置](docs/configuration.md)。脚本不会自动读取 `.env`。

### GitHub Actions（保留，不推荐）

保留 `.github/workflows/daily-sign.yml` 的每日定时和手动入口，兼容原 Secrets，同时支持公共 JSON 数组配置与独立 APP 账号。长期部署优先选择 Docker 或华为云。限制和设置见 [Actions 指南](docs/github-actions.md)。

## 签到与凭据

- 小程序和 APP 分别保存登录 token、DXRisk token、UA；按各自活动编号、渠道和风控来源发送请求。
- 执行前尝试续期小程序登录 token，保存后再签到。APP 登录 token 和 DXRisk token 当前仍手动更新。
- 签到前查日历，已签则跳过；请求后复核日历，确认后才记录成功。
- 遇到支持的风控响应且确认未签时，自动尝试一次原有验证码处理，验证后再决定是否重新提交。
- 将验证返回的完整值原样填入 Captcha 请求头，不自行追加 `:challenge`；结果不确定或验证失败时停止重复请求。
- 按账号推送或汇总推送，具体补发机制取决于运行入口。Docker 与随机云函数的通知补发不会重新触发签到。

验证码识别使用已有算法，真实通过率与服务端响应有关。本地测试使用模拟请求，不调用真实签到接口。登录、风控与验证凭据的区别见 [凭据说明](docs/credentials.md)。

## Docker 面板

账号增删改、启停、小程序与 APP 凭据分别配置；总览展示今日计划与下次任务，记录页显示执行结果，计划页设置时间段、时区、最小间隔和 Bark。

时间每天重新随机，账号顺序随机；已生成的计划保存在 SQLite，容器重启后沿用。自动任务只在指定时段内启动，按上一个账号实际结束时间计算最小间隔。支持同一天的时间段，默认全天为 00:00～23:50。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [Docker](docs/docker.md) | 部署、面板、随机时段、备份与升级 |
| [华为云](docs/functiongraph.md) | 固定版/随机版、ZIP、依赖、OBS 与触发器 |
| [公共配置](docs/configuration.md) | 各入口统一的账号变量、UA 和持久化差异 |
| [基础脚本](docs/basic.md) | Python 单次运行 |
| [GitHub Actions](docs/github-actions.md) | 保留，不推荐；Secrets 和限制 |
| [凭据说明](docs/credentials.md) | 登录、风控、验证码与续期 |
| [版本说明](docs/versions.md) | 公共核心、目录与构建约定 |
| [迁移说明](MIGRATION.md) | 旧环境升级到统一核心 |
| [开发手记](docs/development-story.md) | 项目经历与后续博客链接 |

## 开发与验证

```bash
python3 -m pip install -r requirements-server.txt pytest
python3 -m pytest -q
python3 scripts/build_functiongraph.py --version dev
```

CI 检查 Python 3.9 和 3.12，并构建云函数包。Docker 镜像从源码构建；推送源码、本地提交、发布 Release 与更新线上函数是分别执行的操作。

## 反馈与许可

问题反馈请附部署入口、版本、脱敏日志和复现步骤，不要上传登录 token、DXRisk token、Bark Key、数据库或抓包凭据。

感谢 [ken861222/longhu-checkin](https://github.com/ken861222/longhu-checkin) 对续期、APP 入口和服务化部署的公开探索，以及 Requests、Flask、OpenCV、Pillow 等开源项目。

采用 [MIT License](LICENSE)。这是个人开发的非官方项目，与龙湖官方无关联，用于本人或已获授权账号的学习与管理。

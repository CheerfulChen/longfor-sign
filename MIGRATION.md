# 升级到统一核心

本次将各入口的业务逻辑统一到 `core/`，保留 Docker、基础脚本、GitHub Actions、华为云固定触发与随机时间五个入口。

## 通用变化

- 小程序和 APP 分别配置登录 token、风控 token、UA。
- 开启 APP 的环境变量入口新增必填 `LONGFOR_APP_TOKENS_JSON`。不能继续用小程序 token 代替；暂不使用 APP 时先将 `SIGN_APP_ACCOUNT_IDS_JSON` 设为 `[]`。
- 原 `LONGFOR_TOKEN` / `LONGFOR_DXRISK_TOKEN` 换行格式继续支持；不同账号必须逐个提供风控值，不再自动复用第一个值。
- 小程序登录 token 自动续期；APP token 和 DXRisk token 仍手动更新。
- 验证成功返回的完整值原样写入 Captcha 请求头，不按客户端额外拼接后缀。

## Docker

备份完整数据卷（含 `.key`），重新构建后启动。旧数据库自动补充独立 APP 登录与两套 UA 字段。旧账号已开启 APP 但缺少独立登录 token 时，小程序继续处理，APP 提示补充配置，不冒用小程序凭据。

## 华为云随机版

1. 保留原 OBS 前缀、账号标识、顺序和配置中的小程序 token，不删除当日记录或 credentials.json。
2. 用新的 random-code ZIP 更新代码。新包已包含公共 core/，不要只上传 main.py 或 account_service.py。
3. 使用包内 requirements.txt 更新或重建运行依赖层；Python 3.9 保持可用。
4. 开启 APP 时配置独立 APP token、风控值和可选 UA。四个位置保持一一对应。
5. 保留原半小时触发器和单实例、单并发设置。

OBS 中原 version=1 凭据登记和 version=2 每日计划继续读取。手动重新登录时更改对应环境变量的 token，执行器会按稳定账号标识更新登记。

## 华为云固定版

使用新的 fixed-code ZIP 更新整包及依赖，保留每日固定触发器。默认仍不要求 OBS；如需跨实例持久保存续期结果，可选配置独占 OBS 前缀。不要切换成随机版的半小时触发频率来执行固定版。

## 基础脚本与 Actions

更新源码和 requirements.txt。基础脚本的 .state 不删除；GitHub Actions 继续保留原有 Secrets，新增 JSON 与 APP 配置可选。Actions 默认不保留跨 runner 的续期凭据，不能据此承诺永久免更新 Secrets，仍不推荐作为长期部署方式。

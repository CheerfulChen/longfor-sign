# 公共签到配置

基础脚本、GitHub Actions、华为云固定版和随机版读取相同的环境变量。Docker 通过网页编辑对应的字段，不需要再配置这些账号环境变量。

| 变量 | 说明 |
| --- | --- |
| `LONGFOR_TOKENS_JSON` | 小程序登录 token 数组，例如 `["小程序账号1token","小程序账号2token"]` |
| `LONGFOR_DXRISK_TOKENS_JSON` | 同顺序的小程序风控值，必须逐账号填写 |
| `LONGFOR_TOKEN` / `LONGFOR_DXRISK_TOKEN` | 兼容原有逐行配置；对应 JSON 变量非空时优先使用 JSON |
| `SIGN_ACCOUNT_IDS_JSON` | 稳定标识，默认 account-1、account-2……；配置后保持与账号顺序对应 |
| `SIGN_ACCOUNT_NAMES_JSON` | 显示名称，默认账号1、账号2…… |
| `SIGN_APP_ACCOUNT_IDS_JSON` | 开启 APP 的账号标识数组，默认 `[]` |
| `LONGFOR_APP_TOKENS_JSON` | 独立 APP 登录 token 数组；未配置的位置填 `""` |
| `LONGFOR_APP_DXRISK_TOKENS_JSON` | 独立 APP 风控值数组；未配置的位置填 `""` |
| `LONGFOR_MINI_USER_AGENTS_JSON` | 可选，小程序 UA 数组，未配置位置填 `""` |
| `LONGFOR_APP_USER_AGENTS_JSON` | 可选，APP UA 数组，未配置位置填 `""` |
| `LONGFOR_USER_AGENT` / `LONGFOR_APP_USER_AGENT` | 可选，两端各自的通用 UA；未填写 UA 数组时使用 |
| `BARK_KEY` / `BARK_SERVER` | 推送 Key 和服务器 HTTPS 根地址 |
| `SIGN_STATE_DIR` | 基础脚本本地状态目录，默认 `.state`；固定云函数默认 `/tmp/longfor-sign-fixed` |
| `SAVE_CAPTCHA_IMAGES` | `true` 时保存验证图片及不含凭据的识别结果；默认关闭 |

所有显式填写的数组长度必须与账号数一致；只有 `SIGN_APP_ACCOUNT_IDS_JSON` 是标识子集，不要求等长。华为云随机版目前仍要求 4 个账号，其余批量入口按实际数组长度执行。

登录 token 和风控 token 是不同值；APP 与小程序分别保存。请求头中的 `token` 和 `X-LF-UserToken` 在各自客户端使用同一个登录值。不同账号不得复用同一登录 token 或风控 token。UA 可相同，它不是手机唯一编号。

## 默认 UA

小程序：

```text
Mozilla/5.0 (iPhone; CPU iPhone OS 27_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 MicroMessenger/8.0.80(0x18005030) NetType/WIFI Language/zh_CN miniProgram/wx50282644351869da
```

APP：

```text
Mozilla/5.0 (iPhone; CPU iPhone OS 18_7 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 &MAIAWebKit_iOS_com.longfor.supera_1.30.2_202610281019_Default_3.3.1.0
```

Docker 编辑时留空保留已有 UA；从未填写时使用各入口默认值。环境变量的数组空字符串则回落到对应客户端默认 UA。

## 续期与验证

所有入口执行前尝试续期小程序登录 token，并在实际签到前保存新的凭据。APP 登录 token 暂未验证独立续期链路，仍需手动更新，不会被小程序续期结果覆盖。DXRisk token 不自动续期。

所有入口使用同一套日历查询、自动验证码处理和结果复核。遇到支持的风控响应且日历确认仍未签到时，自动尝试一次验证，再查日历决定是否重试。验证接口返回的完整 token 直接写入 `X-LF-DXRisk-Captcha-Token`；已有的冒号和后缀原样保留，不自行追加第二段。验证凭据不替换登录 token，也不会自动保存为长期风控值。

验证码识别沿用项目已有算法；测试覆盖控制流程，实际是否通过以服务端响应和签到日历为准。

## 持久化位置

| 入口 | 凭据保存 |
| --- | --- |
| Docker | SQLite 数据卷，凭据加密；备份数据库与 `.key` |
| 基础脚本 | `.state/credentials.json`，私有权限、原子写入；文件含凭据，不上传 Git |
| GitHub Actions | 单次任务内有本地状态；默认不跨 runner 保存凭据，不上传 `.state`；原 Secrets 失效时需更新 |
| 华为云固定版 | 可选 OBS；未配置时保存到函数 `/tmp`，冷启动或实例回收后不保证保留 |
| 华为云随机版 | 必需 OBS，保留原前缀和 credentials.json，可继承已有续期凭据 |

需要固定云函数跨实例保留续期结果时，配置 `SIGN_OBS_BUCKET`、`SIGN_OBS_ENDPOINT`、独占的 `SIGN_OBS_PREFIX` 与执行委托。两个函数不能共享同一前缀。

[返回 README](../README.md)

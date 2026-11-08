# 基础脚本

基础脚本、Docker 与两种云函数使用同一个 `core/` 签到核心，支持小程序与可选 APP、独立 UA、小程序登录续期、自动验证码处理、日历复核和 Bark 推送。

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
export LONGFOR_TOKEN='自己的小程序登录token'
export LONGFOR_DXRISK_TOKEN='该账号的小程序风控token'
export BARK_KEY='自己的BarkKey'  # 可选
python main.py
```

需要 Python 3.9 或更高版本。脚本不会自动加载 `.env`。多账号可将 token 和风控值分别按换行填写，必须逐个对应；也支持 `LONGFOR_TOKENS_JSON` 和 `LONGFOR_DXRISK_TOKENS_JSON`。独立 APP 配置、UA 数组与状态保存见 [公共配置](configuration.md)。

一次调用按随机顺序处理整批账号，默认账号间隔 20～60 秒。`SIGN_START_DELAY_MIN_SECONDS` / `MAX_SECONDS` 控制开始前等待，默认 0；`SIGN_ACCOUNT_INTERVAL_MIN_SECONDS` / `MAX_SECONDS` 控制账号间隔。多账号间隔至少 1 秒。脚本本身不创建每日定时器，请按需要自行配置。

登录续期凭据保存在 `.state/credentials.json`，后续调用会使用已保存的值；更改配置中的原 token 表示手动重新绑定该账号。保持账号标识和顺序稳定。该文件含登录凭据，不要上传或分享。

成功退出码为 0，配置异常或有账号未完整成功时退出码为 1。结果不确定时请检查官方客户端日历，不自动重放已结束的任务。

需要检查识别图片时，设置 `SAVE_CAPTCHA_IMAGES=true`，图片与脱敏坐标结果保存到 `captcha_collection/`。调试图片不影响账号 token 配置；该目录默认不进入 Git。

[返回 README](../README.md)

# 华为云 FunctionGraph

保留两种调度方式，二者使用同一份最新公共核心，均支持小程序与可选 APP、独立 token 和 UA、小程序登录续期、自动验证码处理、日历复核和 Bark 推送。

## 选择调度方式

| 配置 | 固定触发版 fixed | 随机时间版 random |
| --- | --- | --- |
| 运行入口 | main.main | main.main |
| TIMER | 每天固定时间一次 | 每半小时一次 |
| 单次执行 | 整批账号，随机顺序、账号间隔 | 每次至多一个到期账号 |
| 账号数 | 按配置数量，须在超时内完成 | 当前要求 4 个 |
| OBS | 可选，用于跨实例保留续期凭据 | 必需，保存计划、进度和续期凭据 |
| 本地状态 | 无 OBS 时使用 /tmp，不保证跨冷启动保留 | 使用 OBS |

“旧版”和“新版”只区分调度方式，业务能力同步更新。不要同时开启两个函数来处理同一批账号；两个函数不能共用 OBS 前缀。

## ZIP 类型

```bash
python3 scripts/build_functiongraph.py --version dev
```

输出目录为 dist/functiongraph。发布构建时可将 dev 换成版本号。

| 文件名 | 用途 |
| --- | --- |
| longfor-sign-functiongraph-fixed-dev.zip | 固定版完整导入包 |
| longfor-sign-functiongraph-fixed-code-dev.zip | 已有固定函数更新代码 |
| longfor-sign-functiongraph-random-dev.zip | 随机版完整导入包 |
| longfor-sign-functiongraph-random-code-dev.zip | 已有随机函数更新代码 |
| SHA256SUMS | 文件完整性校验 |

完整导入包外层包含 functiongraph.yml 和 main.zip，在函数列表“导入函数”上传。代码更新包根目录包含 Python 入口、core/ 与 requirements.txt，在已有函数“上传代码 → ZIP 文件”上传。

不要只上传某一两个 Python 文件，也不要把代码更新包用于完整导入。模板没有真实账号、Bark Key 或桶名；导入后填写自己的配置。模板不创建定时器、委托、依赖层或并发设置。

## 运行设置与依赖

- Python 3.9，入口 main.main，超时 900 秒，内存按实际图像处理需求设置；建议从 256 MB 起验证。
- 最大实例数 1，单实例并发数 1（如可设置）。普通按量实例即可。
- 使用代码包内 requirements.txt，在与函数运行时和 CPU 架构一致的 Linux 环境中构建依赖层。不要直接使用 macOS 的虚拟环境目录。
- 共同依赖为 requests、Pillow、opencv-python-headless、NumPy。requirements.txt 为 Python 3.9 选择兼容的 NumPy 版本。
- 依赖层需要在控制台关联，上传源码 ZIP 不会自动安装依赖。

升级已有函数前查看 [MIGRATION.md](../MIGRATION.md)。新核心在 Python 3.9 上保持语法兼容，依赖的具体轮子须与函数架构相符。

## 构建依赖 ZIP，通过 OBS 关联

保留原来的 OBS 上传方式。源码 ZIP 与依赖 ZIP 分开：源码是本项目的 Python 文件，依赖包包含 OpenCV、NumPy、Pillow、requests 及其动态库。只上传 requirements.txt 不会自动安装它们。固定版和随机版在运行时与架构相同时，可以关联同一份依赖包。

在 Linux 的 Python 3.9 环境执行：

```bash
python3.9 scripts/build_functiongraph_deps.py --version dev
```

脚本安装根目录 requirements.txt 中的版本，保留 .libs 动态库，完成图像转换与导入检查，再将依赖直接压到 ZIP 根目录，并解压复验。输出示例：

```text
dist/functiongraph/longfor-sign-functiongraph-deps-python3.9-x86_64-dev.zip
dist/functiongraph/longfor-sign-functiongraph-deps-python3.9-x86_64-dev.zip.sha256
```

若在 Mac 上操作，通过 Docker 运行 Linux 构建环境。下面示例面向 x86_64 函数；ARM 函数改用 linux/arm64，输出名称会变为 aarch64：

```bash
docker run --rm --platform linux/amd64 \
  -v "$PWD:/project" -w /project python:3.9-slim \
  python scripts/build_functiongraph_deps.py --version dev
```

Python 版本、CPU 架构和底层动态库都要匹配函数环境。华为云[推荐使用 Huawei Cloud EulerOS 2.0 构建原生依赖](https://support.huaweicloud.com/devg-functiongraph/functiongraph_02_0616.html)；以上通用 Linux 容器检查不替代云端运行验证。若云端出现 GLIBC 或共享库错误，在匹配的 EulerOS 环境中使用同一脚本重新构建。不要把 macOS 安装出来的 cv2 目录上传。

关联步骤：

1. 将依赖 ZIP 上传到已有私有 OBS 桶，例如 dependencies/ 下；原有 deps.zip 可保留，便于回退。
2. 函数工作流 → 依赖包管理 → 创建依赖包，选择 Python 3.9，使用 OBS 中 ZIP 的地址创建版本。
3. 打开签到函数的“代码”页，在依赖包处关联刚创建的版本并保存；两个函数分别关联。
4. 再上传对应源码包。代码导入包中的 functiongraph.yml 不会替你创建或关联依赖包。

详细界面流程见华为云[为函数配置依赖包](https://support.huaweicloud.com/usermanual-functiongraph/functiongraph_01_2119.html)。依赖版本改变时重新构建并关联；仅改业务代码且 requirements.txt 未变时，可以复用已验证的依赖版本。

已有桶可以同时存放依赖 ZIP 和随机调度状态，分别使用 dependencies/ 与 longfor-sign/ 等不同前缀。前者是上传后的安装材料，后者由运行中的函数持续读写；下文的执行委托权限用于后者。

## 公共账号配置

变量名称、两端默认 UA 和格式见 [公共配置](configuration.md)。最少填写 LONGFOR_TOKENS_JSON 与 LONGFOR_DXRISK_TOKENS_JSON，按同一顺序一一对应。

开启 APP 时，另外配置 SIGN_APP_ACCOUNT_IDS_JSON、LONGFOR_APP_TOKENS_JSON 与 LONGFOR_APP_DXRISK_TOKENS_JSON。APP 登录 token 不沿用小程序 token，默认关闭 APP。可选的 LONGFOR_MINI_USER_AGENTS_JSON 与 LONGFOR_APP_USER_AGENTS_JSON 分别设置 UA。

小程序自动续期后的 token 在实际签到前保存。APP 登录 token 暂时手动更新；风控 token 也不自动续期。验证码验证通过后的完整返回值原样放入 Captcha 请求头，不自行拼接第二个后缀。

## 固定触发版

每天北京时间 09:00 调用一次的 TIMER 示例：

```text
CRON_TZ=Asia/Shanghai 0 0 9 * * *
```

开始前默认随机等待 0～300 秒，账号之间默认 20～60 秒，可使用 SIGN_START_DELAY_MIN_SECONDS / MAX_SECONDS、SIGN_ACCOUNT_INTERVAL_MIN_SECONDS / MAX_SECONDS 调整。所有等待和请求合计须在函数超时内完成。

固定版不创建 OBS 每日任务记录，调用一次处理一批。手动测试会真实执行整批账号；日历检查会跳过当天已签的活动。默认 /tmp 凭据只保证当前实例可用，若要跨实例保留，请配置下面的 OBS。

## 随机时间版

开启唯一一个半小时 TIMER：

```text
CRON_TZ=Asia/Shanghai 0 0,30 * * * *
```

每天为四个账号生成随机半小时时段计划，计划时段至少相隔 1 小时；到期后等待 10～90 秒再执行。无到期账号则结束调用，不全天保持运行。

当日计划、任务状态、单账号推送和每日汇总保存在 OBS。推送失败由后续检查补发，不因此重新签到。异常中断的任务标记为结果待确认，不自动重放；错过整天不补签昨天。

手动测试同样遵循真实计划，可能执行一个到期账号；idle 表示没有到期账号。不要删除当天状态来强制重签。

## OBS 与执行委托

随机版必填；固定版按需要选填：

| 变量 | 内容 |
| --- | --- |
| SIGN_OBS_BUCKET | 实际私有桶名 |
| SIGN_OBS_ENDPOINT | 桶所在区域，例如 obs.cn-east-3.myhuaweicloud.com，不带协议和桶名 |
| SIGN_OBS_PREFIX | 函数独占前缀；固定模板默认为 longfor-sign-fixed，随机模板为 longfor-sign |
| SIGN_NOTIFY_PLAN | 随机版额外推送每日计划，默认 0，设为 1 开启 |

在函数权限中关联执行委托，授予实际桶和独占前缀：

| 操作 | 资源 |
| --- | --- |
| obs:object:GetObject | obs:*:*:object:桶名/前缀/* |
| obs:object:PutObject | obs:*:*:object:桶名/前缀/* |
| obs:bucket:ListBucket | obs:*:*:bucket:桶名 |

对象权限与桶权限分别配置。缺少 ListBucket 时，读取尚不存在的记录可能得到 403，程序不会把它当作空记录。

通过函数运行上下文取得临时访问凭据，不在模板或环境变量中配置长期 AK/SK。OBS 不是分布式锁，同一前缀必须只有一个串行函数使用。

credentials.json 含最新登录凭据，应保持私有并长期保留。清理日期记录时不要误删它，也不要删除当天及前一天计划。OBS 存储、请求以及函数执行等待按云服务实际账单计费。

[返回 README](../README.md)

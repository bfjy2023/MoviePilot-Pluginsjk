# MoviePilot-Plugins

个人 MoviePilot V2 插件仓库，用于集中维护自开发插件。当前仓库只保留 V2 插件目录；后续新增插件也会放在同一个仓库内统一管理。

## 插件列表

| 插件 ID | 名称 | 版本 | 说明 |
| --- | --- | --- | --- |
| `UnCrossSeedChecker` | 未辅种检查器 | `1.0.0` | 检查下载器中指定站点的种子是否已辅种到其他站点，列出未辅种内容。 |
| `TangLottery` | 不可躺自动抽奖助手 | `1.0.1` | 按每日目标次数自动拆解并执行不可躺抽奖，记录历史、奖品汇总和任务通知。 |
| `ForumRssMonitor` | 论坛动态监控 | `1.2.0` | 监控论坛 RSS/Atom 动态和蜂巢(pting.club) API，默认推送最近 24 小时内的新帖。 |
| `PlayletLottery` | PlayLet自动抽奖助手 | `1.0.3` | 按每日目标次数自动拆解并执行 PlayLet 抽奖，记录历史、奖品汇总和任务通知。 |

## 仓库结构

```text
MoviePilot-Plugins/
├── icons/                         # 插件图标
├── package.v2.json                # V2 插件索引
└── plugins.v2/                    # V2 插件目录
    ├── forumrssmonitor/
    ├── playletlottery/
    ├── tanglottery/
    └── uncrossseedchecker/
```

本仓库不再维护默认版 `plugins/` 目录和 `package.json`，只维护 `plugins.v2/` 与 `package.v2.json`。

## 安装使用

在 MoviePilot 中进入插件仓库设置，将当前 GitHub 仓库地址添加为插件仓库。保存并刷新插件市场后，即可在插件市场中安装本仓库内的插件。

添加仓库后，MoviePilot 会读取：

- `package.v2.json`
- `plugins.v2/`

安装完成后，进入对应插件配置页启用插件并填写必要配置。

## 本地开发测试

本地开发测试时，可将仓库挂载到容器内：

```yaml
volumes:
  - ./MoviePilot-Plugins:/local-plugins
  - ./MoviePilot-Plugins/plugins.v2/forumrssmonitor:/app/app/plugins/forumrssmonitor
  - ./MoviePilot-Plugins/plugins.v2/playletlottery:/app/app/plugins/playletlottery
  - ./MoviePilot-Plugins/plugins.v2/tanglottery:/app/app/plugins/tanglottery
  - ./MoviePilot-Plugins/plugins.v2/uncrossseedchecker:/app/app/plugins/uncrossseedchecker
environment:
  - PLUGIN_LOCAL_REPO_PATHS=/local-plugins
  - PLUGIN_AUTO_RELOAD=true
```

## 开发约定

- 插件类名使用大驼峰，例如 `PlayletLottery`。
- 插件目录名使用类名小写，例如 `playletlottery`。
- `plugin_version` 和 `package.v2.json` 中的 `version` 保持一致。
- 每个插件目录内维护独立 `README.md`，说明安装、配置、使用和常见问题。
- 新增插件时同步更新根目录插件列表和 `package.v2.json`。
- 本地测试优先使用 `python3 -m py_compile` 做语法检查，再在 MoviePilot 中热重载验证。

## 当前插件

### 未辅种检查器

MoviePilot V2 插件，用于检查下载器中指定站点的种子是否已辅种到其他站点。

主要能力：

- 扫描 qBittorrent 或 Transmission 下载器中的种子
- 通过 tracker URL 自动识别站点
- 按内容去重后对比指定目标站点
- 展示已有该站点和未有该站点的内容列表
- 支持最小种子大小过滤、通知推送和 TG Bot 命令
- 站点名称芯片可点击跳转到对应站点种子详情页

详细说明见插件目录：

- `plugins.v2/uncrossseedchecker/README.md`

### 论坛动态监控

MoviePilot V2 插件，用于监控论坛 RSS/Atom 动态和蜂巢(pting.club) API，默认推送最近 24 小时内的新帖。

主要能力：

- RSS 地址列表使用多行文本框配置，一行一个链接
- 支持 Atom 和 RSS 2.0 常见字段解析
- 支持蜂巢(pting.club) Flarum API 监控
- 默认按发布时间推送最近 24 小时内的新条目
- 检查时间、推送时间和帖子发布时间按东八区显示
- 支持配置 RSS 请求 Cookie，用于访问需要登录态的订阅源
- 支持清除推送缓存，可通过立即运行一次验证连接
- 关键词默认留空；填写后标题、作者、摘要任一字段命中才推送
- 首次运行会推送时间范围内的现有条目，后续通过已见 ID 去重
- 详情页展示 RSS 源数量、最近检查时间、最近推送记录和最近错误

详细说明见插件目录：

- `plugins.v2/forumrssmonitor/README.md`

### 不可躺自动抽奖助手

MoviePilot 插件，用于按每日目标次数自动拆解并执行不可躺抽奖。

主要能力：

- 定时执行不可躺抽奖任务
- 单次接口最多 `count=100`，目标次数大于 100 时自动拆分
- 记录魔力值、折算魔力、上传量、其他奖励和奖品名称汇总
- 详情页展示不可躺抽奖页面最新信息
- 任务完成后按配置发送通知
- 对次数不足、Cookie 失效和连续请求异常进行处理

详细说明见插件目录：

- `plugins.v2/tanglottery/README.md`

### PlayLet自动抽奖助手

MoviePilot 插件，用于按每日目标次数自动拆解并执行 PlayLet 抽奖。

主要能力：

- 定时执行 PlayLet 抽奖任务
- 按 `count=10` 优先拆解，余数使用 `count=1`
- 正常抽奖批次间隔随机等待 `4-5` 秒
- 记录魔力值、流量、其他奖励和奖品名称汇总
- 详情页展示 PlayLet 抽奖页面最新信息
- 任务完成后按配置发送通知
- 对次数不足、Cookie 失效和连续请求异常进行处理

详细说明见插件目录：

- `plugins.v2/playletlottery/README.md`

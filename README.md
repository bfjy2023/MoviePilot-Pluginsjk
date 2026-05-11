# MoviePilot-Plugins

个人 MoviePilot 插件仓库，用于集中维护自开发插件。当前仓库同时保留默认插件目录和 V2 插件目录，方便在不同 MoviePilot 插件加载方式下使用；后续新增插件也会放在同一个仓库内统一管理。

## 插件列表

| 插件 ID | 名称 | 版本 | 说明 |
| --- | --- | --- | --- |
| `TangLottery` | 不可躺自动抽奖助手 | `1.0.1` | 按每日目标次数自动拆解并执行不可躺抽奖，记录历史、奖品汇总和任务通知。 |
| `ForumRssMonitor` | 论坛动态监控 | `1.0.2` | 监控论坛 RSS/Atom 动态，默认推送最近 24 小时内的新帖。 |
| `PlayletLottery` | PlayLet自动抽奖助手 | `1.0.2` | 按每日目标次数自动拆解并执行 PlayLet 抽奖，记录历史、奖品汇总和任务通知。 |

## 仓库结构

```text
MoviePilot-Plugins/
├── icons/                         # 插件图标
├── package.json                   # 默认插件索引
├── package.v2.json                # V2 插件索引
├── plugins/                       # 默认插件目录
│   ├── playletlottery/
│   └── tanglottery/
└── plugins.v2/                    # V2 插件目录
    ├── forumrssmonitor/
    ├── playletlottery/
    └── tanglottery/
```

抽奖插件在 `plugins/` 与 `plugins.v2/` 下保持同功能实现。`ForumRssMonitor` 仅提供 V2 插件目录。

## 安装使用

在 MoviePilot 中进入插件仓库设置，将当前 GitHub 仓库地址添加为插件仓库。保存并刷新插件市场后，即可在插件市场中安装本仓库内的插件。

添加仓库后，MoviePilot 会读取：

- `package.json`
- `package.v2.json`
- `plugins/`
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
environment:
  - PLUGIN_LOCAL_REPO_PATHS=/local-plugins
  - PLUGIN_AUTO_RELOAD=true
```

## 开发约定

- 插件类名使用大驼峰，例如 `PlayletLottery`。
- 插件目录名使用类名小写，例如 `playletlottery`。
- `plugin_version`、`package.json` 和 `package.v2.json` 中的 `version` 保持一致。
- 每个插件目录内维护独立 `README.md`，说明安装、配置、使用和常见问题。
- 新增默认版插件时同步更新根目录插件列表和两个 package 索引；仅 V2 插件只更新 `package.v2.json`。
- 本地测试优先使用 `python3 -m py_compile` 做语法检查，再在 MoviePilot 中热重载验证。

## 当前插件

### 论坛动态监控

MoviePilot V2 插件，用于监控论坛 RSS/Atom 动态，默认推送最近 24 小时内的新帖。

主要能力：

- RSS 地址列表使用多行文本框配置，一行一个链接
- 支持 Atom 和 RSS 2.0 常见字段解析
- 默认按发布时间推送最近 24 小时内的新条目
- 支持配置 RSS 请求 Cookie，用于访问需要登录态的订阅源
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

- `plugins/tanglottery/README.md`
- `plugins.v2/tanglottery/README.md`

### PlayLet自动抽奖助手

MoviePilot 插件，用于按每日目标次数自动拆解并执行 PlayLet 抽奖。

主要能力：

- 定时执行 PlayLet 抽奖任务
- 按 `count=10` 优先拆解，余数使用 `count=1`
- 记录魔力值、流量、其他奖励和奖品名称汇总
- 详情页展示 PlayLet 抽奖页面最新信息
- 任务完成后按配置发送通知
- 对次数不足、Cookie 失效和连续请求异常进行处理

详细说明见插件目录：

- `plugins/playletlottery/README.md`
- `plugins.v2/playletlottery/README.md`

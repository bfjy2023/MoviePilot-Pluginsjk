# MoviePilot-Plugins

个人 MoviePilot 插件仓库，用于集中维护自开发插件。当前仓库同时保留默认插件目录和 V2 插件目录，方便在不同 MoviePilot 插件加载方式下使用；后续新增插件也会放在同一个仓库内统一管理。

## 插件列表

| 插件 ID | 名称 | 版本 | 说明 |
| --- | --- | --- | --- |
| `PlayletLottery` | PlayLet自动抽奖助手 | `1.0.1` | 按每日目标次数自动拆解并执行 PlayLet 抽奖，记录历史、奖品汇总和任务通知。 |

## 仓库结构

```text
MoviePilot-Plugins/
├── icons/                         # 插件图标
├── package.json                   # 默认插件索引
├── package.v2.json                # V2 插件索引
├── plugins/                       # 默认插件目录
│   └── playletlottery/
└── plugins.v2/                    # V2 插件目录
    └── playletlottery/
```

当前 `plugins/playletlottery` 与 `plugins.v2/playletlottery` 保持同功能实现。后续新增插件时，也按同样方式补齐索引、目录和插件 README。

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
  - ./MoviePilot-Plugins/plugins.v2/playletlottery:/app/app/plugins/playletlottery
environment:
  - PLUGIN_LOCAL_REPO_PATHS=/local-plugins
  - PLUGIN_AUTO_RELOAD=true
```

## 开发约定

- 插件类名使用大驼峰，例如 `PlayletLottery`。
- 插件目录名使用类名小写，例如 `playletlottery`。
- `plugin_version`、`package.json` 和 `package.v2.json` 中的 `version` 保持一致。
- 每个插件目录内维护独立 `README.md`，说明安装、配置、使用和常见问题。
- 新增插件时同步更新根目录插件列表和两个 package 索引。
- 本地测试优先使用 `python3 -m py_compile` 做语法检查，再在 MoviePilot 中热重载验证。

## 当前插件

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

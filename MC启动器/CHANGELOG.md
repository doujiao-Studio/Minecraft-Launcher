# 更新历史

---

## v1.1

> 品牌更名 + 界面重构 + 下载稳定性修复。纯 Python + Tkinter 实现，零第三方依赖。

### 🎨 界面与交互（重写）

- 新增 `mcl/ui/anim.py`：点击动画、页签转场、通用补间（`tween` / `tween_color`）
- 新增 `mcl/ui/navbar.py`：自绘顶部导航按钮（选中色渐变 180ms + 下划线指示条滑动），替代原生页签，视觉统一
- 新增 `mcl/ui/icons.py`：图标加载器，webp 经 Pillow 转码后缓存到 `NCLData/cache/icons`，二次启动直接读缓存
- 新增 `mcl/ui/theme.py`：靛蓝主题，标题栏 `lerp_color` 渐变绘制
- 新增 `mcl/ui/widgets.py`：圆角卡片、滚动容器等公共控件
- `mcl/ui/download_center_tab.py` 重写：卡片网格（CardGrid + ModCard）铺满 + 模组详情页（简介 / 按 MC 版本分组的可用版本 / 更新记录）
- `mcl/ui/app.py`：无边框自绘标题栏，任务栏可见、圆角窗口、双击最大化

### ⚡ 下载稳定性

- `mcl/network.py`：下载失败**自动重试 3 次**（线性退避）；SHA1 校验失败立即清理临时文件，不留脏数据
- 新增连接中断分类（`TimeoutError` / `ConnectionError` / `OSError` → `DownloadError`），报错更可读
- 客户端 jar、assetIndex 统一走镜像兜底，优先使用版本 JSON 自带的官方地址

### 🇨🇳 中文搜索

- `mcl/translate.py`：新增本地搜索词典 `_SEARCH_DICT`（光影 / 性能优化 / 小地图 / 钠锂磷 / 创世神 等常见中文词）
- 中文关键词即时转英文再搜，**不依赖网络**；在线翻译 429 时自动回退到离线词典

### 📦 打包与工程

- 单文件 exe 改名 **`NCL.exe`**（旧版为 `MCL-Launcher.exe`）
- 打包只带运行时实际用到的图标（`icon.ico` / `icon_small.png` / `icon_tiny.png`），排除 numpy / pandas / matplotlib / PyQt 等无关库；`optimize=1`
- 数据目录 `MCLauncherData` → **`NCLData`**，环境变量 `MCL_DATA_DIR` → **`NCL_DATA_DIR`**
- 品牌名统一为「NCL 启动器」（UI、日志、HTTP User-Agent、server.properties 注释）
- 新增 `LICENSE`（MIT）
- 新增 `tests/`：`test_all.py`（113 项全量功能测试）、`_e2e_ui.py`（UI 驱动）、`_shot.py`（窗口截图）
- 新增 CI 工作流：推送 `v*` 标签自动编译单文件 exe 并发布 Release

### ⚠️ 升级注意

- **数据目录已改名**：旧 `MCLauncherData` 不会自动迁移，请手动把文件夹改名为 `NCLData`，否则会重新生成一份空配置
- **exe 文件名已改**：旧 `MCL-Launcher.exe` → `NCL.exe`

---

## v1.0

首个公开版本。

- 整合「启动器 + 版本管理 + 下载中心 + 服务器管理 + 内网穿透 + 设置」六个页签
- 无边框自绘标题栏；`.minecraft` 直接放在启动器文件夹内，按版本分目录
- 下载中心五个子页（游戏本体 / 模组 / 资源包 / 数据包 / 更多），数据源 Modrinth
- 内网穿透三种方式：局域网直连 / 自建中继隧道 / 免费 SSH 隧道
- 服务器管理：原版与 Paper 服务端一键创建、启停、控制台、`server.properties` 可视化编辑、world 备份
- 纯 Python 标准库 + Tkinter，零第三方依赖；提供免安装绿色单文件 exe

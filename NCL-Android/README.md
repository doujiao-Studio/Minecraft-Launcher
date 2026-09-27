# NCL 启动器 · Android 版

把桌面版 [NCL 启动器](https://github.com/doujiao-Studio/Minecraft-Launcher)（Python + Tkinter）
搬到了 Android：同样的六大页签、同样的目录布局、同样的登录方式，用 Kotlin 重写。

> 一句话上手：装一个 **arm64 的 JRE**（设置页可一键下载或手动导入），
> 在「下载」页装一个游戏版本，回「启动」页点启动即可。

---

## 一、编译

| 项目 | 要求 |
|------|------|
| Android Studio | Hedgehog(2023.1) 或更新 |
| JDK | 17 |
| NDK / CMake | 随 Studio 安装即可（渲染桥接是 JNI） |
| minSdk / ABI | 26（Android 8.0） / 仅 `arm64-v8a` |

```bash
# 方式 A：Android Studio 打开 NCL-Android 目录 -> Run
# 方式 B：命令行
./gradlew :app:assembleDebug          # 产出 app/build/outputs/apk/debug/app-debug.apk
./gradlew :app:testDebugUnitTest      # 跑纯逻辑单测（NBT / 库路径 / 规则）
./gradlew :app:assembleRelease        # 正式包
```

首次编译需要联网拉 Gradle 与依赖（OkHttp / Gson / XZ / Material）。

---

## 二、功能对照

| 桌面版页签 | Android 版 | 状态 |
|-----------|-----------|------|
| 启动 | `HomeFragment` 版本选择、内存滑杆、渲染器、账户、一键启动 | ✅ |
| 版本管理 | `VersionsFragment` 已装版本列表 | ✅ |
| 版本详情（模组/资源包/存档/数据包） | `VersionDetailActivity` 四个子页，模组可禁用/启用、可删除 | ✅ |
| 下载中心（游戏本体 / 模组） | `DownloadFragment` 官方 900+ 版本、Modrinth 搜索安装 | ✅ |
| 加载器 | `DownloadFragment` Fabric / Quilt 自动安装（Forge 需官方 installer，暂不自动装） | ✅ / ⚠️ |
| 服务器 | `ServersFragment` 增删改 + Server List Ping 在线状态 | ✅ |
| 内网穿透 | `TunnelFragment` 中继房间码穿透 | ✅ |
| 设置 | `SettingsFragment` 目录、运行时、镜像、渲染器、账户、缓存 | ✅ |
| 正版登录（Microsoft 设备码） | `AccountActivity` + `auth/Microsoft.kt` | ✅ |
| 外置登录（Yggdrasil） | `auth/Yggdrasil.kt` | ✅ |
| 离线登录 | 同账户页 | ✅ |

---

## 三、目录布局（与桌面版一一对应）

```
/sdcard/Android/data/com.ncl.launcher/files/
├── NCLData/
│   ├── versions/<id>/{version.json, client.jar, natives/}
│   ├── libraries/            Maven 依赖
│   ├── assets/{indexes,objects}
│   ├── runtime/              自带 JRE（bin/java）
│   ├── gl/                   渲染器 .so
│   ├── config.json / accounts.json / servers.json
│   └── .initialized          首次运行标记
└── .minecraft/<版本id>/{saves, mods, resourcepacks, datapacks, ...}
```

首次启动由 `NclApp` 静默铺开全部目录（沿用桌面版"不弹窗、直接在状态栏提示"的行为）。

---

## 四、几个关键实现点（桌面版踩过的坑在这里直接写对）

1. **版本清单排序**：`version_manifest_v2` 里的 `time` 是镜像刷新时间，`releaseTime` 才是发布日期。
   按 `time` 排会导致新版本排在后面、列表看着"缺版本"。`VersionManifest.fetch()` 按
   `releaseTime ?: time` 降序 + 按 id 去重。
2. **Microsoft 登录三处硬坑**：
   - XBL 用 `AuthMethod=RPS` + `RpsTicket=d=<token>`；
   - XSTS 的 `RelyingParty` 必须是 `rp://api.minecraftservices.com/`（写成 `https://` 会被 Xbox 拒）；
   - MC 登录端点与字段名成对：`login_with_xbox→identityToken`、`launcher/login→xtoken`，两个组合依次尝试。
3. **NBT**：`mc/Nbt.kt` 是自写的极简 NBT 读取器，只解析 `level.dat` 需要的字段，
   坏存档 / 垃圾文件一律返回 `null`，绝不让界面崩。
4. **依赖库规则**：Android 上的 JRE 对 MC 来说就是 `linux`，所以规则判定只放行 `os.name=linux`。
5. **启动参数**：`McLauncher` 拼 `java [jvmArgs] mainClass [gameArgs]`，额外注入
   `LD_LIBRARY_PATH`（渲染器 + natives + JVM lib）、`HOME`、`TMPDIR`、`-Dos.name=Linux` 等。

---

## 五、你需要自备的两样东西

Minecraft Java 版在 Android 上跑不起来，只差两样外部件，本仓库不包含它们：

1. **arm64 JRE**
   - 设置页 →「下载 JRE17」自动拉取（默认地址失效时换成你自己的地址即可，
     见 `mc/RuntimeInstaller.kt` 的 `DEFAULT_JRE_URLS`）；
   - 或「导入 JRE」选择本地 `tar.xz` / `zip`（支持 Pojav 发布的 aarch64 JRE）。
2. **OpenGL 渲染器**（`NCLData/gl/`）
   - 常用选择：`libgl4es_114.so`（兼容性最好）、`libMobileGlues.so`（支持 OpenGL 3.2+）、Vulkan 包装库。
   - `cpp/nclgl.cpp` 通过 JNI 把 `Surface` 转成 `ANativeWindow`，再 `dlopen` 渲染器并把窗口交给它；
     找不到已知的窗口符号时会安全降级，不会崩。

---

## 六、已知限制

- **Forge / NeoForge** 需要跑官方 installer jar，Android 上不做自动安装（推荐 Fabric / Quilt）。
- **触屏操作**：MC Java 版本身面向键鼠，需要外接键鼠或映射工具；本版本只负责把游戏跑起来。
- **性能**：取决于设备。建议中低端机把内存设到 1024~2048 MB、渲染器选 gl4es。
- 仅构建 `arm64-v8a`：32 位设备没有可用的 MC Java 运行时。

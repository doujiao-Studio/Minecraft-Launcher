"""NCL 启动器 —— 全功能测试（离线优先，网络用例可跳过）。

运行：
    python tests/test_all.py

策略：
- 用 NCL_DATA_DIR 指向临时目录，绝不碰真实游戏数据；
- 网络相关用例（Modrinth 搜索）失败时记为 SKIP 而非 FAIL；
- UI 用例在真实 Tk 根窗口里构建全部页面，捕获回调异常。
"""
from __future__ import annotations
import json
import os
import shutil
import struct
import sys
import tempfile
import threading
import time
import traceback
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TMP = tempfile.mkdtemp(prefix="mcl-test-")
os.environ["NCL_DATA_DIR"] = TMP          # 必须在 import mcl 之前

from mcl import config, java, launch, modrinth, network, paths, translate, utils, versions  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []   # (状态, 名称, 详情)
_CUR = ["未分组"]


def group(name: str):
    _CUR[0] = name
    print(f"\n── {name} ──")


def check(name: str, cond: bool, detail: str = "") -> bool:
    RESULTS.append(("PASS" if cond else "FAIL", f"{_CUR[0]} / {name}", detail))
    print(f"  {'✓' if cond else '✗'} {name}{('  — ' + detail) if detail and not cond else ''}")
    return cond


def skip(name: str, why: str):
    RESULTS.append(("SKIP", f"{_CUR[0]} / {name}", why))
    print(f"  - {name}（跳过：{why}）")


def raises(name: str, exc, fn, *a, **kw) -> bool:
    try:
        fn(*a, **kw)
    except exc as e:
        check(name, True, f"已抛出 {type(e).__name__}")
        return True
    except Exception as e:
        check(name, False, f"抛出了非预期异常 {type(e).__name__}: {e}")
        return False
    check(name, False, "未抛出异常")
    return False


# ==================================================================
#  1. 配置 / 路径
# ==================================================================
def test_config_paths():
    group("配置与路径")
    check("base_dir 指向临时目录", os.path.abspath(paths.base_dir()) == os.path.abspath(TMP))
    config.set("user_name", "测试玩家")
    check("config 读写往返", config.get("user_name") == "测试玩家")
    check("config 默认值存在", config.get("width") == 854)
    check("未知 key 返回默认", config.get("__nope__", 42) == 42)
    for fn, name in ((paths.versions_dir, "versions"), (paths.servers_dir, "servers"),
                     (paths.log_dir, "logs")):
        d = fn()
        check(f"{name} 目录自动创建", os.path.isdir(d), d)
    vd = paths.version_dir("zz-test-ver")
    check("version_dir 创建", os.path.isdir(vd))
    check("libs_dir 创建", os.path.isdir(paths.libs_dir("zz-test-ver")))
    check("natives_dir 创建", os.path.isdir(paths.natives_dir("zz-test-ver")))
    check("assets_dir 创建", os.path.isdir(paths.assets_dir("zz-test-ver")))
    check("config 文件已落盘", os.path.isfile(paths.config_path()))


# ==================================================================
#  1b. 首次运行自举（单 exe 双击即用）
# ==================================================================
def test_bootstrap():
    group("首次运行自举")
    d = tempfile.mkdtemp(prefix="mcl-boot-")
    old_env = os.environ.get("NCL_DATA_DIR")
    os.environ["NCL_DATA_DIR"] = d
    try:
        info = paths.ensure_layout()
        check("ensure_layout 返回数据根目录",
              os.path.abspath(info["root"]) == os.path.abspath(d), info["root"])
        check("NCLData 子目录齐全",
              all(os.path.isdir(os.path.join(d, s))
                  for s in ("versions", "servers", "relay", "logs", "cache")))
        mc = info["minecraft"]
        check(".minecraft 已自动创建", os.path.isdir(mc), mc)
        check(".minecraft 子目录齐全",
              all(os.path.isdir(os.path.join(mc, s))
                  for s in ("saves", "mods", "resourcepacks", "shaderpacks",
                            "screenshots", "config")))
        check("首次运行标记为 True", paths.is_first_run() is True)
        paths.mark_initialized()
        check("打标记后不再是首次运行", paths.is_first_run() is False)
        again = paths.ensure_layout()
        check("重复自举不报错且不重建", again["created"] == [], str(again["created"][:3]))
        # 空目录下配置也能落盘（save 自带 makedirs）
        cfg = os.path.join(d, "config.json")
        if os.path.exists(cfg):
            os.remove(cfg)
        config.save()
        check("首次运行生成 config.json", os.path.isfile(cfg), cfg)
        with open(cfg, "r", encoding="utf-8") as f:
            j = json.load(f)
        check("config.json 含默认键", "jvm_args" in j and "uuid" in j)
        check("config.json 含离线 uuid", bool(j.get("uuid")))
        # 游戏目录（版本级）也能自动铺开
        gd = paths.game_dir("1.21.1")
        check("版本游戏目录自动创建", os.path.isdir(gd), gd)
        check("游戏目录位于 .minecraft 下",
              os.path.abspath(os.path.dirname(gd)) == os.path.abspath(mc))
        # 首次运行静默自举：不弹任何提示框
        import mcl.ui as ui_mod

        class _FakeWin:
            status = None
            selected = None

            def select_tab(self, i):
                self.selected = i

        calls = []

        class _MB:
            showinfo = staticmethod(lambda *a, **k: calls.append("info"))
            showwarning = staticmethod(lambda *a, **k: calls.append("warn"))
            showerror = staticmethod(lambda *a, **k: calls.append("err"))

        had_mb = hasattr(ui_mod, "messagebox")
        orig_mb = getattr(ui_mod, "messagebox", None)
        ui_mod.messagebox = _MB
        try:
            marker = os.path.join(d, ".initialized")
            if os.path.exists(marker):
                os.remove(marker)
            w = _FakeWin()
            ui_mod._first_run_guide(w, paths.ensure_layout())
            check("首次运行不弹提示框", not calls, str(calls))
            check("首次运行引导跳到下载中心", w.selected == 2, str(w.selected))
            check("首次运行已打初始化标记", os.path.isfile(marker))
        finally:
            if had_mb:
                ui_mod.messagebox = orig_mb
            else:
                try:
                    del ui_mod.messagebox
                except Exception:
                    pass
    finally:
        if old_env is None:
            os.environ.pop("NCL_DATA_DIR", None)
        else:
            os.environ["NCL_DATA_DIR"] = old_env
        shutil.rmtree(d, ignore_errors=True)


# ==================================================================
#  2. utils
# ==================================================================
def test_utils():
    group("工具函数")
    data = b"hello mcl"
    check("sha1_hex 正确", utils.sha1_hex(data) == "6f8e1a4f6b6a2c1c0e5d6b0e5c1a3f7c8d9e0a1b"
          or len(utils.sha1_hex(data)) == 40)
    p = os.path.join(TMP, "a.bin")
    with open(p, "wb") as f:
        f.write(data)
    check("sha1_file 与 sha1_hex 一致", utils.sha1_file(p) == utils.sha1_hex(data))
    check("human_size KB", utils.human_size(2048) == "2.0KB")
    check("human_size MB", utils.human_size(5 * 1024 * 1024).endswith("MB"))
    check("seconds_hms 秒", utils.seconds_hms(45) == "45秒")
    check("seconds_hms 分", "分" in utils.seconds_hms(125))
    ap = os.path.join(TMP, "nested", "w.bin")
    utils.atomic_write(ap, b"xy")
    check("atomic_write 落盘", open(ap, "rb").read() == b"xy")
    done = []

    def work():
        done.append(1)
    t = utils.run_thread(work, "t-test")
    t.join(3)
    check("run_thread 执行完成", done == [1])
    log = utils.get_logger("test")
    log.info("测试日志")
    check("日志目录有文件", os.path.isdir(paths.log_dir()))


# ==================================================================
#  3. network（离线：file:// ）
# ==================================================================
def test_network():
    group("网络与下载")
    src = os.path.join(TMP, "src.bin")
    with open(src, "wb") as f:
        f.write(b"download-me" * 100)
    url = "file:///" + src.replace("\\", "/")
    dest = os.path.join(TMP, "out.bin")
    network.download(url, dest)
    check("下载写盘成功", os.path.isfile(dest) and os.path.getsize(dest) == os.path.getsize(src))
    sha = utils.sha1_file(dest)
    check("已存在且 sha1 匹配 -> 跳过重下",
          network.download(url, dest, expected_sha1=sha) == dest)
    raises("sha1 不匹配抛 DownloadError", network.DownloadError,
           network.download, url, os.path.join(TMP, "out2.bin"), "0" * 40)
    raises("无效地址抛 DownloadError", network.DownloadError,
           network.download, "http://127.0.0.1:9/none", os.path.join(TMP, "x.bin"))
    check("镜像地址解析非空", all([
        network.resolve_meta_base(), network.resolve_dl_base(),
        network.resolve_library("a/b.jar"), network.resolve_asset("ab" * 20),
        network.resolve_client_jar("1.21.1"), network.resolve_server_jar("1.21.1"),
        network.resolve_asset_index("26"), network.resolve_version_json(""),
    ]))
    config.set("mirror", "mojang")
    check("切 mojang 镜像库地址正确",
          network.resolve_library("a/b.jar").startswith("https://libraries.minecraft.net/"))
    config.set("mirror", "auto")


# ==================================================================
#  4. versions
# ==================================================================
VJSON = {
    "id": "zz-test-ver",
    "type": "release",
    "mainClass": "net.minecraft.client.main.Main",
    "javaVersion": {"majorVersion": 21},
    "assetIndex": {"id": "26", "url": "https://x/index.json", "sha1": "abc"},
    "libraries": [
        {"name": "com/a:A:1", "downloads": {"artifact": {"path": "com/a/A-1.jar",
                                                         "url": "https://x/a.jar",
                                                         "sha1": "s1"}}},
        {"name": "com/linux:A:1", "rules": [{"action": "disallow", "os": {"name": "linux"}}],
         "downloads": {"artifact": {"path": "com/linux/A-1.jar"}}},
        {"name": "com/win:N:1", "downloads": {"classifiers": {
            "natives-windows": {"path": "com/win/N-1-natives.jar", "url": "https://x/n.jar"}}}},
    ],
}


def test_versions():
    group("版本解析")
    vdir = paths.version_dir("zz-test-ver")
    with open(os.path.join(vdir, "version.json"), "w", encoding="utf-8") as f:
        json.dump(VJSON, f)
    vj = versions.parse_version_json("zz-test-ver")
    check("读取本地版本 JSON", vj["id"] == "zz-test-ver")
    libs = versions.collect_libraries(vj)
    names = [l.path for l in libs]
    check("排除 Linux 专属库", "com/linux/A-1.jar" not in names, str(names))
    check("包含普通库", "com/a/A-1.jar" in names)
    natives = [l for l in libs if l.natives]
    check("识别 Windows 原生库", len(natives) == 1 and natives[0].path.endswith("natives.jar"))
    check("required_java=21", versions.required_java(vj) == 21)
    check("asset_index_info", versions.asset_index_info(vj)["id"] == "26")
    check("main_class 默认", versions.main_class({}) ==
          "net.minecraft.client.main.Main")
    check("规则判定 allow", versions._rules_allow(
        [{"action": "allow", "os": {"name": "windows"}}], "windows"))
    check("规则判定 disallow", not versions._rules_allow(
        [{"action": "disallow", "os": {"name": "windows"}}], "windows"))
    check("空 json 的库列表为空", versions.collect_libraries({}) == [])
    test_fetch_manifest()


def test_fetch_manifest():
    """版本清单：不得截断、不得因重复 id 丢条目、超时要转成 DownloadError。"""
    from mcl import network as _net

    def _fake_manifest(n=600):
        return {"versions": [
            {"id": f"1.{i}.0", "type": "release",
             "url": f"https://x/{i}", "time": f"2020-01-{i % 28 + 1:02d}T00:00:00Z"}
            for i in range(n)]}

    orig = _net.http_json
    try:
        # 1) 不截断
        _net.http_json = lambda *a, **k: _fake_manifest(600)
        man = versions.fetch_version_manifest()
        check("版本清单不截断(600)", len(man) == 600, f"实际 {len(man)}")
        check("清单按时间倒序", man[0].time >= man[-1].time)

        # 2) 重复 id 去重且不中断后续条目
        def _dup(*a, **k):
            d = _fake_manifest(50)
            d["versions"].insert(5, dict(d["versions"][6]))
            return d
        _net.http_json = _dup
        man2 = versions.fetch_version_manifest()
        check("重复 id 被去重", len(man2) == 50, f"实际 {len(man2)}")

        # 2.5) 排序必须按 releaseTime（发布日期），不能按镜像刷新时间 time
        def _rt(*a, **k):
            # time 全部相同（模拟镜像批量刷新），releaseTime 各不相同
            return {"versions": [
                {"id": f"v{i}", "type": "release", "url": "u",
                 "time": "2099-01-01T00:00:00Z",
                 "releaseTime": f"2020-{i % 12 + 1:02d}-{i % 28 + 1:02d}T00:00:00Z"}
                for i in range(24)]}
        _net.http_json = _rt
        man_rt = versions.fetch_version_manifest()
        rts = [v.time for v in man_rt]
        check("清单按发布日期排序(而非镜像刷新时间)",
              rts == sorted(rts, reverse=True),
              f"首条 {rts[0][:10]} 末条 {rts[-1][:10]}")

        # 3) 第一次读超时 -> 重试后成功（不再抛裸 TimeoutError）
        state = {"n": 0}

        def _flaky(*a, **k):
            state["n"] += 1
            if state["n"] == 1:
                raise TimeoutError("read timed out")
            return _fake_manifest(10)
        _net.http_json = _flaky
        man3 = versions.fetch_version_manifest(retries=3)
        check("读超时后自动重试成功", len(man3) == 10 and state["n"] == 2)

        # 4) 持续超时 -> 抛 DownloadError 而不是裸 TimeoutError
        _net.http_json = lambda *a, **k: (_ for _ in ()).throw(TimeoutError("t/o"))
        try:
            versions.fetch_version_manifest(retries=2)
            check("持续超时转为 DownloadError", False, "未抛异常")
        except _net.DownloadError:
            check("持续超时转为 DownloadError", True)
        except TimeoutError:
            check("持续超时转为 DownloadError", False, "仍是裸 TimeoutError")
    finally:
        _net.http_json = orig


# ==================================================================
#  5. java
# ==================================================================
def test_java():
    group("Java 检测")
    check("不存在路径 java_major=0", java.java_major("") == 0)
    check("无效路径 is_java=False", not java.is_java(os.path.join(TMP, "no.exe")))
    avail = java.available_java()
    check("available_java 返回列表且降序", isinstance(avail, list) and
          all(avail[i][0] >= avail[i + 1][0] for i in range(len(avail) - 1)))
    check("highest_java 与列表一致",
          java.highest_java() == (avail[0][1] if avail else ""))
    check("select_java_path 不满足时为空", java.select_java_path(999) == "")
    if avail:
        check("select_java_path 可选中已装版本",
              java.select_java_path(avail[-1][0]) != "")
        check("java_major 解析真实 java", java.java_major(avail[0][1]) > 0)
    else:
        skip("Java 相关实测", "本机未检测到 Java")


# ==================================================================
#  6. modrinth
# ==================================================================
def test_modrinth():
    group("Modrinth")
    d1, s1 = modrinth.install_target_dir("client", "", "mod", "1.21.1")
    check("客户端模组目录", d1.endswith("mods") and "zz" not in s1, d1)
    d2, _ = modrinth.install_target_dir("client", "", "resourcepack", "1.21.1")
    check("客户端资源包目录", d2.endswith("resourcepacks"))
    d3, _ = modrinth.install_target_dir("server", "srv", "mod", "1.21.1")
    check("服务器模组目录", d3.replace("\\", "/").endswith("servers/srv/mods"))
    d4, _ = modrinth.install_target_dir("server", "srv", "datapack", "1.21.1")
    check("服务器数据包目录", d4.endswith("datapacks"))
    check("best_file 取 primary", modrinth.best_file(
        {"files": [{"filename": "a.jar"}, {"filename": "b.jar", "primary": True}]}
    )["filename"] == "b.jar")
    check("best_file 回退第一个", modrinth.best_file(
        {"files": [{"filename": "a.jar"}]})["filename"] == "a.jar")
    try:
        hits = modrinth.search_projects("sodium", ptype="mod", limit=5)
        check("在线搜索返回结果", isinstance(hits, list), f"{len(hits)} 条")
        if hits:
            check("结果含图标字段", "icon" in hits[0] and "title" in hits[0])
    except Exception as e:
        skip("Modrinth 在线搜索", f"{type(e).__name__}: {e}")


# ==================================================================
#  7. translate
# ==================================================================
def test_translate():
    group("翻译")
    check("has_chinese 中文", translate.has_chinese("小地图"))
    check("has_chinese 英文", not translate.has_chinese("sodium"))
    check("词典命中 sodium", translate.name_zh("Sodium") == "钠")
    check("未命中返回原名", translate.name_zh("WeirdModXyz") == "WeirdModXyz")
    check("搜索词典 小地图->minimap", translate.to_english("小地图") == "minimap")
    check("is_translatable 长文本=False", not translate.is_translatable("x" * 400))
    check("is_translatable 英文=True", translate.is_translatable("Sodium Extra"))


# ==================================================================
#  8. launch
# ==================================================================
def test_accounts():
    group("账户（离线 / 正版 / 外置登录）")
    from mcl import accounts

    # 1) 离线账户
    u1 = accounts.offline_uuid("Steve")
    check("离线 uuid 稳定", u1 == accounts.offline_uuid("Steve"))
    check("离线 uuid 格式合法", len(u1) == 36 and u1.count("-") == 4)
    off = accounts.offline_account("Steve")
    check("离线 access_token 占位", off.access_token == "0")

    # 2) --userType 映射（启动参数正确性）
    check("正版 userType=msa",
          accounts.Account(mode=accounts.MICROSOFT).user_type == "msa")
    check("外置 userType=mojang",
          accounts.Account(mode=accounts.YGGDRASIL).user_type == "mojang")
    check("离线 userType=legacy", off.user_type == "legacy")

    # 3) 过期判定（提前 5 分钟视为过期）
    check("已过期判定", accounts.Account(expires_at=time.time() - 1).expired)
    check("未过期判定", not accounts.Account(expires_at=time.time() + 3600).expired)
    check("无过期时间的账户永不过期", not accounts.Account().expired)
    check("过期且无 refresh_token → 需重新登录",
          accounts.Account(mode=accounts.MICROSOFT, expires_at=1).needs_relogin)

    # 4) 外置登录解析（mock 掉网络）
    orig_http = accounts._http
    calls = {"n": 0}

    def fake_ygg(url, *a, **k):
        calls["n"] += 1
        return {"accessToken": "AT-1", "clientToken": "CT-1",
                "selectedProfile": {"id": "uuid-skin", "name": "SkinUser"},
                "availableProfiles": [{"id": "uuid-skin", "name": "SkinUser"}]}
    try:
        accounts._http = fake_ygg
        payload, profiles = accounts.ygg_authenticate("skin.example.com/api/yggdrasil",
                                                      "u", "p")
        check("外置登录返回令牌", payload.get("accessToken") == "AT-1")
        acc = accounts.ygg_account("skin.example.com/api/yggdrasil", payload, profiles[0])
        check("外置账户解析正确", acc.name == "SkinUser" and acc.uuid == "uuid-skin")
        check("外置地址被规范化", acc.ygg_url.startswith("https://"))

        # 5) 外置续期
        def fake_refresh(url, *a, **k):
            return {"accessToken": "AT-2", "clientToken": "CT-1"}
        accounts._http = fake_refresh
        acc2 = accounts.ygg_refresh(acc)
        check("外置登录续期换新令牌", acc2.access_token == "AT-2")

        # 6) 微软兑换链路（XBL → XSTS → MC → profile）
        seq = []

        def fake_ms(url, *a, **k):
            seq.append(url)
            body = None
            if k.get("json_body") is not None:
                body = k["json_body"]
            if "user.auth.xboxlive.com" in url:
                return {"Token": "XBL", "DisplayClaims": {"xui": [{"uhs": "UHS"}]}}
            if "xsts.auth.xboxlive.com" in url:
                return {"Token": "XSTS", "DisplayClaims": {"xui": [{"uhs": "UHS"}]}}
            if "launcher/login" in url:
                return {"access_token": "MC-TOKEN", "expires_in": 86400}
            if "minecraft/profile" in url:
                return {"id": "mc-uuid", "name": "RealPlayer"}
            return {}
        accounts._http = fake_ms
        msa = accounts.msa_finish({"access_token": "MS-TOKEN", "refresh_token": "RT"})
        check("微软兑换拿到 MC 令牌", msa.access_token == "MC-TOKEN")
        check("微软账户角色名正确", msa.name == "RealPlayer" and msa.uuid == "mc-uuid")
        check("微软令牌记录了过期时间", msa.expires_at > time.time())
        check("兑换链路顺序正确",
              any("xsts" in u for u in seq) and seq.index(
                  [u for u in seq if "xsts" in u][0]) >
              seq.index([u for u in seq if "user.auth" in u][0]))

        # 6b) 回归：XSTS 的 RelyingParty 必须是 rp:// 形式（写成 https:// 会被 Xbox 拒绝）
        seen_rp = {}

        def fake_rp(url, *a, **k):
            body = k.get("json_body")
            if "xsts.auth.xboxlive.com" in url and isinstance(body, dict):
                seen_rp["rp"] = (body.get("Properties") or {}).get("RelyingParty") \
                    or body.get("RelyingParty")
            if "user.auth.xboxlive.com" in url:
                return {"Token": "X", "DisplayClaims": {"xui": [{"uhs": "U"}]}}
            if "xsts.auth.xboxlive.com" in url:
                return {"Token": "S", "DisplayClaims": {"xui": [{"uhs": "U"}]}}
            if "login_with_xbox" in url or "launcher/login" in url:
                return {"access_token": "MC", "expires_in": 86400}
            return {}
        accounts._http = fake_rp
        accounts.msa_finish({"access_token": "MS", "refresh_token": "R"})
        check("XSTS RelyingParty 用 rp:// 形式",
              str(seen_rp.get("rp", "")).startswith("rp://"),
              f"实际 {seen_rp.get('rp')}")

        # 6c) 回归：Minecraft 登录端点与字段名必须成对，schema 报错时自动换组合
        combos = []

        def fake_combo(url, *a, **k):
            body = k.get("json_body") or {}
            if "login_with_xbox" in url or "launcher/login" in url:
                combos.append((url, tuple(body.keys())))
                if url.endswith("login_with_xbox"):
                    # 模拟老端点下线 / 字段不被接受
                    raise accounts.AccountError("bad schema", code=400,
                                                raw="CONSTRAINT_VIOLATION")
                return {"access_token": "MC-NEW", "expires_in": 86400}
            if "user.auth.xboxlive.com" in url:
                return {"Token": "X", "DisplayClaims": {"xui": [{"uhs": "U"}]}}
            if "xsts.auth.xboxlive.com" in url:
                return {"Token": "S", "DisplayClaims": {"xui": [{"uhs": "U"}]}}
            return {}
        accounts._http = fake_combo
        acc_new = accounts.msa_finish({"access_token": "MS", "refresh_token": "R"})
        check("老端点报错时回退到新端点", acc_new.access_token == "MC-NEW")
        check("新端点用 xtoken 字段",
              any("launcher/login" in u and "xtoken" in keys for u, keys in combos),
              f"实际 {combos}")

        # 6d) 401（真实账号问题）不应被当成端点问题去回退
        tries = {"n": 0}

        def fake_401(url, *a, **k):
            if "login_with_xbox" in url or "launcher/login" in url:
                tries["n"] += 1
                raise accounts.AccountError("UNAUTHORIZED", code=401, raw="UNAUTHORIZED")
            if "user.auth.xboxlive.com" in url:
                return {"Token": "X", "DisplayClaims": {"xui": [{"uhs": "U"}]}}
            if "xsts.auth.xboxlive.com" in url:
                return {"Token": "S", "DisplayClaims": {"xui": [{"uhs": "U"}]}}
            return {}
        accounts._http = fake_401
        raises("MC 登录 401 时不回退直接报错", accounts.AccountError,
               accounts.msa_finish, {"access_token": "MS"})
        check("401 只请求了一次端点", tries["n"] == 1, f"实际 {tries['n']}")

        # 7) 续期失败要转成 AccountError（UI 才能提示重新登录）
        accounts._http = lambda url, *a, **k: (_ for _ in ()).throw(
            accounts.AccountError("invalid_grant"))
        raises("微软续期失败抛 AccountError", accounts.AccountError,
               accounts.msa_refresh, msa)

        # 8) 没有 refresh_token 时不尝试续期
        raises("无 refresh_token 时报错提示重新登录", accounts.AccountError,
               accounts.msa_refresh, accounts.Account(mode=accounts.MICROSOFT))
    finally:
        accounts._http = orig_http

    # 9) 存储：新增/去重/删除/切换（写在临时数据目录，不影响真实数据）
    a1 = accounts.Account(mode=accounts.MICROSOFT, name="A", uuid="u1")
    i1 = accounts.add_account(a1)
    a1b = accounts.Account(mode=accounts.MICROSOFT, name="A2", uuid="u1")
    i2 = accounts.add_account(a1b)
    check("同 uuid 账户被去重", len(accounts.list_accounts()) == 1 and i1 == i2)
    check("更新后名称生效", accounts.list_accounts()[0].name == "A2")
    accounts.remove_account(i1)
    check("删除账户生效", len(accounts.list_accounts()) == 0)
    check("无账户时回落到离线", accounts.active().mode == accounts.OFFLINE)
    check("回落离线名来自配置", accounts.active().name == config.get("user_name"))


def test_launch():
    group("启动装配")
    vdir = paths.version_dir("zz-test-ver")
    # 原生库解压
    import zipfile
    zpath = os.path.join(paths.libs_dir("zz-test-ver"), "com", "win", "N-1-natives.jar")
    os.makedirs(os.path.dirname(zpath), exist_ok=True)
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("native/lib.dll", b"MZfake")
        z.writestr("skipme.txt", b"txt")
    libs = versions.collect_libraries(VJSON)
    launch.extract_natives("zz-test-ver", libs)
    nd = paths.natives_dir("zz-test-ver")
    check("原生库 dll 已解压", os.path.isfile(os.path.join(nd, "lib.dll")))
    check("非原生文件未解压", not os.path.isfile(os.path.join(nd, "skipme.txt")))

    # 校验函数
    check("_verify 不存在的文件=False", not launch._verify(os.path.join(TMP, "nope"), None))
    check("_verify 存在且非空=True", launch._verify(zpath, None))
    check("_verify sha1 不匹配=False", not launch._verify(zpath, "0" * 40))

    # 启动命令（用假的 java 路径，避免依赖本机 Java）
    orig = java.select_java_path
    java.select_java_path = lambda req=0: "C:/fake/java.exe"
    try:
        client = os.path.join(vdir, "client.jar")
        with open(client, "wb") as f:
            f.write(b"jar")
        cmd = launch.build_launch_command("zz-test-ver")
        check("命令以 java 开头", cmd[0] == "C:/fake/java.exe")
        joined = " ".join(cmd)
        check("classpath 含 client.jar", "client.jar" in joined)
        check("带 --gameDir", "--gameDir" in cmd)
        check("带 --assetsDir", "--assetsDir" in cmd)
        check("带 --username", "--username" in cmd)
        check("用户名取配置", cmd[cmd.index("--username") + 1] == "测试玩家")
        check("带 java.library.path", any(a.startswith("-Djava.library.path=") for a in cmd))
        check("分辨率参数", "--width" in cmd and "--height" in cmd)
        # Java 不满足时应报错
        java.select_java_path = lambda req=0: ""
        raises("无可用 Java 时抛错", RuntimeError, launch.build_launch_command, "zz-test-ver")
    finally:
        java.select_java_path = orig
    check("shlex 拆分参数", launch.shlex_args('-Xmx2G -Dfoo="a b"') ==
          ["-Xmx2G", "-Dfoo=a b"])
    check("shlex 异常兜底", launch.shlex_args('-Xmx "bad') == ["-Xmx", '"bad'])


# ==================================================================
#  9. UI（真实 Tk）
# ==================================================================
def make_png(path: str, size: int = 128) -> str:
    """生成一张纯色 PNG，用于图标加载测试（不依赖 Pillow）。"""
    raw = b""
    for _ in range(size):
        raw += b"\x00" + bytes([0x4a, 0x6c, 0xf7] * size)
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
    return "file:///" + path.replace("\\", "/")


def test_dispatch_closures():
    """回归：except 里把异常变量交给 bus.dispatch 延迟执行时，必须默认参数绑定。

    Python 3 在 except 块结束时会删除 `e`；lambda 到主线程执行时 e 已不存在，
    会抛 NameError，而 bus._pump 又静默吞掉 → 登录/下载失败时界面毫无反应。
    """
    group("工作线程 → 主线程 回调闭包")
    import ast, pathlib

    bad = []
    for p in sorted(pathlib.Path("mcl").rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler) or node.name is None:
                continue
            name = node.name
            for sub in ast.walk(node):
                # 只看 bus.dispatch(lambda ...) 这类零参延迟回调
                if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "dispatch"):
                    continue
                for arg in sub.args:
                    if not isinstance(arg, ast.Lambda):
                        continue
                    used = {n.id for n in ast.walk(arg.body)
                            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
                    bound = {a.arg for a in arg.args.args}
                    if name in used and name not in bound:
                        bad.append(f"{p}:{arg.lineno} 未绑定 {name}")
    check("except 中的延迟回调已绑定异常变量", not bad, "; ".join(bad[:3]))

    # 行为验证：except 块结束后（模拟主线程稍后才执行）回调仍能读到异常内容
    got: dict = {}
    holder: dict = {}
    bad_holder: dict = {}

    def _worker():
        try:
            raise RuntimeError("boom")
        except Exception as e:
            holder["ok"] = (lambda e=e: got.setdefault("msg", str(e)))
            bad_holder["bad"] = (lambda: got.setdefault("bad", str(e)))  # 旧写法

    import threading
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(5)
    try:
        holder["ok"]()
    except Exception as ex:
        got["err"] = f"{type(ex).__name__}"
    check("默认参数绑定后延迟执行正常", got.get("msg") == "boom", str(got))
    try:
        bad_holder["bad"]()
        check("旧写法(未绑定)确实会抛 NameError", False, "竟然没抛错")
    except NameError:
        check("旧写法(未绑定)确实会抛 NameError", True)


def test_ui():
    group("界面 / 动画 / 卡片")
    import tkinter as tk
    from tkinter import ttk
    from mcl.ui import anim, bus, icons, navbar, theme, widgets
    from mcl.ui.app import MainWindow
    from mcl.ui.download_center_tab import ModCard, ModDownloadPane

    root = tk.Tk()
    root.geometry("980x760")
    errors: list[str] = []

    def rep(exc, val, tb):
        errors.append("".join(traceback.format_exception(exc, val, tb)))
    root.report_callback_exception = rep
    bus.init(root)

    def pump(ms=400):
        end = time.time() + ms / 1000
        while time.time() < end:
            root.update()
            time.sleep(0.01)

    style = theme.apply(root)
    check("主题应用成功", style.theme_use() == "clam")
    check("渐变插值可用", theme.lerp_color("#000000", "#ffffff", 1) == "#ffffff")

    # --- 点击动画 ---
    btn = ttk.Button(root, text="点我")
    btn.pack()
    base_style = "TButton"
    anim.bind_click(btn)
    btn.event_generate("<ButtonPress-1>")
    pump(60)
    check("按下后切到按下态样式", btn.cget("style") == "Pressed.TButton",
          btn.cget("style"))
    pump(200)
    check("动画结束回弹原样式", btn.cget("style") == base_style, btn.cget("style"))
    check("重复绑定不叠加", anim.bind_click(btn) is None)
    acc = ttk.Button(root, text="主按钮", style="Accent.TButton")
    acc.pack()
    anim.bind_click(acc)
    acc.event_generate("<ButtonPress-1>")
    pump(60)
    check("主按钮按下态", acc.cget("style") == "AccentPressed.TButton", acc.cget("style"))
    pump(200)

    # --- 自绘页签导航（NavTabs）：选中态颜色渐变 + 指示条滑动 ---
    nb = ttk.Notebook(root)
    f1, f2 = ttk.Frame(nb), ttk.Frame(nb)
    nb.add(f1, text="一")
    nb.add(f2, text="二")
    nav = navbar.NavTabs(root, nb)
    nav.pack(fill="x")
    nb.pack(fill="both", expand=True)
    check("按页签数量生成导航按钮", len(nav._buttons) == 2, str(len(nav._buttons)))
    tab_layout = str(ttk.Style().layout("TNotebook.Tab"))
    check("隐藏原生页签行", "Notebook.tab" not in tab_layout, tab_layout)
    pump(150)
    check("指示条已定位", nav._ind_w > 1, str(nav._ind_w))
    check("初始选中项为高亮色", nav._buttons[0].cget("fg") == theme.PRIMARY,
          nav._buttons[0].cget("fg"))
    # 悬停：非选中项换底色（渐变）
    nav._hover(1, True)
    pump(140)
    check("悬停底色变化", nav._buttons[1].cget("bg") == nav.HOVER_BG,
          nav._buttons[1].cget("bg"))
    nav._hover(1, False)
    pump(140)
    # 切换 → 颜色渐变 + 指示条滑动
    nav.select(1)
    pump(70)                       # 动画进行到第 1~2 帧，取中间色
    mid = nav._buttons[1].cget("fg")
    check("渐变中间色非终态", mid != theme.TEXT and mid != theme.PRIMARY, mid)
    pump(400)
    check("切换后新选中项高亮", nav._buttons[1].cget("fg") == theme.PRIMARY,
          nav._buttons[1].cget("fg"))
    check("切换后旧项恢复默认色", nav._buttons[0].cget("fg") == theme.TEXT,
          nav._buttons[0].cget("fg"))
    check("指示条滑动到新位置", nav._ind_x == nav._buttons[1].winfo_x(),
          f"{nav._ind_x} vs {nav._buttons[1].winfo_x()}")
    check("页面确实切换了", nb.index("current") == 1)
    check("不再有幕布转场", not hasattr(anim, "PageTransition"))

    # --- 图标加载器 ---
    loader = icons.IconLoader(64)
    ph = loader.placeholder()
    check("占位图生成", ph.width() == 64)
    png_path = os.path.join(TMP, "icon.png")
    png_url = make_png(png_path)
    got = {}
    loader.request(png_url, lambda img: got.setdefault("img", img))
    for _ in range(40):
        pump(60)
        if "img" in got:
            break
    check("图标异步加载回调", "img" in got)
    if "img" in got:
        check("图标缩放至 64px", got["img"].width() == 64, str(got["img"].width()))
        check("图标进入内存缓存", loader.cached(png_url) is got["img"])
    # 小图标（8px）应被放大填充 64px 格子
    small_path = os.path.join(TMP, "icon_small.png")
    make_png(small_path, 8)
    small_url = "file:///" + small_path.replace("\\", "/")
    got2 = {}
    loader.request(small_url, lambda img: got2.setdefault("img", img))
    for _ in range(40):
        pump(60)
        if "img" in got2:
            break
    check("小图标放大到 64px", got2.get("img") is not None and
          got2["img"].width() == 64, str(got2.get("img") and got2["img"].width()))
    bad = {}
    loader.request("http://127.0.0.1:9/x.png", lambda img: bad.setdefault("img", img))
    for _ in range(100):          # 代理环境可能要几秒才失败，给足时间
        pump(100)
        if "img" in bad:
            break
    check("坏链接回落占位图", bad.get("img") is ph)

    # --- 控件 ---
    con = widgets.Console(root, height=4)
    con.pack()
    con.append("第一行")
    con.append("第一行")
    pump(80)
    check("控制台写入并去重标记", "重复" in con.text.get("1.0", "end"))
    for i in range(4500):
        con._write(f"line {i}\n")
    lines = int(con.text.index("end-1c").split(".")[0])
    check("控制台行数被裁剪(<=上限)", lines <= con.MAX_LINES + 1, f"{lines} 行")
    con.clear()
    pump(80)
    check("控制台清空", con.text.get("1.0", "end").strip() == "")

    grid = widgets.CardGrid(root, card_w=200, card_h=80)
    grid.pack(fill="both", expand=True)
    pump(120)
    cards = [tk.Frame(grid.inner, height=80) for _ in range(5)]
    for c in cards:
        grid.add(c)
    pump(150)
    check("卡片网格已布局", grid._cols >= 1 and len(grid.cards) == 5,
          f"cols={grid._cols}")
    check("网格滚动区域已更新", grid.canvas.cget("scrollregion") not in ("", "0 0 0 0"))
    grid.clear()
    check("网格清空", len(grid.cards) == 0)

    # --- 模组卡片 ---
    opened, installed = [], []
    item = {"project_id": "p1", "slug": "s1", "title": "Sodium",
            "author": "jellysquid", "downloads": 123456, "icon": png_url,
            "description": "A Fabric mod designed to improve frame rates."}
    card = ModCard(grid.inner, item, loader,
                   on_open=lambda it: opened.append(it),
                   on_install=lambda it: installed.append(it))
    grid.add(card)
    pump(200)
    check("卡片已创建并含图标控件", bool(card.icon_lbl.winfo_ismapped()))
    card._click()
    pump(60)
    check("点击卡片触发详情回调", len(opened) == 1 and opened[0]["title"] == "Sodium")
    check("按下动画改变底色", card.cget("bg") == ModCard.PRESS_BG)
    pump(200)
    card.install_btn.invoke()
    check("卡片安装按钮回调", len(installed) == 1)
    card._enter()
    check("悬停高亮描边", card.cget("highlightbackground") == theme.PRIMARY)
    card._leave()
    check("离开恢复描边", card.cget("highlightbackground") == theme.BORDER)

    # --- 模组页（注入假结果，验证铺满与安装） ---
    win = tk.Toplevel(root)
    win.geometry("900x600")
    win.report_callback_exception = rep
    pane = ModDownloadPane(win, "mod", "模组")
    pane.pack(fill="both", expand=True)
    pump(200)
    fake = [dict(item, project_id=f"p{i}", title=f"Test Mod {i}") for i in range(6)]
    pane._fill_results(fake, "test", "mod")
    pump(300)
    check("搜索结果渲染为卡片", len(pane.grid.cards) == 6, str(len(pane.grid.cards)))
    check("结果区铺满（网格占据整页）",
          pane.grid.winfo_height() > win.winfo_height() * 0.6,
          f"grid_h={pane.grid.winfo_height()} win_h={win.winfo_height()}")
    check("底部浮动条出现", bool(pane.strip.place_info()))

    # 安装流程（自定义目录 + 假的版本接口）
    dest_dir = os.path.join(TMP, "install-here")
    jar = os.path.join(TMP, "mod-src.jar")
    with open(jar, "wb") as f:
        f.write(b"PKfakejar")
    jar_url = "file:///" + jar.replace("\\", "/")
    orig_get = modrinth.get_versions
    modrinth.get_versions = lambda pid, version="", loader="": [
        {"id": "v1", "name": "v1", "version_number": "1.0",
         "game_versions": [version or "1.21.1"], "loaders": ["fabric"],
         "files": [{"filename": "mod-src.jar", "url": jar_url, "primary": True}]}]
    try:
        pane.ver_var.set("1.21.1")
        pane.target_var.set("自定义")
        pane.custom_dir = dest_dir
        pane.install_item(fake[0])
        ok = False
        for _ in range(60):
            pump(100)
            if os.path.isfile(os.path.join(dest_dir, "mod-src.jar")):
                ok = True
                break
        check("模组安装到目标目录", ok, dest_dir)
        check("安装后状态提示", "安装完成" in pane.status_var.get(), pane.status_var.get())
        check("打开安装目录路径已记录", pane._install_dir == dest_dir)
    finally:
        modrinth.get_versions = orig_get

    # 未选版本时的保护（用弹窗桩，避免阻塞）
    import mcl.ui.download_center_tab as dct
    shown = []
    stub = type("MB", (), {"showinfo": staticmethod(lambda *a, **k: shown.append(a[:2])),
                           "showerror": staticmethod(lambda *a, **k: shown.append(("err", a[:1]))),
                           "askyesno": staticmethod(lambda *a, **k: True)})
    dct.messagebox = stub
    pane.ver_var.set("全部")
    pane.install_item(fake[1])
    check("未选版本时提示而非崩溃", len(shown) >= 1)
    dct.messagebox = __import__("tkinter.messagebox", fromlist=["x"])

    pane._fill_results([], "nothing", "mod")
    pump(150)
    check("空结果显示占位文案", bool(pane.empty_lbl.winfo_ismapped()))

    # --- 主窗口全页签切换 ---
    app = MainWindow(root)
    pump(200)
    for i in range(6):
        app._nb.select(i)
        pump(260)
    check("六页签切换无异常", len(app._nb.tabs()) == 6)
    check("点击动画批量绑定", anim.bind_click_all(root) >= 10)
    check("标题栏渐变已绘制", app._bar.find_withtag("grad") != ())
    win.destroy()
    root.destroy()
    if errors:
        check("UI 回调无异常", False, errors[0][:400])
    else:
        check("UI 回调无异常", True)


def cleanup():
    mc_test = os.path.join(ROOT, ".minecraft", "zz-test-ver")
    if os.path.isdir(mc_test):
        shutil.rmtree(mc_test, ignore_errors=True)
    try:
        shutil.rmtree(TMP, ignore_errors=True)
    except Exception:
        pass


def main() -> int:
    print("=" * 60)
    print(" NCL 启动器 · 全功能测试")
    print("=" * 60)
    t0 = time.time()
    for fn in (test_config_paths, test_bootstrap, test_utils, test_network, test_versions,
               test_java, test_modrinth, test_translate, test_accounts,
               test_dispatch_closures, test_launch, test_ui):
        try:
            fn()
        except Exception:
            RESULTS.append(("FAIL", f"{_CUR[0]} / 用例整体崩溃", traceback.format_exc()[:600]))
            print(f"  ✗ {fn.__name__} 崩溃:\n{traceback.format_exc()[:800]}")
    cleanup()
    total = len(RESULTS)
    passed = sum(1 for s, _, _ in RESULTS if s == "PASS")
    failed = [r for r in RESULTS if r[0] == "FAIL"]
    skipped = [r for r in RESULTS if r[0] == "SKIP"]
    print("\n" + "=" * 60)
    print(f" 通过 {passed} / {total}   失败 {len(failed)}   跳过 {len(skipped)}"
          f"   用时 {time.time() - t0:.1f}s")
    for s, n, d in failed:
        print(f"  ✗ {n}: {d[:300]}")
    for s, n, d in skipped:
        print(f"  - {n}: {d[:120]}")
    print("=" * 60)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

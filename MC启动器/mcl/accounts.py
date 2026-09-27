"""账户管理：离线 / Microsoft 正版 / 外置登录（Yggdrasil）。

Microsoft 正版登录走 OAuth2 设备码流（device code flow），不需要在启动器里开本地端口，
也不需要客户端密钥，适合桌面启动器：

  1) POST login.microsoftonline.com/consumers/oauth2/v2.0/devicecode
     → user_code（用户在浏览器里输入的 8 位码）+ device_code + verification_uri
  2) 轮询 .../token（grant_type=urn:ietf:params:oauth:grant-type:device_code）
     → MS access_token / refresh_token
  3) MS token → Xbox Live 用户令牌（user.auth.xboxlive.com/user/authenticate）
  4) Xbox 令牌 → XSTS 令牌（xsts.auth.xboxlive.com/xsts/authorize，RelyingParty=minecraftservices）
  5) XSTS → api.minecraftservices.com/launcher/login → MC access_token
  6) api.minecraftservices.com/minecraft/profile → 角色名 + uuid

外置登录走 Yggdrasil（Blessing Skin / authlib-injector 等皮肤站）：
  POST <地址>/authserver/authenticate → accessToken + selectedProfile

令牌存于 NCLData/accounts.json。refresh_token 落盘，下次启动自动续期，
过期且续期失败时才要求重新登录。
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid as uuid_mod
from dataclasses import dataclass, field
from typing import Callable, Optional

from . import config, paths

log = None  # 延迟获取，避免导入顺序问题

OFFLINE = "offline"
MICROSOFT = "microsoft"
YGGDRASIL = "yggdrasil"

# 内置客户端 ID：来自开源启动器 picomc（公开可查）。若失效或你想用自己的，
# 在「设置 → 账户」里填入自己 Azure 应用的客户端 ID 即可覆盖。
MSA_CLIENT_ID_DEFAULT = "c52aed44-3b4d-4215-99c5-824033d2bc0f"
MSA_CLIENT_ID_FALLBACK = "69324f03-7b0c-48a3-a995-584127fba992"

MSA_TENANT = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
MSA_SCOPE = "XboxLive.signin offline_access"
XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
# XSTS 的 RelyingParty 必须是 rp:// 形式（写成 https:// 会被 Xbox 拒绝，返回 400）
XSTS_RP = "rp://api.minecraftservices.com/"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
# Minecraft 登录端点与字段名必须成对匹配：
#   老端点 authentication/login_with_xbox → identityToken
#   新端点 launcher/login                → xtoken
# 混用会返回 400 CONSTRAINT_VIOLATION。两个组合依次尝试，兼容服务端变更。
MC_LOGIN_ENDPOINTS = (
    ("https://api.minecraftservices.com/authentication/login_with_xbox", "identityToken"),
    ("https://api.minecraftservices.com/launcher/login", "xtoken"),
)

UA = {"User-Agent": "NCL-Launcher/1.1 (+https://github.com/doujiao-Studio/Minecraft-Launcher)"}

_lock = threading.RLock()


class AccountError(Exception):
    """账户相关错误（登录失败 / 令牌失效等）。"""

    def __init__(self, msg: str = "", code: int = 0, raw: str = ""):
        super().__init__(msg)
        self.code = code      # HTTP 状态码，0 = 非 HTTP 错误
        self.raw = raw        # 服务端原始响应，便于判断错误类型


class ProfileRequired(AccountError):
    """外置登录返回多个角色，需要用户先选一个。"""

    def __init__(self, profiles: list[dict], payload: dict, url: str):
        super().__init__("请选择要使用的角色")
        self.profiles = profiles
        self.payload = payload
        self.url = url


# ---------------------------------------------------------------- 数据模型

@dataclass
class Account:
    mode: str = OFFLINE
    name: str = "Steve"
    uuid: str = ""
    access_token: str = ""
    refresh_token: str = ""
    client_token: str = ""      # Yggdrasil 客户端标识
    ygg_url: str = ""           # 外置登录地址
    expires_at: float = 0.0     # Unix 时间戳，0 = 不自动过期
    skin_url: str = ""

    # ---- 派生属性 ----
    @property
    def user_type(self) -> str:
        """传给游戏的 --userType。"""
        return {MICROSOFT: "msa", YGGDRASIL: "mojang"}.get(self.mode, "legacy")

    @property
    def mode_label(self) -> str:
        return {MICROSOFT: "正版(Microsoft)", YGGDRASIL: "外置登录",
                OFFLINE: "离线"}.get(self.mode, self.mode)

    @property
    def expired(self) -> bool:
        return bool(self.expires_at) and time.time() >= self.expires_at - 300

    @property
    def needs_relogin(self) -> bool:
        """过期且没有可用的 refresh_token：只能重新登录。"""
        return self.expired and not self.refresh_token

    def label(self) -> str:
        return f"{self.mode_label} · {self.name}"

    def to_dict(self) -> dict:
        return dict(mode=self.mode, name=self.name, uuid=self.uuid,
                    access_token=self.access_token, refresh_token=self.refresh_token,
                    client_token=self.client_token, ygg_url=self.ygg_url,
                    expires_at=self.expires_at, skin_url=self.skin_url)

    @staticmethod
    def from_dict(d: dict) -> "Account":
        return Account(
            mode=d.get("mode", OFFLINE),
            name=d.get("name", "Steve"),
            uuid=d.get("uuid", ""),
            access_token=d.get("access_token", ""),
            refresh_token=d.get("refresh_token", ""),
            client_token=d.get("client_token", ""),
            ygg_url=d.get("ygg_url", ""),
            expires_at=float(d.get("expires_at", 0) or 0),
            skin_url=d.get("skin_url", ""),
        )


def offline_uuid(name: str) -> str:
    """离线模式的标准 uuid：md5("OfflinePlayer:<name>") 改写成 uuid v3 形式。"""
    h = hashlib.md5(("OfflinePlayer:" + (name or "Steve")).encode("utf-8")).digest()
    b = bytearray(h)
    b[6] = (b[6] & 0x0F) | 0x30
    b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid_mod.UUID(bytes=bytes(b)))


# ---------------------------------------------------------------- 存储

def _file() -> str:
    return os.path.join(paths.base_dir(), "accounts.json")


def _load_raw() -> dict:
    p = _file()
    if not os.path.exists(p):
        return {"accounts": [], "active": None}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {"accounts": [], "active": None}
    if not isinstance(data, dict):
        return {"accounts": [], "active": None}
    data.setdefault("accounts", [])
    data.setdefault("active", None)
    return data


def _save_raw(data: dict) -> None:
    p = _file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)
    try:
        # 尽力收紧权限（Windows 上无效果，主要照顾类 Unix）
        os.chmod(p, 0o600)
    except Exception:
        pass


def list_accounts() -> list[Account]:
    with _lock:
        return [Account.from_dict(d) for d in _load_raw()["accounts"]]


def active_index() -> Optional[int]:
    with _lock:
        data = _load_raw()
        idx = data.get("active")
        if isinstance(idx, int) and 0 <= idx < len(data["accounts"]):
            return idx
        return None


def set_active(index: Optional[int]) -> None:
    with _lock:
        data = _load_raw()
        data["active"] = index
        _save_raw(data)


def add_account(acc: Account) -> int:
    """新增或更新（按 mode+uuid 去重），返回索引。"""
    with _lock:
        data = _load_raw()
        for i, d in enumerate(data["accounts"]):
            if d.get("mode") == acc.mode and d.get("uuid") == acc.uuid:
                data["accounts"][i] = acc.to_dict()
                data["active"] = i
                _save_raw(data)
                return i
        data["accounts"].append(acc.to_dict())
        idx = len(data["accounts"]) - 1
        data["active"] = idx
        _save_raw(data)
        return idx


def remove_account(index: int) -> None:
    with _lock:
        data = _load_raw()
        if not (0 <= index < len(data["accounts"])):
            return
        data["accounts"].pop(index)
        act = data.get("active")
        if act == index:
            data["active"] = None
        elif isinstance(act, int) and act > index:
            data["active"] = act - 1
        _save_raw(data)


def update_account(index: int, acc: Account) -> None:
    with _lock:
        data = _load_raw()
        if 0 <= index < len(data["accounts"]):
            data["accounts"][index] = acc.to_dict()
            _save_raw(data)


def logout() -> None:
    """退出登录态，回到离线账户。"""
    set_active(None)


def offline_account(name: str | None = None) -> Account:
    """由配置构造离线账户（保持与旧版 user_name/uuid 兼容）。"""
    n = (name or config.get("user_name") or "Steve").strip() or "Steve"
    uid = config.get("uuid") or offline_uuid(n)
    return Account(mode=OFFLINE, name=n, uuid=uid, access_token="0")


def active() -> Account:
    """当前生效账户；未登录时回落到配置里的离线账户。"""
    idx = active_index()
    if idx is not None:
        accs = list_accounts()
        acc = accs[idx]
        if acc.mode != OFFLINE:
            return acc
        # 离线账户以配置里的昵称为准
        if acc.name != config.get("user_name"):
            acc.name = config.get("user_name", acc.name)
            acc.uuid = config.get("uuid", acc.uuid) or offline_uuid(acc.name)
    return offline_account()


def active_label() -> str:
    """给 UI 用的一行描述。"""
    acc = active()
    extra = ""
    if acc.mode != OFFLINE and acc.expired:
        extra = "（登录已过期）"
    return f"{acc.mode_label} · {acc.name}{extra}"


# ---------------------------------------------------------------- HTTP

def _http(url: str, data=None, headers: dict | None = None,
          timeout: int = 30, method: str | None = None,
          json_body=None) -> dict:
    """发请求并返回 JSON。

    data      → 表单编码（微软 OAuth 端点要求 application/x-www-form-urlencoded）
    json_body → JSON 编码（Xbox / Minecraft / Yggdrasil 端点）
    """
    body = None
    hdr = dict(UA)
    if json_body is not None:
        body = json.dumps(json_body).encode("utf-8")
        hdr["Content-Type"] = "application/json"
    elif data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        hdr["Content-Type"] = "application/x-www-form-urlencoded"
    if headers:
        hdr.update(headers)

    req = urllib.request.Request(url, data=body, headers=hdr, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = ""
        try:
            raw = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        raise AccountError(_friendly_http_error(url, e.code, raw),
                           code=e.code, raw=raw)
    except Exception as e:
        raise AccountError(f"网络错误：{e}")
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        raise AccountError(f"服务器返回了无法解析的内容：{raw[:120]}")


def _friendly_http_error(url: str, code: int, raw: str) -> str:
    try:
        j = json.loads(raw)
    except Exception:
        j = {}
    err = (j.get("error") or "").lower()
    desc = j.get("error_description") or ""
    if "minecraftservices" in url or "minecraft" in url:
        if code == 404:
            return "这个微软账号没有购买 Minecraft Java 版（接口返回 404）"
        if code == 401:
            return "Minecraft 令牌无效或已过期，请重新登录"
    if "login.microsoftonline.com" in url:
        if err == "invalid_client":
            return ("客户端 ID 无效或不允许设备码登录。请在「设置 → 账户」换成自己 "
                    "Azure 应用的客户端 ID（需开启「允许公共客户端流」）")
        if err in ("authorization_pending", "slow_down"):
            return err
        if desc:
            return f"微软登录失败（{err or code}）：{desc[:160]}"
    if "xsts.auth.xboxlive.com" in url:
        return _xsts_error(j)
    return f"HTTP {code}：{raw[:160] or url}"


def _xsts_error(j: dict) -> str:
    """把 XSTS 的错误码翻译成人话（玩家最常踩的几个）。"""
    code = str(j.get("XErr") or j.get("xErr") or "")
    msg = j.get("Message") or ""
    table = {
        "2148916233": "该微软账号没有 Xbox 档案（通常意味着没有购买 Minecraft）",
        "2148916235": "该账号所在地区被 Xbox Live 限制",
        "2148916238": "未成年账号未加入家庭组，无法登录",
        "2148916236": "账号需要完成年龄验证",
        "2148916237": "达到游戏时长限制",
        "2148916227": "该账号因违反社区准则被封禁",
    }
    if code in table:
        return f"{table[code]}（XSTS {code}）"
    return f"Xbox 验证失败：{msg or code or '未知错误'}"


# ---------------------------------------------------------------- Microsoft

def client_id() -> str:
    return (config.get("ms_client_id") or "").strip() or MSA_CLIENT_ID_DEFAULT


def _client_id_candidates() -> list[str]:
    """用户自填优先，其次内置默认，最后备用 ID。"""
    out = []
    custom = (config.get("ms_client_id") or "").strip()
    if custom:
        out.append(custom)
    out.append(MSA_CLIENT_ID_DEFAULT)
    out.append(MSA_CLIENT_ID_FALLBACK)
    seen, uniq = set(), []
    for c in out:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def msa_begin() -> dict:
    """第一步：申请设备码，返回 {user_code, verification_uri, device_code, ...}。"""
    last: Exception | None = None
    for cid in _client_id_candidates():
        try:
            j = _http(f"{MSA_TENANT}/devicecode",
                      {"client_id": cid, "scope": MSA_SCOPE}, timeout=30)
            j["client_id"] = cid
            return j
        except AccountError as e:
            last = e
            # 只有「客户端无效」才换下一个 ID，其他错误直接抛
            if "客户端 ID 无效" in str(e):
                continue
            raise
    raise AccountError(f"获取登录码失败：{last}")


def msa_poll(device_code: str, client_id_used: str, interval: int = 5,
             expires_in: int = 900,
             should_stop: Callable[[], bool] | None = None) -> dict:
    """第二步：轮询直到用户在浏览器里完成授权，返回微软 token。"""
    deadline = time.time() + max(30, expires_in)
    while time.time() < deadline:
        if should_stop and should_stop():
            raise AccountError("已取消登录")
        try:
            j = _http(f"{MSA_TENANT}/token", {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": client_id_used,
                "device_code": device_code,
            }, timeout=30)
            if j.get("access_token"):
                return j
        except AccountError as e:
            msg = str(e)
            if "authorization_pending" not in msg and "slow_down" not in msg:
                raise
        time.sleep(max(2, interval))
    raise AccountError("登录码已过期，请重新获取")


def _xbl_token(ms_access_token: str) -> tuple[str, str]:
    j = _http(XBL_URL, json_body={
        "Properties": {
            "AuthMethod": "RPS",
            "SiteName": "user.auth.xboxlive.com",
            "RpsTicket": f"d={ms_access_token}",
        },
        "RelyingParty": "http://auth.xboxlive.com",
        "TokenType": "JWT",
    })
    token = j.get("Token")
    uhs = ""
    try:
        uhs = j["DisplayClaims"]["xui"][0]["uhs"]
    except Exception:
        pass
    if not token:
        raise AccountError("Xbox Live 验证未返回令牌")
    return token, uhs


def _xsts_token(xbl: str) -> tuple[str, str]:
    j = _http(XSTS_URL, json_body={
        "Properties": {"SandboxId": "RETAIL", "UserTokens": [xbl]},
        "RelyingParty": XSTS_RP,
        "TokenType": "JWT",
    })
    token = j.get("Token")
    uhs = ""
    try:
        uhs = j["DisplayClaims"]["xui"][0]["uhs"]
    except Exception:
        pass
    if not token:
        raise AccountError(_xsts_error(j))
    return token, uhs


def _mc_login(uhs: str, xsts: str) -> dict:
    """用 XSTS 令牌换 Minecraft 访问令牌（端点/字段名成对尝试）。"""
    identity = f"XBL3.0 x={uhs};{xsts}"
    last: Exception | None = None
    for url, key in MC_LOGIN_ENDPOINTS:
        try:
            j = _http(url, json_body={key: identity})
        except AccountError as e:
            last = e
            # 端点下线或字段名不被接受才换组合；401/403 等是真实账号问题，直接抛
            if e.code in (400, 404, 405, 410) or "CONSTRAINT_VIOLATION" in (e.raw or ""):
                continue
            raise
        if j.get("access_token"):
            return j
        last = AccountError("Minecraft 服务未返回令牌")
    raise last or AccountError("Minecraft 服务未返回令牌")


def _mc_profile(access_token: str) -> dict:
    try:
        j = _http(MC_PROFILE_URL, headers={"Authorization": f"Bearer {access_token}"})
    except AccountError:
        return {}
    return j if isinstance(j, dict) else {}


def msa_finish(ms_token: dict) -> Account:
    """把微软 token 兑换成 Minecraft 账户（含角色名与 uuid）。"""
    access = ms_token.get("access_token", "")
    if not access:
        raise AccountError("微软令牌为空，登录未完成")
    xbl, _ = _xbl_token(access)
    xsts, uhs = _xsts_token(xbl)
    mc = _mc_login(uhs, xsts)
    token = mc.get("access_token", "")
    prof = _mc_profile(token)
    name = prof.get("name") or "Player"
    uid = prof.get("id") or mc.get("username") or ""
    if not uid:
        # 极少数账号（未设置角色名）没有 profile，退化用 username 兜底
        uid = offline_uuid(name)
    return Account(
        mode=MICROSOFT, name=name, uuid=uid, access_token=token,
        refresh_token=ms_token.get("refresh_token", ""),
        expires_at=time.time() + int(mc.get("expires_in", 86400)),
    )


def msa_login(on_code: Callable[[dict], None] | None = None,
              should_stop: Callable[[], bool] | None = None) -> Account:
    """完整设备码登录流程（阻塞，请在后台线程调用）。"""
    dc = msa_begin()
    if on_code:
        on_code(dc)
    ms = msa_poll(dc.get("device_code", ""), dc.get("client_id", client_id()),
                  interval=int(dc.get("interval", 5) or 5),
                  expires_in=int(dc.get("expires_in", 900) or 900),
                  should_stop=should_stop)
    return msa_finish(ms)


def msa_refresh(acc: Account) -> Account:
    """用 refresh_token 续期（微软令牌通常 24 小时有效）。"""
    if not acc.refresh_token:
        raise AccountError("登录已过期，请重新登录")
    last: Exception | None = None
    for cid in _client_id_candidates():
        try:
            j = _http(f"{MSA_TENANT}/token", {
                "client_id": cid,
                "grant_type": "refresh_token",
                "refresh_token": acc.refresh_token,
                "scope": MSA_SCOPE,
            }, timeout=30)
            if not j.get("access_token"):
                raise AccountError("续期未返回新令牌")
            new = msa_finish(j)
            new.refresh_token = j.get("refresh_token") or acc.refresh_token
            return new
        except AccountError as e:
            last = e
            if "客户端 ID 无效" in str(e):
                continue
            raise
    raise AccountError(f"续期失败：{last}")


# ---------------------------------------------------------------- Yggdrasil

def ygg_normalize(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        raise AccountError("请填写外置登录地址")
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


def ygg_authenticate(url: str, username: str, password: str) -> tuple[dict, list[dict]]:
    """外置登录第一步：账号密码换令牌。返回 (响应, 可选角色列表)。"""
    url = ygg_normalize(url)
    ct = config.get("ygg_client_token") or str(uuid_mod.uuid4())
    config.set("ygg_client_token", ct)
    payload = {
        "username": username,
        "password": password,
        "clientToken": ct,
        "requestUser": True,
    }
    try:
        j = _http(url + "/authserver/authenticate", json_body=payload, timeout=30)
    except AccountError:
        # 少数老皮肤站只实现了 /api/yggdrasil 前缀
        j = _http(url + "/api/yggdrasil/authserver/authenticate", json_body=payload, timeout=30)
    if not j.get("accessToken"):
        raise AccountError("外置登录失败：账号或密码错误，或该地址不是有效的认证服务器")
    sel = j.get("selectedProfile")
    profiles = j.get("availableProfiles") or ([sel] if sel else [])
    return j, [p for p in profiles if p]


def ygg_account(url: str, payload: dict, profile: dict) -> Account:
    """由登录响应 + 选定角色构造账户。"""
    return Account(
        mode=YGGDRASIL,
        name=profile.get("name", "Player"),
        uuid=profile.get("id", ""),
        access_token=payload.get("accessToken", ""),
        client_token=payload.get("clientToken", "") or config.get("ygg_client_token", ""),
        ygg_url=ygg_normalize(url),
    )


def ygg_refresh(acc: Account) -> Account:
    url = ygg_normalize(acc.ygg_url)
    j = _http(url + "/authserver/refresh", json_body={
        "accessToken": acc.access_token,
        "clientToken": acc.client_token,
        "requestUser": True,
    }, timeout=30)
    if not j.get("accessToken"):
        raise AccountError("外置登录续期失败，请重新登录")
    sel = j.get("selectedProfile") or {}
    acc.access_token = j["accessToken"]
    acc.client_token = j.get("clientToken", acc.client_token)
    if sel.get("name"):
        acc.name = sel["name"]
        acc.uuid = sel.get("id", acc.uuid)
    return acc


# ---------------------------------------------------------------- 统一入口

def ensure_valid(acc: Account) -> Account:
    """令牌快过期就自动续期；失败抛 AccountError（UI 提示重新登录）。"""
    if acc.mode == OFFLINE or not acc.expired:
        return acc
    new = msa_refresh(acc) if acc.mode == MICROSOFT else ygg_refresh(acc)
    # 写回存储
    idx = active_index()
    if idx is not None:
        update_account(idx, new)
    return new

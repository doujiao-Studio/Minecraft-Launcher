"""轻量翻译：MyMemory 免费接口（国内实测可用），带缓存与失败回退。

仅用于：中文搜索关键词 -> 英文，英文简介 -> 中文。失败时原样返回。
"""
from __future__ import annotations
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import utils

log = utils.get_logger("translate")

MYMEMORY = "https://api.mymemory.translated.net/get"
TIMEOUT = 6
_cache: dict = {}
_lock = threading.Lock()
_rate_lock = threading.Lock()
_last_ts = 0.0
RATE_INTERVAL = 0.25  # 每次请求最小间隔(秒)，防止触发免费接口限流


def has_chinese(s: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in (s or ""))


def is_translatable(s: str) -> bool:
    """判断是否需要翻译（非中文、含可读英文、长度适中）。"""
    s = (s or "").strip()
    if not s or len(s) > 300:
        return False
    if has_chinese(s):
        return False
    return bool(re.search(r"[A-Za-z]{3}", s))


def _request(text: str, to_zh: bool) -> str:
    global _last_ts
    with _rate_lock:
        now = time.time()
        wait = RATE_INTERVAL - (now - _last_ts)
        if wait > 0:
            time.sleep(wait)
        _last_ts = time.time()
    langpair = "en|zh-CN" if to_zh else "zh-CN|en"
    url = (f"{MYMEMORY}?q={urllib.parse.quote(text)}&langpair={langpair}")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                body = r.read().decode("utf-8", errors="replace")
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
    data = json.loads(body)
    t = (data.get("responseData", {}) or {}).get("translatedText", "")
    if t and t != text:
        return t
    return text


_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_HTML_ENT = re.compile(r"&#\d+;|&(?:amp|lt|gt|quot|#39|nbsp);")

# 常用模组中英对照（MyMemory 限流/翻不出时的兜底，key 为小写原名）
_ZH_DICT = {
    "sodium": "钠", "lithium": "锂", "phosphor": "磷", "hydrogen": "氢",
    "krypton": "氪", "starlight": "星光", "iris": "虹膜",
    "iris shaders": "虹膜着色器", "iris shader": "虹膜着色器",
    "fabric api": "Fabric API接口", "fabric language kotlin": "Fabric语言Kotlin",
    "mod menu": "模组菜单", "cloth config api": "布料配置API",
    "entity culling": "实体剔除", "ferritecore": "铁氧体核心",
    "immediatelyfast": "即时加载加速", "yetanotherconfiglib": "YACL配置库",
    "xaero's minimap": "Xaero小地图", "xaero's world map": "Xaero世界地图",
    "optifine": "高清修复", "jei": "JEI物品管理器",
    "just enough items": "JEI物品管理器", "jade": "玉",
    "create": "机械动力", "tinkers' construct": "匠魂", "tconstruct": "匠魂",
    "tinkers construct": "匠魂",
    "twilight forest": "暮色森林", "biomes o' plenty": "超多生物群系",
    "alex's mobs": "Alex的生物", "journeymap": "旅行地图",
    "worldedit": "创世神", "appleskin": "苹果皮", "controlling": "按键控制",
    "mouse tweaks": "鼠标手势", "neat": "生命值显示",
    "roughly enough items": "REI物品管理器", "rei": "REI物品管理器",
    "smooth boot": "平滑启动", "betterf3": "更好的F3",
    "sodium extra": "钠扩展", "reese's sodium options": "Sodium选项界面",
    "better advancements": "更好的进度", "keybind fix": "按键修复",
    "inventory tweaks": "背包整理", "just enough resources": "JER资源显示",
    "jermods": "JER资源显示", "chunk animator": "区块动画",
    "toast control": "通知控制", "betterframes": "更好的帧率",
    "litematica": "投影", "minihud": "迷你HUD", "tweakeroo": "实用扩展",
    "malilib": "MaLiLib", "wthit": "玉(WTHIT)", "shulkerbox tooltip": "潜影盒提示",
    "applied energistics 2": "应用能源2", "ae2": "应用能源2",
    "botania": "植物魔法", "draconic evolution": "龙之研究", "projecte": "等价交换",
    "extra utilities": "更多实用设备", "thaumcraft": "神秘时代",
    "buildcraft": "建筑工艺", "industrial craft 2": "工业时代2", "ic2": "工业时代2",
    "thermal expansion": "热力膨胀", "ender io": "末影接口",
    "immersive engineering": "沉浸工程", "forestry": "林业",
    "gallery mod": "画廊", "galacticraft": "星系", "hbm's nuclear tech mod": "HBM核技术",
    "nuclearcraft": "核电工艺", "pam's harvestcraft": "潘马斯农场",
    "better animals plus": "更多动物", "minecraft comes alive": "虚拟人生",
    "custom npc": "自定义NPC", "sprout": "芽", "wizardry": "巫术",
    "elemental craft": "元素工艺", "thebetweenlands": "交错次元",
    "rotten creatures": "腐烂生物", "mc dungeons weapons": "我的世界地下城武器",
    "quark": "夸克", "sophisticated backpacks": "精巧背包",
    "backpacked": "背包", "curios api": "饰品栏API", "curios": "饰品栏",
    "travellers backpack": "旅行者背包", "waystones": "路石",
    "gravestone mod": "墓碑", "gravestones": "墓碑", "death chest": "死亡宝箱",
    "corpse": "遗体", "ambientsounds": "环境音效", "sound physical": "物理音效",
    "dynamic surroundings": "动态环境", "biomes o plenty": "超多生物群系",
}


def _lookup_zh(name: str) -> str:
    return _ZH_DICT.get((name or "").lower().strip(), "")


def name_zh(name: str) -> str:
    """本地查常用模组中文名（即时、无网络）；查不到返回原名。"""
    zh = _ZH_DICT.get((name or "").lower().strip(), "")
    return zh or (name or "")


def _quality_ok(out: str, to_zh: bool) -> bool:
    """翻译结果质量校验：英->中必须含汉字，否则判定失败(可被乱码/回显蒙混)。"""
    if not out:
        return False
    out = _HTML_ENT.sub("", out)
    if to_zh:
        return bool(_CJK_RE.search(out))
    return bool(re.search(r"[A-Za-z]{3}", out))


def translate(text: str, to_zh: bool = True) -> str:
    """翻译文本；失败或结果质量不合格返回原文。线程安全 + 缓存。"""
    text = (text or "").strip()
    if not text:
        return text
    key = (text, to_zh)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            return hit
    try:
        out = _request(text, to_zh)
        if out != text and not _quality_ok(out, to_zh):
            out = text
    except Exception as e:
        log.debug("翻译失败 %r: %s", key, e)
        out = text
    if to_zh and (out == text or not _quality_ok(out, True)):
        zh = _lookup_zh(text)
        if zh:
            out = zh
    with _lock:
        _cache[key] = out
    return out


# 中文搜索词 -> 英文（本地即时映射，不依赖网络；在线翻译 429 时兜底）
_SEARCH_DICT = {
    "性能优化": "optimize", "优化": "optimize", "性能": "performance",
    "光影": "shader", "光影着色": "shader", "高清修复": "optifine",
    "小地图": "minimap", "地图": "map", "世界地图": "world map",
    "旅行地图": "journeymap", "投影": "litematica", "创世神": "worldedit",
    "钠": "sodium", "锂": "lithium", "磷": "phosphor",
    "背包整理": "inventory sorting", "背包": "backpack", "背包扩容": "backpack",
    "合成表": "recipe", "物品管理": "jei", "物品管理器": "jei",
    "鞘翅": "elytra", "飞行": "elytra",
    "汉化": "chinese localization", "中文": "chinese",
    "材质": "texture", "皮肤": "skin",
    "更多生物": "more mobs", "生物": "mob", "更多动物": "more animals",
    "龙": "dragon", "暮色": "twilight forest", "匠魂": "tinkers construct",
    "工业": "industrial craft", "科技": "technology", "魔法": "magic",
    "机械动力": "create", "机械": "create", "家具": "furniture",
    "女仆": "maid", "更好的": "better",
    "加速": "accelerate", "帧率": "fps", "帧": "fps", "卡顿": "lag",
    "生物群系": "biome", "维度": "dimension", "传送": "teleport",
    "建筑": "building", "武器": "weapon", "盔甲": "armor", "食物": "food",
    "宠物": "pet", "附魔": "enchant", "红石": "redstone",
    "末地": "end", "地狱": "nether", "下界": "nether", "洞穴": "cave",
    "地形": "terrain", "世界生成": "worldgen", "农业": "farming",
    "村民": "villager", "交易": "trade", "饰品": "bauble",
    "实体": "entity", "伤害": "damage", "血量": "health", "生命值": "health",
    "自然": "nature", "装饰": "decoration", "声音": "sound", "音效": "sound",
    "音乐": "music", "放大": "zoom", "像素": "pixel",
    "成就": "advancement", "进度": "advancement", "末影": "ender",
    "守卫者": "guardian", "幽灵": "phantom", "守卫": "guardian",
}


def to_english(query: str) -> str:
    """中文搜索词 -> 英文。优先本地词典（即时），否则在线翻译（失败回退原文）。"""
    q = (query or "").strip()
    if not q:
        return q
    hit = _SEARCH_DICT.get(q)
    if hit:
        return hit
    return translate(q, to_zh=False)


def translate_batch(items: list[str], to_zh: bool = True, workers: int = 2) -> list[str]:
    """并发翻译列表；只翻译需要翻译的项，其余原样。"""
    need = [(i, s) for i, s in enumerate(items) if is_translatable(s)]
    if not need:
        return list(items)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        out_map = {i: translate(s, to_zh) for i, s in need}
    return [out_map.get(i, s) for i, s in enumerate(items)]

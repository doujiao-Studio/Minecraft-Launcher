package com.ncl.launcher.mc

import com.google.gson.Gson
import com.google.gson.annotations.SerializedName
import com.ncl.launcher.net.Http

private val gson = Gson()

const val MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

data class ManifestVersion(
    val id: String = "",
    val type: String = "release",
    val url: String = "",
    val time: String = "",
    @SerializedName("releaseTime") val releaseTime: String = "",
    val sha1: String = ""
)

data class ManifestLatest(val release: String = "", val snapshot: String = "")

data class VersionManifest(
    val latest: ManifestLatest = ManifestLatest(),
    val versions: List<ManifestVersion> = emptyList()
)

// ---------------------------------------------------------------------------
//  version.json
// ---------------------------------------------------------------------------

data class Artifact(
    val path: String? = null,
    val url: String? = null,
    val sha1: String? = null,
    val size: Long = 0
)

data class LibraryDownloads(
    val artifact: Artifact? = null,
    val classifiers: Map<String, Artifact>? = null
)

data class OsRule(val name: String? = null, val version: String? = null, val arch: String? = null)

data class Rule(
    val action: String = "allow",
    val os: OsRule? = null,
    val features: Map<String, Boolean>? = null
)

data class Library(
    val name: String = "",
    val downloads: LibraryDownloads? = null,
    val rules: List<Rule>? = null,
    val natives: Map<String, String>? = null,
    val url: String? = null
)

data class AssetIndexRef(
    val id: String = "",
    val sha1: String = "",
    val size: Long = 0,
    val url: String = "",
    val totalSize: Long = 0
)

/** JSON 里 arguments 的 game/jvm 元素可能是字符串也可能是 {value, rules} 对象 —— 用 Any 承接 */
data class VersionDetails(
    val id: String = "",
    val type: String = "release",
    val mainClass: String = "",
    val assets: String? = null,
    @SerializedName("assetIndex") val assetIndex: AssetIndexRef? = null,
    val downloads: Map<String, Artifact>? = null,
    val libraries: List<Library>? = null,
    val arguments: Map<String, List<Any>>? = null,
    val minecraftArguments: String? = null,
    val javaVersion: Map<String, Any>? = null,
    val inheritsFrom: String? = null
)

data class AssetObject(val hash: String = "", val size: Long = 0)
data class AssetIndex(val objects: Map<String, AssetObject> = emptyMap(), val virtual: Boolean? = false)

object VersionManifest {

    /**
     * 拉取版本清单。
     * 注意：清单里的 `time` 是镜像刷新时间、`releaseTime` 才是发布日期 —— 必须按 releaseTime 排序，
     * 否则顺序会乱（桌面版踩过这个坑）。
     */
    @Throws(Exception::class)
    fun fetch(): VersionManifest {
        val raw = Http.get(MANIFEST_URL)
        val man = gson.fromJson(raw, VersionManifest::class.java)
            ?: throw IllegalStateException("版本清单解析失败")
        val sorted = man.versions
            .sortedByDescending { it.releaseTime.ifBlank { it.time } }
            .distinctBy { it.id }
        return man.copy(versions = sorted)
    }

    /** 只要正式版 + 快照（与桌面版下载中心一致） */
    fun installable(man: VersionManifest): List<ManifestVersion> =
        man.versions.filter { it.type == "release" || it.type == "snapshot" }

    fun fetchDetails(url: String): VersionDetails =
        gson.fromJson(Http.get(url), VersionDetails::class.java)
            ?: throw IllegalStateException("版本 json 解析失败: $url")

    fun fetchAssetIndex(ref: AssetIndexRef): AssetIndex =
        gson.fromJson(Http.get(ref.url), AssetIndex::class.java) ?: AssetIndex()

    /** library 是否适用于当前平台（Android 上的 JRE 对 MC 来说就是 linux/arm64） */
    fun libraryApplies(lib: Library): Boolean {
        val rules = lib.rules
        if (rules.isNullOrEmpty()) return true
        var allow = false // 有 rules 时默认 deny，靠 allow 规则打开
        for (r in rules) {
            if (!ruleMatches(r)) continue
            allow = r.action == "allow"
        }
        return allow
    }

    private fun ruleMatches(r: Rule): Boolean {
        val os = r.os
        if (os != null) {
            if (os.name != null && os.name != "linux") return false
        }
        val feats = r.features
        if (!feats.isNullOrEmpty()) {
            // 默认特性（如 is_demo_user）视为 false
            for ((k, v) in feats) if (v) return false
        }
        return true
    }

    /** maven 名 -> 本地库路径，例如 com.mojang:brigadier:1.0.17 */
    fun libraryPath(name: String, classifier: String? = null): String {
        val parts = name.split(":")
        if (parts.size < 3) return name
        val group = parts[0].replace('.', '/')
        val artifact = parts[1]
        val version = parts[2]
        var file = "$artifact-$version"
        if (parts.size >= 4) file = "$artifact-$version-${parts[3]}"
        if (!classifier.isNullOrBlank()) file = "$file-$classifier"
        return "$group/$artifact/$version/$file.jar"
    }
}

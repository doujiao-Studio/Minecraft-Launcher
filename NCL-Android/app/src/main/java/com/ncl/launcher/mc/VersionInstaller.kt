package com.ncl.launcher.mc

import com.ncl.launcher.data.Paths
import com.ncl.launcher.net.Http
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.util.zip.ZipInputStream

/**
 * 版本安装器：把官方 version.json 描述的 client.jar / libraries / assets 全部拉到本地。
 * 全程在 IO 线程执行，进度通过回调抛回主线程。
 */
object VersionInstaller {

    class Progress(val stage: String, val done: Int, val total: Int, val label: String = "")

    /**
     * @param entry 版本清单条目
     * @param onProgress 进度回调（已经切回调用者线程，通常是主线程）
     */
    suspend fun install(
        entry: ManifestVersion,
        onProgress: suspend (Progress) -> Unit,
        shouldCancel: () -> Boolean = { false }
    ): Result<String> = withContext(Dispatchers.IO) {
        runCatching {
            val vid = entry.id
            val dir = Paths.versionDir(vid)
            dir.mkdirs()

            // 1) version.json
            onProgress(Progress("版本信息", 0, 100, vid))
            val jsonText = Http.get(entry.url)
            File(dir, "version.json").writeText(jsonText)
            var details = VersionManifest.fetchDetails(entry.url)

            // 2) 继承链（Forge / Fabric / NeoForge 都 inheritsFrom 原版）
            var parentJson: VersionDetails? = null
            val parentId = details.inheritsFrom
            if (!parentId.isNullOrBlank()) {
                val pdir = Paths.versionDir(parentId)
                if (!File(pdir, "version.json").exists()) {
                    onProgress(Progress("父版本 $parentId", 3, 100))
                    installVanilla(parentId)
                }
                parentJson = readLocalDetails(parentId)
            }

            // 3) client.jar
            onProgress(Progress("游戏本体", 5, 100, vid))
            val clientUrl = details.downloads?.get("client")?.url
                ?: parentJson?.downloads?.get("client")?.url
            if (clientUrl != null) {
                val target = Paths.clientJar(vid)
                if (!target.exists() || target.length() <= 0) {
                    Http.download(clientUrl, target)
                }
            } else if (!Paths.clientJar(vid).exists() && parentId != null) {
                Paths.clientJar(parentId).copyTo(Paths.clientJar(vid), overwrite = true)
            }

            // 4) libraries（含继承）
            val libs = LinkedHashMap<String, Library>()
            parentJson?.libraries.orEmpty().forEach { libs[it.name] = it }
            details.libraries.orEmpty().forEach { libs[it.name] = it }
            val applicable = libs.values.filter { VersionManifest.libraryApplies(it) }

            val nativesDir = File(dir, "natives")
            nativesDir.mkdirs()

            var i = 0
            val libTotal = applicable.size.coerceAtLeast(1)
            for (lib in applicable) {
                if (shouldCancel()) return@runCatching vid
                i++
                val pct = 10 + (60 * i / libTotal)
                onProgress(Progress("依赖库", pct, 100, lib.name))

                val artifact = lib.downloads?.artifact
                val path = artifact?.path
                    ?: VersionManifest.libraryPath(lib.name)
                val out = File(Paths.librariesDir(), path)
                val url = artifact?.url ?: lib.url ?: defaultMavenUrl(lib.name)
                if (!out.exists() || out.length() <= 0) {
                    runCatching { Http.download(url, out) }
                        .onFailure { if (!defaultMavenUrl(lib.name).let { runCatching { Http.download(it, out) }.isSuccess }) throw it }
                }

                // natives：linux 分类 -> 解压出 .so
                val nativeKey = lib.natives?.get("linux") ?: lib.natives?.get("linux-arm64")
                if (!nativeKey.isNullOrBlank()) {
                    val classifier = lib.downloads?.classifiers?.get(nativeKey)
                    val nUrl = classifier?.url
                    if (!nUrl.isNullOrBlank()) {
                        val nOut = File(Paths.librariesDir(), classifier.path ?: VersionManifest.libraryPath(lib.name, nativeKey))
                        if (!nOut.exists() || nOut.length() <= 0) Http.download(nUrl, nOut)
                        runCatching { unzipSo(nOut, nativesDir) }
                    }
                }
            }

            // 5) assets
            val indexRef = details.assetIndex ?: parentJson?.assetIndex
            if (indexRef != null && indexRef.url.isNotBlank()) {
                onProgress(Progress("资源索引", 72, 100))
                val idxFile = File(Paths.assetsDir(), "indexes/${indexRef.id}.json")
                if (!idxFile.exists()) Http.download(indexRef.url, idxFile)
                val index = runCatching {
                    VersionManifest.fetchAssetIndex(indexRef)
                }.getOrElse { com.google.gson.Gson().fromJson(idxFile.readText(), AssetIndex::class.java) }
                    ?: AssetIndex()

                val objects = index.objects.values.distinctBy { it.hash }
                var j = 0
                for (obj in objects) {
                    if (shouldCancel()) return@runCatching vid
                    j++
                    if (j % 20 == 0 || j == objects.size) {
                        onProgress(Progress("游戏资源", 75 + 24 * j / objects.size.coerceAtLeast(1), 100, "$j/${objects.size}"))
                    }
                    val h = obj.hash
                    val out = File(Paths.assetsDir(), "objects/${h.substring(0, 2)}/$h")
                    if (out.exists() && out.length() > 0) continue
                    val url = "https://resources.download.minecraft.net/${h.substring(0, 2)}/$h"
                    runCatching { Http.download(url, out) }
                }
            }

            onProgress(Progress("完成", 100, 100, vid))
            vid
        }
    }

    /** 只装原版（作为 loader 的父版本） */
    suspend fun installVanilla(versionId: String) {
        val man = VersionManifest.fetch()
        val entry = man.versions.firstOrNull { it.id == versionId }
            ?: throw IllegalArgumentException("找不到版本 $versionId")
        install(entry, {}) { false }
    }

    private fun readLocalDetails(versionId: String): VersionDetails {
        val f = Paths.versionJson(versionId)
        return com.google.gson.Gson().fromJson(f.readText(), VersionDetails::class.java)
    }

    private fun defaultMavenUrl(name: String): String {
        val p = name.split(":")
        return if (name.contains("@")) {
            val n = name.removeSuffix(".jar").substringBefore("@")
            val parts = n.split(":")
            "https://bmclapi2.bangbang93.com/maven/${parts[0].replace('.', '/')}/${parts[1]}/${parts[2]}/${parts[1]}-${parts[2]}.jar"
        } else {
            val path = VersionManifest.libraryPath(name)
            "https://bmclapi2.bangbang93.com/maven/$path"
        }
    }

    /** 从 native jar 里抽出 .so（与桌面版一致的“解压到 natives 目录”做法） */
    fun unzipSo(zip: File, dest: File): Int {
        dest.mkdirs()
        var n = 0
        ZipInputStream(zip.inputStream()).use { zis ->
            while (true) {
                val e = zis.nextEntry ?: break
                if (e.isDirectory) continue
                val name = e.name.substringAfterLast('/')
                if (!name.endsWith(".so")) continue
                val out = File(dest, name)
                FileOutputStream(out).use { zis.copyTo(it) }
                n++
            }
        }
        return n
    }
}

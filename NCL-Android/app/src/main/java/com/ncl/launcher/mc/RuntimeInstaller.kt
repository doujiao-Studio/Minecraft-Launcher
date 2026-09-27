package com.ncl.launcher.mc

import com.ncl.launcher.data.Paths
import com.ncl.launcher.net.Http
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.tukaani.xz.XZInputStream
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream

/**
 * Android 上没有系统 JRE，必须自带一个 aarch64 的 JRE。
 * 本类负责：导入本地压缩包 / 联网下载 / 解压 / 补可执行权限。
 */
object RuntimeInstaller {

    /** 候选下载地址，逐个尝试（失效时可在设置里换自己的地址） */
    val DEFAULT_JRE_URLS = listOf(
        "https://github.com/PojavLauncherTeam/android-openjdk-build-multiarch/releases/latest/download/jre17-aarch64.tar.xz",
        "https://github.com/PojavLauncherTeam/android-openjdk-build-multiarch/releases/download/jre17-aarch64-20240218/jre17-aarch64-20240218.tar.xz"
    )

    private fun chmodExecutable(f: File) {
        runCatching {
            val p = Runtime.getRuntime().exec(arrayOf("chmod", "755", f.absolutePath))
            p.waitFor()
        }
        runCatching { f.setExecutable(true, true) }
    }

    fun hasRuntime(): Boolean = Paths.javaBin().exists()

    fun javaVersion(): String {
        val bin = Paths.javaBin()
        if (!bin.exists()) return "未安装"
        return runCatching {
            val p = ProcessBuilder(bin.absolutePath, "-version")
                .redirectErrorStream(true).start()
            val out = p.inputStream.bufferedReader().readText()
            p.waitFor()
            out.lines().firstOrNull()?.trim() ?: "未知"
        }.getOrDefault("未知")
    }

    /** 从 tar.xz / tar.gz / zip 安装运行时；tar.xz 是 Pojav JRE 的发布格式 */
    suspend fun installFromFile(src: File, onProgress: suspend (String) -> Unit): Result<Unit> =
        withContext(Dispatchers.IO) {
            runCatching {
                val staging = File(Paths.root, "tmp/runtime-stage")
                staging.deleteRecursively()
                staging.mkdirs()
                onProgress("解压中…")
                when {
                    src.name.endsWith(".tar.xz") -> untar(XZInputStream(src.inputStream()), staging)
                    src.name.endsWith(".xz") -> untar(XZInputStream(src.inputStream()), staging)
                    src.name.endsWith(".zip") -> unzip(src, staging)
                    src.name.endsWith(".tar.gz") || src.name.endsWith(".tgz") ->
                        untar(java.util.zip.GZIPInputStream(src.inputStream()), staging)
                    else -> throw IllegalArgumentException("不支持的运行时格式：${src.name}")
                }
                finishInstall(staging)
                onProgress("运行时安装完成")
            }
        }

    suspend fun downloadAndInstall(onProgress: suspend (String, Int) -> Unit): Result<Unit> =
        withContext(Dispatchers.IO) {
            runCatching {
                val tmp = File(Paths.root, "tmp/jre.tar.xz")
                tmp.parentFile?.mkdirs()
                var ok = false
                for (url in DEFAULT_JRE_URLS) {
                    onProgress("下载运行时…", 0)
                    ok = runCatching {
                        Http.download(url, tmp) { done, total ->
                            val pct = if (total > 0) (done * 100 / total).toInt() else 0
                            kotlinx.coroutines.runBlocking { onProgress("下载运行时…", pct) }
                            true
                        }
                    }.getOrDefault(false)
                    if (ok && tmp.length() > 1024) break
                }
                if (!ok) throw IllegalStateException("运行时下载失败，请在设置里手动导入 JRE")
                installFromFile(tmp) { onProgress(it, 100) }.getOrThrow()
                tmp.delete()
            }
        }

    /** 把解压出来的内容整理成 <NCLData>/runtime（内含 bin/java） */
    private fun finishInstall(staging: File) {
        // 有些包根目录下还有一层 jre17-aarch64/
        var base = staging
        if (!File(base, "bin/java").exists()) {
            base.walkTopDown().firstOrNull { it.isDirectory && File(it, "bin/java").exists() }?.let { base = it }
        }
        require(File(base, "bin/java").exists()) { "压缩包里找不到 bin/java" }

        val target = Paths.runtimeDir()
        if (target.exists()) target.deleteRecursively()
        target.parentFile?.mkdirs()
        base.copyRecursively(target, overwrite = true)

        // 权限：JVM 与所有 bin 下的可执行文件必须可执行
        File(target, "bin").walkTopDown().forEach { chmodExecutable(it) }
        File(target, "lib").walkTopDown().filter { it.name.endsWith(".so") }.forEach { chmodExecutable(it) }
        File(target, "lib/jli").walkTopDown().forEach { chmodExecutable(it) }
        staging.deleteRecursively()
    }

    /** 极简 tar 解包（GNU/ustar 足够覆盖 JDK 发布包） */
    private fun untar(input: InputStream, dest: File) {
        dest.mkdirs()
        val buf = ByteArray(512)
        var remainingName = ""
        var remainingBytes = 0L
        var out: FileOutputStream? = null

        fun skipPadded(len: Long, ins: java.io.InputStream) {
            val pad = (512 - (len % 512)) % 512
            if (pad > 0) ins.skip(pad)
        }

        input.use { ins ->
            while (true) {
                var read = 0
                while (read < 512) {
                    val n = ins.read(buf, read, 512 - read)
                    if (n <= 0) break
                    read += n
                }
                if (read < 512) break
                if (buf.all { it == 0.toByte() }) break

                val name = String(buf, 0, 512).trim { it == 0.toByte() || it.isWhitespace() }
                val sizeOctal = String(buf, 124, 12).trim { it == 0.toByte() || it.isWhitespace() }
                val size = if (sizeOctal.isBlank()) 0L else java.lang.Long.parseLong(sizeOctal.trim(), 8)
                val typeFlag = buf[156]
                val prefix = String(buf, 345, 155).trim { it == 0.toByte() }
                val fullName = (if (prefix.isNotBlank()) "$prefix/" else "") + name
                val target = File(dest, fullName)

                if (typeFlag == '5'.code.toByte()) {
                    target.mkdirs()
                    continue
                }
                if (typeFlag == 'L'.code.toByte()) { // GNU 长文件名
                    val nb = ByteArray(size.toInt())
                    var off = 0
                    while (off < nb.size) {
                        val n = ins.read(nb, off, nb.size - off)
                        if (n <= 0) break
                        off += n
                    }
                    remainingName = String(nb, 0, off).trim { it == 0.toByte() }
                    skipPadded(size, ins)
                    continue
                }

                val realTarget = if (remainingName.isNotBlank()) {
                    File(dest, remainingName).also { remainingName = "" }
                } else target
                realTarget.parentFile?.mkdirs()
                out = FileOutputStream(realTarget)
                var left = size
                val data = ByteArray(64 * 1024)
                while (left > 0) {
                    val n = ins.read(data, 0, minOf(left, data.size.toLong()).toInt())
                    if (n <= 0) break
                    out!!.write(data, 0, n)
                    left -= n
                }
                out.close()
                skipPadded(size, ins)
            }
        }
    }

    private fun unzip(zip: File, dest: File) {
        dest.mkdirs()
        java.util.zip.ZipInputStream(zip.inputStream()).use { zis ->
            while (true) {
                val e = zis.nextEntry ?: break
                val out = File(dest, e.name)
                if (e.isDirectory) {
                    out.mkdirs()
                    continue
                }
                out.parentFile?.mkdirs()
                FileOutputStream(out).use { zis.copyTo(it) }
            }
        }
    }
}

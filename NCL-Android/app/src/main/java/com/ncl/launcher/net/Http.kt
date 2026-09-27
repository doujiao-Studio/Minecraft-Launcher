package com.ncl.launcher.net

import com.ncl.launcher.data.Config
import com.ncl.launcher.data.ConfigStore
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.File
import java.io.FileOutputStream
import java.util.concurrent.TimeUnit

class HttpException(message: String) : Exception(message)

/**
 * 统一网络层。境外源在大陆访问慢，默认走 BMCLAPI 镜像（与桌面版一致）。
 */
object Http {

    private val client: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    val jsonClient = client

    /** 按当前镜像配置改写 URL */
    fun mirror(url: String): String {
        if (ConfigStore.load().mirror != Config.MIRROR_BMCLAPI) return url
        return when {
            url.startsWith("https://launchermeta.mojang.com") ->
                url.replace("https://launchermeta.mojang.com", "https://bmclapi2.bangbang93.com")
            url.startsWith("https://piston-meta.mojang.com") ->
                url.replace("https://piston-meta.mojang.com", "https://bmclapi2.bangbang93.com")
            url.startsWith("https://resources.download.minecraft.net") ->
                url.replace("https://resources.download.minecraft.net", "https://bmclapi2.bangbang93.com/assets")
            url.startsWith("https://libraries.minecraft.net") ->
                url.replace("https://libraries.minecraft.net", "https://bmclapi2.bangbang93.com/maven")
            url.startsWith("https://launcher.mojang.com") ->
                url.replace("https://launcher.mojang.com", "https://bmclapi2.bangbang93.com")
            else -> url
        }
    }

    fun get(url: String): String {
        val req = Request.Builder().url(mirror(url)).get().build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw HttpException("GET $url -> ${resp.code}")
            return resp.body?.string() ?: throw HttpException("空响应 $url")
        }
    }

    /** 带进度回调的下载；返回 false 表示取消 */
    fun download(
        url: String,
        target: File,
        onProgress: ((done: Long, total: Long) -> Boolean)? = null
    ): Boolean {
        target.parentFile?.mkdirs()
        val tmp = File(target.parentFile, target.name + ".part")
        val req = Request.Builder().url(mirror(url)).get().build()
        client.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw HttpException("下载失败 ${resp.code}: $url")
            val body = resp.body ?: throw HttpException("空响应 $url")
            val total = body.contentLength()
            var done = 0L
            body.byteStream().use { input ->
                FileOutputStream(tmp).use { out ->
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n <= 0) break
                        out.write(buf, 0, n)
                        done += n
                        if (onProgress != null && !onProgress(done, total)) {
                            out.close()
                            tmp.delete()
                            return false
                        }
                    }
                }
            }
        }
        if (target.exists()) target.delete()
        if (!tmp.renameTo(target)) {
            tmp.copyTo(target, overwrite = true)
            tmp.delete()
        }
        return true
    }
}

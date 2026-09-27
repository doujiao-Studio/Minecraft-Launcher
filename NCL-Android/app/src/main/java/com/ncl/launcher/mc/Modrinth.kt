package com.ncl.launcher.mc

import com.ncl.launcher.net.Http
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject

/** Modrinth 模组搜索 / 下载（与桌面版下载中心的模组页一致） */
object Modrinth {

    private const val API = "https://api.modrinth.com/v2"

    data class Project(
        val slug: String,
        val title: String,
        val description: String,
        val iconUrl: String,
        val downloads: Long
    )

    data class VersionFile(val versionId: String, val url: String, val fileName: String)

    suspend fun search(query: String, loader: String = "fabric"): List<Project> =
        withContext(Dispatchers.IO) {
            val q = java.net.URLEncoder.encode(query, "UTF-8")
            val facets = java.net.URLEncoder.encode(
                "[[\"project_type:mod\"],[\"categories:$loader\"]]", "UTF-8"
            )
            val txt = Http.get("$API/search?query=$q&limit=30&index=relevance&facets=$facets")
            val arr = JSONObject(txt).getJSONArray("hits")
            val out = ArrayList<Project>()
            for (i in 0 until arr.length()) {
                val o = arr.getJSONObject(i)
                out.add(
                    Project(
                        slug = o.optString("slug"),
                        title = o.optString("title"),
                        description = o.optString("description").take(80),
                        iconUrl = o.optString("icon_url"),
                        downloads = o.optLong("downloads")
                    )
                )
            }
            out
        }

    /** 取该模组适配指定 MC 版本的最新文件 */
    suspend fun downloadable(slug: String, mcVersion: String, loader: String): VersionFile? =
        withContext(Dispatchers.IO) {
            val txt = runCatching { Http.get("$API/project/$slug/version") }.getOrNull() ?: return@withContext null
            val arr = org.json.JSONArray(txt)
            for (i in 0 until arr.length()) {
                val v = arr.getJSONObject(i)
                val loaders = v.optJSONArray("loaders") ?: continue
                var hasLoader = false
                for (j in 0 until loaders.length()) if (loaders.getString(j) == loader) hasLoader = true
                if (!hasLoader) continue
                val gv = v.optJSONArray("game_versions")
                if (gv != null && mcVersion.isNotBlank()) {
                    var ok = false
                    for (j in 0 until gv.length()) if (gv.getString(j) == mcVersion) ok = true
                    if (!ok) continue
                }
                val files = v.optJSONArray("files") ?: continue
                for (j in 0 until files.length()) {
                    val f = files.getJSONObject(j)
                    if (f.optBoolean("primary", j == 0)) {
                        return@withContext VersionFile(
                            v.optString("id"), f.getString("url"), f.getString("filename")
                        )
                    }
                }
            }
            null
        }
}

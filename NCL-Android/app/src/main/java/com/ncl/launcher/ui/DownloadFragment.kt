package com.ncl.launcher.ui

import android.os.Bundle
import android.view.View
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.ncl.launcher.R
import com.ncl.launcher.data.ConfigStore
import com.ncl.launcher.data.Paths
import com.ncl.launcher.databinding.FragmentDownloadBinding
import com.ncl.launcher.mc.ManifestVersion
import com.ncl.launcher.mc.Modrinth
import com.ncl.launcher.mc.VersionInstaller
import com.ncl.launcher.mc.VersionManifest
import com.ncl.launcher.net.Http
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray

/** 下载中心：游戏版本 / Modrinth 模组 / 加载器（Fabric、Quilt） */
class DownloadFragment : Fragment(R.layout.fragment_download) {

    private var _b: FragmentDownloadBinding? = null
    private val b get() = _b!!

    private lateinit var adapter: SimpleAdapter
    private var manifest: List<ManifestVersion> = emptyList()
    private var installing = false

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        _b = FragmentDownloadBinding.bind(view)

        adapter = SimpleAdapter(onClick = { item -> onItemClick(item) })
        b.rv.layoutManager = LinearLayoutManager(requireContext())
        b.rv.adapter = adapter

        b.rgMode.setOnCheckedChangeListener { _, id ->
            b.rowSearch.visibility = if (id == R.id.rbMod) View.VISIBLE else View.GONE
            when (id) {
                R.id.rbGame -> loadVersions()
                R.id.rbLoader -> loadLoaders()
                else -> adapter.submitList(
                    listOf(RowItem("输入关键词搜索模组", "例如 sodium、iris、jei", payload = "hint"))
                )
            }
        }
        b.btnSearch.setOnClickListener { searchMods(b.etSearch.text.toString()) }

        loadVersions()
    }

    // ------------------------------------------------------------ 游戏版本
    private fun loadVersions() {
        lifecycleScope.launch {
            b.tvProgress.text = "正在获取版本清单…"
            b.rowProgress.visibility = View.VISIBLE
            val list = withContext(Dispatchers.IO) {
                runCatching { VersionManifest.installable(VersionManifest.fetch()) }.getOrDefault(emptyList())
            }
            b.rowProgress.visibility = View.GONE
            if (list.isEmpty()) {
                toast("版本清单获取失败，检查网络后在「设置」里换镜像")
                return@launch
            }
            manifest = list
            adapter.submitList(list.map {
                RowItem(
                    title = it.id,
                    sub = when (it.type) { "snapshot" -> "快照" else -> "正式版" } +
                        " · 发布于 ${it.releaseTime.take(10)}",
                    tail = if (Paths.versionDir(it.id).exists()) "已安装" else "",
                    payload = it.id
                )
            })
        }
    }

    // --------------------------------------------------------------- 模组
    private fun searchMods(q: String) {
        if (q.isBlank()) return
        lifecycleScope.launch {
            b.tvProgress.text = "搜索中…"
            b.rowProgress.visibility = View.VISIBLE
            val res = withContext(Dispatchers.IO) {
                runCatching { Modrinth.search(q, "fabric") }.getOrDefault(emptyList())
            }
            b.rowProgress.visibility = View.GONE
            adapter.submitList(res.map {
                RowItem(
                    title = it.title,
                    sub = it.description,
                    tail = "${it.downloads / 1000}k 下载",
                    payload = it.slug
                )
            })
            if (res.isEmpty()) toast("没有搜到，换个关键词试试")
        }
    }

    // ------------------------------------------------------------- 加载器
    private fun loadLoaders() {
        val installed = Paths.installedVersions()
        adapter.submitList(
            listOf(
                RowItem("Fabric", "安装最新稳定版到已装版本", payload = "loader:fabric"),
                RowItem("Quilt", "安装最新稳定版到已装版本", payload = "loader:quilt"),
                RowItem(
                    "Forge / NeoForge",
                    "需要跑官方 installer，Android 上暂不支持自动安装，建议用 Fabric / Quilt",
                    payload = "loader:none", dim = true
                ),
                RowItem("已安装版本：${installed.size} 个", installed.joinToString("  "), payload = "info")
            )
        )
    }

    private fun onItemClick(item: RowItem) {
        if (installing) {
            toast("正在安装，请稍候")
            return
        }
        val payload = item.payload as? String ?: return
        when {
            payload == "loader:fabric" -> installLoader("fabric")
            payload == "loader:quilt" -> installLoader("quilt")
            payload.startsWith("loader:") -> toast("该加载器暂不支持自动安装")
            payload == "hint" || payload == "info" -> {}
            manifest.any { it.id == payload } -> {
                val entry = manifest.first { it.id == payload }
                doInstall(entry)
            }
            else -> downloadMod(payload)
        }
    }

    private fun doInstall(entry: ManifestVersion) {
        installing = true
        lifecycleScope.launch {
            b.rowProgress.visibility = View.VISIBLE
            b.pb.progress = 0
            val res = VersionInstaller.install(
                entry,
                // 注意：install 在 IO 线程回调，UI 必须切回主线程
                onProgress = { p ->
                    lifecycleScope.launch(Dispatchers.Main) {
                        b.pb.progress = p.done
                        b.tvProgress.text = "${p.stage} ${p.done}%  ${p.label}"
                    }
                },
                shouldCancel = { false }
            )
            b.rowProgress.visibility = View.GONE
            installing = false
            if (res.isSuccess) toast("${entry.id} 安装完成") else toast("安装失败：${res.exceptionOrNull()?.message}")
        }
    }

    /** Fabric / Quilt：拉 profile json 当作一个「继承原版」的版本来装 */
    private fun installLoader(kind: String) {
        val mc = Paths.installedVersions().firstOrNull()
        if (mc.isNullOrBlank()) {
            toast("请先安装一个原版游戏版本")
            return
        }
        installing = true
        lifecycleScope.launch {
            b.rowProgress.visibility = View.VISIBLE
            b.tvProgress.text = "查询 $kind 版本…"
            val ok = withContext(Dispatchers.IO) {
                runCatching {
                    val api = if (kind == "fabric") "https://meta.fabricmc.net/v2"
                    else "https://meta.quiltmc.org/v3"
                    val listUrl = "$api/versions/loader/$mc"
                    val arr = JSONArray(Http.get(listUrl))
                    var loaderVer = ""
                    for (i in 0 until arr.length()) {
                        val o = arr.getJSONObject(i).optJSONObject("loader") ?: continue
                        if (kind == "fabric" && !o.optBoolean("stable", false)) continue
                        loaderVer = o.optString("version")
                        if (kind == "fabric") break
                    }
                    if (loaderVer.isBlank()) loaderVer = arr.getJSONObject(0).optJSONObject("loader")?.optString("version") ?: ""
                    val profileUrl = if (kind == "fabric")
                        "https://meta.fabricmc.net/v2/versions/loader/$mc/$loaderVer/profile/json"
                    else
                        "https://meta.quiltmc.org/v3/versions/loader/$mc/$loaderVer/profile/json"
                    val json = Http.get(profileUrl)
                    val id = org.json.JSONObject(json).optString("id")
                    require(id.isNotBlank()) { "加载器 profile 无效" }
                    VersionInstaller.install(
                        ManifestVersion(id = id, type = "release", url = profileUrl),
                        onProgress = { p ->
                            lifecycleScope.launch {
                                b.pb.progress = p.done
                                b.tvProgress.text = "${p.stage} ${p.done}% ${p.label}"
                            }
                        }
                    ).getOrThrow()
                }
            }
            b.rowProgress.visibility = View.GONE
            installing = false
            if (ok.isSuccess) toast("$kind 安装完成") else toast("安装失败：${ok.exceptionOrNull()?.message}")
        }
    }

    /** 模组下载到当前版本的 mods 目录 */
    private fun downloadMod(slug: String) {
        val vid = ConfigStore.load().lastVersion.ifBlank { Paths.installedVersions().firstOrNull() ?: "" }
        if (vid.isBlank()) {
            toast("请先安装一个游戏版本")
            return
        }
        lifecycleScope.launch {
            b.rowProgress.visibility = View.VISIBLE
            b.tvProgress.text = "获取下载地址…"
            val res = withContext(Dispatchers.IO) {
                runCatching {
                    val f = Modrinth.downloadable(slug, vid, "fabric")
                        ?: throw IllegalStateException("没有适配 $vid 的版本")
                    val dir = Paths.modsDir(vid).apply { mkdirs() }
                    Http.download(f.url, java.io.File(dir, f.fileName))
                    f.fileName
                }
            }
            b.rowProgress.visibility = View.GONE
            res.onSuccess { toast("已下载 $it 到 $vid 的模组目录") }
                .onFailure { toast("下载失败：${it.message}") }
        }
    }

    override fun onDestroyView() {
        _b = null
        super.onDestroyView()
    }
}

package com.ncl.launcher.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.ArrayAdapter
import androidx.activity.result.contract.ActivityResultContracts
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.ncl.launcher.R
import com.ncl.launcher.auth.AccountStore
import com.ncl.launcher.data.Config
import com.ncl.launcher.data.ConfigStore
import com.ncl.launcher.data.Paths
import com.ncl.launcher.databinding.FragmentSettingsBinding
import com.ncl.launcher.mc.RuntimeInstaller
import kotlinx.coroutines.launch
import java.io.File

/** 设置：数据目录 / Java 运行时 / 镜像 / 渲染器 / 账户 / 缓存 */
class SettingsFragment : Fragment(R.layout.fragment_settings) {

    private var _b: FragmentSettingsBinding? = null
    private val b get() = _b!!

    private val mirrors = listOf(Config.MIRROR_BMCLAPI, Config.MIRROR_MOJANG)
    private val mirrorLabels = listOf("BMCLAPI 镜像（国内快）", "Mojang 官方源")
    private val renderers = listOf(
        Config.RENDERER_AUTO, Config.RENDERER_GL4ES,
        Config.RENDERER_MOBILEGLUES, Config.RENDERER_VULKAN
    )
    private val rendererLabels = listOf("自动", "gl4es（兼容性好）", "MobileGlues（OpenGL 3.2）", "Vulkan 包装")

    /** 导入 JRE：系统文件选择器 */
    private val pickRuntime = registerForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) return@registerForActivityResult
        lifecycleScope.launch {
            b.tvRuntime.text = "正在解压…"
            val tmp = File(Paths.root, "tmp/import-runtime")
            tmp.parentFile?.mkdirs()
            val copied = runCatching {
                requireContext().contentResolver.openInputStream(uri)?.use { input ->
                    tmp.outputStream().use { input.copyTo(it) }
                }
                tmp
            }.getOrNull()
            if (copied == null) {
                b.tvRuntime.text = "读取文件失败"
                return@launch
            }
            val res = RuntimeInstaller.installFromFile(copied) { b.tvRuntime.text = it }
            copied.delete()
            b.tvRuntime.text = if (res.isSuccess) "已安装：${RuntimeInstaller.javaVersion()}"
            else "安装失败：${res.exceptionOrNull()?.message}"
        }
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        _b = FragmentSettingsBinding.bind(view)
        val cfg = ConfigStore.load()

        b.tvDataDir.text = Paths.root.absolutePath
        b.tvAbout.text = "NCL 启动器 Android 版 v1.0.0\n游戏目录：${Paths.minecraftRoot.absolutePath}"

        b.tvRuntime.text = if (RuntimeInstaller.hasRuntime())
            "已安装：${RuntimeInstaller.javaVersion()}" else "未安装"
        b.btnImportRuntime.setOnClickListener {
            pickRuntime.launch(arrayOf("*/*"))
        }
        b.btnDownloadRuntime.setOnClickListener {
            lifecycleScope.launch {
                b.tvRuntime.text = "准备下载…"
                val res = RuntimeInstaller.downloadAndInstall { msg, pct ->
                    b.tvRuntime.text = "$msg $pct%"
                }
                b.tvRuntime.text = if (res.isSuccess) "已安装：${RuntimeInstaller.javaVersion()}"
                else "下载失败：${res.exceptionOrNull()?.message}"
            }
        }

        b.spMirror.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, mirrorLabels)
        b.spMirror.setSelection(mirrors.indexOf(cfg.mirror).coerceAtLeast(0))
        b.spMirror.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: android.widget.AdapterView<*>, v: View?, i: Int, id: Long) {
                ConfigStore.edit { it.mirror = mirrors[i] }
            }
            override fun onNothingSelected(p: android.widget.AdapterView<*>) {}
        }

        b.spRenderer.adapter = ArrayAdapter(requireContext(), android.R.layout.simple_spinner_dropdown_item, rendererLabels)
        b.spRenderer.setSelection(renderers.indexOf(cfg.renderer).coerceAtLeast(0))
        b.spRenderer.onItemSelectedListener = object : android.widget.AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: android.widget.AdapterView<*>, v: View?, i: Int, id: Long) {
                ConfigStore.edit { it.renderer = renderers[i] }
            }
            override fun onNothingSelected(p: android.widget.AdapterView<*>) {}
        }

        b.btnOpenData.setOnClickListener { requireContext().openDir(Paths.root.absolutePath) }

        b.btnMsLogin.setOnClickListener {
            startActivity(Intent(requireContext(), AccountActivity::class.java))
        }
        b.btnManage.setOnClickListener {
            startActivity(Intent(requireContext(), AccountActivity::class.java))
        }
        b.btnLogout.setOnClickListener {
            AccountStore.logout()
            updateAccount()
            toast("已退出登录")
        }

        b.btnCleanCache.setOnClickListener {
            val n = runCatching {
                Paths.cacheDir().deleteRecursively()
                Paths.cacheDir().mkdirs()
                true
            }.isSuccess
            toast(if (n) "缓存已清理" else "清理失败")
        }

        updateAccount()
    }

    override fun onResume() {
        super.onResume()
        updateAccount()
    }

    private fun updateAccount() {
        val acc = AccountStore.active()
        _b?.tvAccount?.text = "${acc.name} · ${acc.displayType}"
    }

    override fun onDestroyView() {
        _b = null
        super.onDestroyView()
    }
}

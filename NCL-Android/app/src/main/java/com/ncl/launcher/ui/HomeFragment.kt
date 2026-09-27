package com.ncl.launcher.ui

import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.SeekBar
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import com.ncl.launcher.R
import com.ncl.launcher.auth.AccountStore
import com.ncl.launcher.data.Config
import com.ncl.launcher.data.ConfigStore
import com.ncl.launcher.data.Paths
import com.ncl.launcher.databinding.FragmentHomeBinding
import com.ncl.launcher.mc.RuntimeInstaller
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** 启动页：选版本 / 调内存 / 选渲染器 / 启动游戏 */
class HomeFragment : Fragment(R.layout.fragment_home) {

    private var _b: FragmentHomeBinding? = null
    private val b get() = _b!!

    private val renderers = listOf(Config.RENDERER_AUTO, Config.RENDERER_GL4ES, Config.RENDERER_MOBILEGLUES, Config.RENDERER_VULKAN)
    private val rendererLabels = listOf("自动", "gl4es（兼容性好）", "MobileGlues（OpenGL 3.2）", "Vulkan 包装")

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        _b = FragmentHomeBinding.bind(view)
        val cfg = ConfigStore.load()

        // 版本
        val versions = Paths.installedVersions()
        b.spVersion.adapter = ArrayAdapter(
            requireContext(), android.R.layout.simple_spinner_dropdown_item,
            if (versions.isEmpty()) listOf("（无可用版本）") else versions
        )
        val lastIdx = versions.indexOf(cfg.lastVersion)
        if (lastIdx >= 0) b.spVersion.setSelection(lastIdx)
        b.spVersion.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>, v: View?, i: Int, id: Long) {
                val sel = versions.getOrNull(i) ?: return
                ConfigStore.edit { it.lastVersion = sel }
                updateVersionInfo(sel)
            }
            override fun onNothingSelected(p: AdapterView<*>) {}
        }
        updateVersionInfo(versions.getOrNull(lastIdx) ?: versions.firstOrNull() ?: "")

        // 内存
        val mem = cfg.memory.coerceIn(512, 4096)
        b.sbMem.progress = mem
        b.tvMem.text = "内存分配：$mem MB"
        b.sbMem.setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
            override fun onProgressChanged(sb: SeekBar?, p: Int, fromUser: Boolean) {
                val v = (p / 128).coerceAtLeast(4) * 128
                b.tvMem.text = "内存分配：$v MB"
                if (fromUser) ConfigStore.edit { it.memory = v }
            }
            override fun onStartTrackingTouch(sb: SeekBar?) {}
            override fun onStopTrackingTouch(sb: SeekBar?) {}
        })

        // 渲染器
        b.spRenderer.adapter = ArrayAdapter(
            requireContext(), android.R.layout.simple_spinner_dropdown_item, rendererLabels
        )
        b.spRenderer.setSelection(renderers.indexOf(cfg.renderer).coerceAtLeast(0))
        b.spRenderer.onItemSelectedListener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>, v: View?, i: Int, id: Long) {
                ConfigStore.edit { it.renderer = renderers[i] }
            }
            override fun onNothingSelected(p: AdapterView<*>) {}
        }

        b.tvRuntime.text = if (RuntimeInstaller.hasRuntime())
            "已安装：${RuntimeInstaller.javaVersion()}" else "未安装运行时"

        b.btnMsLogin.setOnClickListener {
            startActivity(Intent(requireContext(), AccountActivity::class.java))
        }
        b.btnManage.setOnClickListener {
            startActivity(Intent(requireContext(), AccountActivity::class.java))
        }
        b.btnLaunch.setOnClickListener { launch() }

        updateAccount()
    }

    override fun onResume() {
        super.onResume()
        updateAccount()
        _b?.tvRuntime?.text = if (RuntimeInstaller.hasRuntime())
            "已安装：${RuntimeInstaller.javaVersion()}" else "未安装运行时"
    }

    private fun updateAccount() {
        val acc = AccountStore.active()
        _b?.tvAccount?.text = "${acc.name} · ${acc.displayType}"
    }

    private fun updateVersionInfo(vid: String) {
        if (vid.isBlank()) {
            b.tvVersionInfo.text = "还没有安装版本，请到「下载」页获取"
            return
        }
        val jar = Paths.clientJar(vid)
        b.tvVersionInfo.text = if (jar.exists())
            "$vid · 本体 ${com.ncl.launcher.mc.Scan.humanSize(jar.length())}"
        else "$vid · 本体缺失，请重新下载"
    }

    private fun launch() {
        val versions = Paths.installedVersions()
        val vid = versions.getOrNull(b.spVersion.selectedItemPosition) ?: ""
        if (vid.isBlank()) {
            toast("请先在「下载」页安装一个游戏版本")
            return
        }
        if (!RuntimeInstaller.hasRuntime()) {
            toast("还没有 Java 运行时，请到「设置」页导入或下载 JRE")
            return
        }
        if (!Paths.clientJar(vid).exists()) {
            toast("版本 $vid 缺少 client.jar，请重新下载")
            return
        }
        ConfigStore.edit { it.lastVersion = vid }
        val acc = AccountStore.active()
        if (acc.type == "offline" && acc.name.isBlank()) {
            toast("请先在账户里设置一个游戏名")
            return
        }
        lifecycleScope.launch {
            b.btnLaunch.isEnabled = false
            b.tvStatus.text = "正在准备启动参数…"
            val ok = withContext(Dispatchers.IO) {
                runCatching { com.ncl.launcher.mc.McLauncher.build(vid) }.isSuccess
            }
            b.btnLaunch.isEnabled = true
            if (!ok) {
                b.tvStatus.text = "启动参数生成失败，请检查版本文件是否完整"
                return@launch
            }
            b.tvStatus.text = "正在启动 $vid …"
            startActivity(
                Intent(requireContext(), GameActivity::class.java)
                    .putExtra(GameActivity.EXTRA_VERSION, vid)
            )
        }
    }

    override fun onDestroyView() {
        _b = null
        super.onDestroyView()
    }
}

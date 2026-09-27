package com.ncl.launcher.ui

import android.os.Bundle
import android.view.SurfaceHolder
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.ncl.launcher.databinding.ActivityGameBinding
import com.ncl.launcher.gl.GlBridge
import com.ncl.launcher.mc.McLauncher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.InputStreamReader

/** 游戏窗口：绑定 Surface -> 起 JVM -> 实时输出日志 */
class GameActivity : AppCompatActivity(), SurfaceHolder.Callback {

    companion object {
        const val EXTRA_VERSION = "version"
    }

    private lateinit var b: ActivityGameBinding
    private var versionId: String = ""
    private var process: Process? = null
    private var readerJob: Job? = null
    private var ready = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        versionId = intent.getStringExtra(EXTRA_VERSION) ?: ""
        b = ActivityGameBinding.inflate(layoutInflater)
        setContentView(b.root)

        b.surface.holder.addCallback(this)
        b.btnStop.setOnClickListener { finish() }

        // 点一下画面切换日志面板
        b.surface.setOnClickListener {
            b.scrollLog.visibility =
                if (b.scrollLog.visibility == View.VISIBLE) View.GONE else View.VISIBLE
        }
    }

    override fun surfaceCreated(holder: SurfaceHolder) {
        runCatching { GlBridge.setSurface(holder.surface) }
        ready = true
        startGame()
    }

    override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
        runCatching { GlBridge.setWindowSize(width, height) }
    }

    override fun surfaceDestroyed(holder: SurfaceHolder) {
        ready = false
        runCatching { GlBridge.clearSurface() }
    }

    private fun startGame() {
        if (versionId.isBlank()) {
            log("没有指定版本，退出")
            return
        }
        if (process != null) return // 转屏会重建 Surface，不要重复起进程
        lifecycleScope.launch {
            val spec = withContext(Dispatchers.IO) {
                runCatching { McLauncher.build(versionId, surfaceWidth(), surfaceHeight()) }
            }.getOrElse { e ->
                log("启动参数生成失败：${e.message}")
                return@launch
            }

            log("启动 $versionId …")
            log(spec.argv.joinToString(" ").take(600))
            process = withContext(Dispatchers.IO) {
                runCatching {
                    ProcessBuilder(spec.argv).apply {
                        directory(spec.workDir)
                        environment().putAll(spec.env)
                        redirectErrorStream(true)
                    }.start()
                }.getOrElse { e ->
                    log("启动进程失败：${e.message}")
                    null
                }
            } ?: return@launch

            readerJob = lifecycleScope.launch(Dispatchers.IO) {
                process?.inputStream?.let { stream ->
                    BufferedReader(InputStreamReader(stream)).use { reader ->
                        while (true) {
                            val line = reader.readLine() ?: break
                            log(line)
                        }
                    }
                }
            }
        }
    }

    private fun surfaceWidth(): Int = runCatching { b.surface.width }.getOrDefault(0)
    private fun surfaceHeight(): Int = runCatching { b.surface.height }.getOrDefault(0)

    private fun log(line: String) {
        runOnUiThread {
            val tv = b.tvLog
            tv.append("$line\n")
            val text = tv.text.toString()
            if (text.length > 20000) tv.text = text.takeLast(10000)
            b.scrollLog.post { b.scrollLog.fullScroll(View.FOCUS_DOWN) }
        }
    }

    override fun onDestroy() {
        readerJob?.cancel()
        runCatching { process?.destroy() }
        super.onDestroy()
    }
}

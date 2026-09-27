package com.ncl.launcher.ui

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.ncl.launcher.R
import com.ncl.launcher.auth.Account
import com.ncl.launcher.auth.AccountStore
import com.ncl.launcher.auth.AuthException
import com.ncl.launcher.auth.Microsoft
import com.ncl.launcher.auth.Yggdrasil
import com.ncl.launcher.databinding.ActivityAccountBinding
import kotlinx.coroutines.launch

/** 账户：Microsoft 设备码登录 / 外置登录 / 离线登录 */
class AccountActivity : AppCompatActivity() {

    private lateinit var b: ActivityAccountBinding
    private lateinit var adapter: SimpleAdapter
    private var lastUri: String = "https://www.microsoft.com/link"

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        b = ActivityAccountBinding.inflate(layoutInflater)
        setContentView(b.root)

        adapter = SimpleAdapter(
            onClick = { item ->
                val acc = item.payload as? Account ?: return@SimpleAdapter
                AccountStore.setActive(acc.name)
                toast("已切换到 ${acc.name}")
                refresh()
            },
            onLongClick = { item ->
                val acc = item.payload as? Account ?: return@SimpleAdapter false
                android.app.AlertDialog.Builder(this)
                    .setTitle("删除账户？")
                    .setMessage("${acc.name}（${acc.displayType}）")
                    .setNegativeButton("取消", null)
                    .setPositiveButton("删除") { _, _ -> AccountStore.remove(acc); refresh() }
                    .show()
                true
            }
        )
        b.rvAccounts.layoutManager = LinearLayoutManager(this)
        b.rvAccounts.adapter = adapter

        b.btnMsa.setOnClickListener { startMicrosoft() }
        b.btnOpenBrowser.setOnClickListener {
            startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(lastUri)))
        }
        b.btnYgg.setOnClickListener { yggLogin() }
        b.btnOffline.setOnClickListener { offlineLogin() }

        refresh()
    }

    private fun startMicrosoft() {
        b.btnMsa.isEnabled = false
        b.tvCode.text = "正在申请设备码…"
        lifecycleScope.launch {
            runCatching {
                val dc = Microsoft.begin()
                lastUri = dc.verificationUri
                b.tvCode.text =
                    "1) 打开 ${dc.verificationUri}\n2) 输入验证码：${dc.userCode}\n\n等待你完成验证…"
                runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(dc.verificationUri))) }
                val token = Microsoft.poll(dc) { msg -> b.tvCode.append("\n$msg") }
                val acc = Microsoft.finish(token)
                AccountStore.add(acc)
                b.tvCode.text = "登录成功：${acc.name}"
                toast("已登录 ${acc.name}")
                refresh()
            }.onFailure { e ->
                b.tvCode.text = when (e) {
                    is AuthException -> "登录失败（${e.code}）：${e.message}"
                    else -> "登录失败：${e.message}"
                }
            }
            b.btnMsa.isEnabled = true
        }
    }

    private fun yggLogin() {
        val server = b.etYggServer.text.toString().trim()
        val user = b.etYggUser.text.toString().trim()
        val pass = b.etYggPass.text.toString()
        if (server.isBlank() || user.isBlank() || pass.isBlank()) {
            toast("请填写外置登录服务器、账号和密码")
            return
        }
        lifecycleScope.launch {
            runCatching { Yggdrasil.login(server, user, pass) }
                .onSuccess { acc ->
                    AccountStore.add(acc)
                    toast("已登录 ${acc.name}")
                    refresh()
                }
                .onFailure { toast("外置登录失败：${it.message}") }
        }
    }

    private fun offlineLogin() {
        val name = b.etOffline.text.toString().trim()
        if (name.isBlank()) {
            toast("请输入游戏名")
            return
        }
        val acc = Account(
            name = name,
            uuid = AccountStore.offlineUuid(name),
            accessToken = "-",
            userType = "legacy",
            type = "offline"
        )
        AccountStore.add(acc)
        toast("已使用离线账户 $name")
        refresh()
    }

    private fun refresh() {
        val list = AccountStore.list()
        adapter.submitList(list.map { acc ->
            RowItem(
                title = acc.name,
                sub = acc.displayType,
                tail = if (acc.name == AccountStore.active().name) "当前" else "",
                payload = acc
            )
        })
    }
}

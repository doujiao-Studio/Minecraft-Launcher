package com.ncl.launcher.ui

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.view.View
import android.widget.EditText
import android.widget.LinearLayout
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.ncl.launcher.R
import com.ncl.launcher.data.ConfigStore
import com.ncl.launcher.data.Paths
import com.ncl.launcher.data.ServerEntry
import com.ncl.launcher.data.ServerPing
import com.ncl.launcher.data.ServerStore
import com.ncl.launcher.databinding.FragmentServersBinding
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** 服务器列表：添加 / 查状态 / 一键进服（复制地址 + 启动匹配版本） */
class ServersFragment : Fragment(R.layout.fragment_servers) {

    private var _b: FragmentServersBinding? = null
    private val b get() = _b!!

    private lateinit var adapter: SimpleAdapter
    private val statuses = HashMap<String, ServerPing.Status>()

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        _b = FragmentServersBinding.bind(view)

        adapter = SimpleAdapter(
            onClick = { item ->
                val e = item.payload as? ServerEntry ?: return@SimpleAdapter
                val cm = requireContext().getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                cm.setPrimaryClip(ClipData.newPlainText("address", e.address))
                toast("已复制 ${e.address}，进服后粘贴即可；正在启动游戏…")
                val vid = ConfigStore.load().lastVersion.ifBlank { Paths.installedVersions().firstOrNull() ?: "" }
                if (vid.isNotBlank() && Paths.clientJar(vid).exists()) {
                    startActivity(
                        Intent(requireContext(), GameActivity::class.java)
                            .putExtra(GameActivity.EXTRA_VERSION, vid)
                    )
                }
            },
            onLongClick = { item ->
                val e = item.payload as? ServerEntry ?: return@SimpleAdapter false
                android.app.AlertDialog.Builder(requireContext())
                    .setTitle("删除服务器？")
                    .setMessage(e.name)
                    .setNegativeButton("取消", null)
                    .setPositiveButton("删除") { _, _ -> ServerStore.remove(e); refresh() }
                    .show()
                true
            }
        )
        b.rv.layoutManager = LinearLayoutManager(requireContext())
        b.rv.adapter = adapter

        b.btnAdd.setOnClickListener { showAddDialog() }
        b.btnQuery.setOnClickListener { queryAll() }
        b.btnJoin.setOnClickListener {
            val first = ServerStore.list().firstOrNull()
            if (first == null) toast("还没有服务器")
            else adapter.select(adapter.currentList.firstOrNull())
        }

        refresh()
    }

    private fun showAddDialog() {
        val ctx = requireContext()
        val layout = LinearLayout(ctx).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 20, 40, 0)
        }
        val etName = EditText(ctx).apply { hint = "名称" }
        val etAddr = EditText(ctx).apply { hint = "地址，如 mc.example.com:25565" }
        layout.addView(etName)
        layout.addView(etAddr)
        android.app.AlertDialog.Builder(ctx)
            .setTitle("添加服务器")
            .setView(layout)
            .setNegativeButton("取消", null)
            .setPositiveButton("添加") { _, _ ->
                val name = etName.text.toString().trim().ifBlank { "服务器" }
                val addr = etAddr.text.toString().trim()
                if (addr.isBlank()) {
                    toast("地址不能为空")
                    return@setPositiveButton
                }
                ServerStore.add(ServerEntry(name, addr, ""))
                refresh()
            }
            .show()
    }

    private fun refresh() {
        val list = ServerStore.list()
        adapter.submitList(list.map { e ->
            val st = statuses[e.address]
            RowItem(
                title = e.name,
                sub = e.address,
                tail = when {
                    st == null -> ""
                    !st.online -> "离线"
                    st.players.isBlank() -> "在线"
                    else -> "在线 ${st.players}"
                },
                payload = e
            )
        })
    }

    private fun queryAll() {
        lifecycleScope.launch {
            val list = ServerStore.list()
            val res = withContext(Dispatchers.IO) {
                list.associate { e ->
                    val (host, port) = splitAddress(e.address)
                    e.address to ServerPing.query(host, port)
                }
            }
            statuses.clear()
            statuses.putAll(res)
            refresh()
            toast("已刷新 ${res.size} 个服务器")
        }
    }

    private fun splitAddress(addr: String): Pair<String, Int> {
        val i = addr.lastIndexOf(':')
        return if (i > 0) addr.substring(0, i) to (addr.substring(i + 1).toIntOrNull() ?: 25565)
        else addr to 25565
    }

    override fun onDestroyView() {
        _b = null
        super.onDestroyView()
    }
}

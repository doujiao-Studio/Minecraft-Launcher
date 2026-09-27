package com.ncl.launcher.auth

import com.google.gson.Gson
import com.ncl.launcher.data.Paths
import java.io.File
import java.util.UUID

/**
 * 账户存储。字段与桌面版 accounts.json 对齐：
 *   offline   -> userType "legacy"
 *   yggdrasil -> userType "mojang"
 *   microsoft -> userType "msa"
 */
data class Account(
    var name: String = "",
    var uuid: String = "",
    var accessToken: String = "",
    var userType: String = "legacy",
    var type: String = "offline",
    var refreshToken: String = ""
) {
    val displayType: String
        get() = when (type) {
            "microsoft" -> "正版 (Microsoft)"
            "yggdrasil" -> "外置登录"
            else -> "离线"
        }
}

private data class AccountFile(
    var accounts: MutableList<Account> = mutableListOf(),
    var active: String = ""
)

object AccountStore {

    private val gson = Gson()
    private var cache: AccountFile? = null

    private fun file(): File = Paths.accountsFile()

    private fun load(): AccountFile {
        cache?.let { return it }
        val f = file()
        val af = if (f.exists()) {
            runCatching { gson.fromJson(f.readText(), AccountFile::class.java) }.getOrNull() ?: AccountFile()
        } else AccountFile()
        cache = af
        return af
    }

    private fun save(af: AccountFile = load()) {
        cache = af
        runCatching {
            file().parentFile?.mkdirs()
            file().writeText(gson.toJson(af))
        }
    }

    fun list(): List<Account> = load().accounts

    fun add(acc: Account): Account {
        val af = load()
        af.accounts.removeAll { it.name == acc.name && it.type == acc.type }
        af.accounts.add(0, acc)
        af.active = acc.name
        save(af)
        return acc
    }

    fun remove(acc: Account) {
        val af = load()
        af.accounts.removeAll { it.name == acc.name && it.type == acc.type }
        if (af.active == acc.name) af.active = af.accounts.firstOrNull()?.name ?: ""
        save(af)
    }

    fun setActive(name: String) {
        val af = load()
        af.active = name
        save(af)
    }

    /** 当前账户；没有任何账户时返回一个默认离线账户（不落盘） */
    fun active(): Account {
        val af = load()
        val byName = af.accounts.firstOrNull { it.name == af.active }
        if (byName != null) return byName
        val first = af.accounts.firstOrNull()
        if (first != null) {
            af.active = first.name
            save(af)
            return first
        }
        return Account(name = "Player", uuid = offlineUuid("Player"), userType = "legacy", type = "offline")
    }

    fun logout() {
        val af = load()
        af.active = ""
        save(af)
    }

    /** 离线 UUID（与 Mojang 算法一致的 version 3 / OFFLINE_PLAYER 命名空间） */
    fun offlineUuid(name: String): String =
        UUID.nameUUIDFromBytes("OfflinePlayer:$name".toByteArray(Charsets.UTF_8)).toString()
}

package com.ncl.launcher.auth

import com.ncl.launcher.net.Http
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import java.util.UUID

/** 外置登录（Yggdrasil），兼容统一通行证 / Blessing Skin 等第三方验证服务器 */
object Yggdrasil {

    suspend fun login(server: String, username: String, password: String): Account =
        withContext(Dispatchers.IO) {
            val base = normalize(server)
            val payload = JSONObject().apply {
                put("agent", JSONObject().apply {
                    put("name", "Minecraft")
                    put("version", 1)
                })
                put("username", username)
                put("password", password)
                put("clientToken", UUID.randomUUID().toString())
                put("requestUser", true)
            }
            val res = post("$base/authserver/authenticate", payload)
            val token = res.optString("accessToken")
            if (token.isBlank()) throw AuthException("ygg", res.optString("errorMessage", "外置登录失败"))

            val profiles = res.optJSONArray("availableProfiles")
            val selected = res.optJSONObject("selectedProfile")
            val profile = selected ?: profiles?.optJSONObject(0)
            val name = profile?.optString("name") ?: username
            val uuid = profile?.optString("id") ?: AccountStore.offlineUuid(username)

            Account(
                name = name,
                uuid = uuid,
                accessToken = token,
                userType = "mojang",
                type = "yggdrasil",
                refreshToken = res.optString("clientToken")
            )
        }

    /** 补上协议后缀，用户只填域名也能用 */
    fun normalize(url: String): String {
        var s = url.trim().trimEnd('/')
        if (s.isBlank()) return ""
        if (!s.startsWith("http://") && !s.startsWith("https://")) s = "https://$s"
        return s
    }

    private fun post(url: String, json: JSONObject): JSONObject {
        val mt = "application/json; charset=utf-8".toMediaType()
        val req = Request.Builder().url(url).post(json.toString().toRequestBody(mt)).build()
        Http.jsonClient.newCall(req).execute().use { resp ->
            val txt = resp.body?.string() ?: ""
            if (!resp.isSuccessful) throw AuthException("ygg_${resp.code}", "$url -> ${resp.code} ${txt.take(200)}")
            return JSONObject(txt)
        }
    }
}

package com.ncl.launcher.auth

import com.ncl.launcher.net.Http
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext
import okhttp3.FormBody
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

class AuthException(val code: String, message: String) : Exception(message)

/** 设备码登录第一步的结果 */
data class DeviceCode(
    val deviceCode: String,
    val userCode: String,
    val verificationUri: String,
    val interval: Int,
    val expiresIn: Int,
    val clientId: String
)

/**
 * Microsoft 设备码登录全链路（与桌面版 mcl/accounts.py 完全一致）：
 *   devicecode -> XBL(RPS) -> XSTS(rp://api.minecraftservices.com/) -> MC login -> profile
 *
 * 三个历史坑，这里直接写对：
 *   1. XBL 用 AuthMethod=RPS + RpsTicket=d=<token>
 *   2. XSTS 的 RelyingParty 必须是 rp://api.minecraftservices.com/（写成 https:// 会被拒）
 *   3. MC 登录端点与字段名必须成对：login_with_xbox→identityToken，launcher/login→xtoken
 */
object Microsoft {

    private const val CLIENT_ID_DEFAULT = "c52aed44-3b4d-4215-99c5-824033d2bc0f"
    private const val CLIENT_ID_FALLBACK = "69324f03-7b0c-48a3-a995-584127fba992"
    private const val TENANT = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
    private const val SCOPE = "XboxLive.signin offline_access"
    private const val XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
    private const val XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
    private const val XSTS_RP = "rp://api.minecraftservices.com/"
    private const val PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"

    private val CLIENT_IDS = listOf(CLIENT_ID_DEFAULT, CLIENT_ID_FALLBACK)

    suspend fun begin(): DeviceCode = withContext(Dispatchers.IO) {
        var last: Exception? = null
        for (cid in CLIENT_IDS) {
            try {
                val body = FormBody.Builder()
                    .add("client_id", cid)
                    .add("scope", SCOPE)
                    .build()
                val req = Request.Builder().url("$TENANT/devicecode").post(body).build()
                Http.jsonClient.newCall(req).execute().use { resp ->
                    val txt = resp.body?.string() ?: ""
                    if (!resp.isSuccessful) throw AuthException("http_${resp.code}", txt)
                    val o = JSONObject(txt)
                    return@withContext DeviceCode(
                        deviceCode = o.getString("device_code"),
                        userCode = o.getString("user_code"),
                        verificationUri = o.optString("verification_uri", "https://www.microsoft.com/link"),
                        interval = o.optInt("interval", 5),
                        expiresIn = o.optInt("expires_in", 900),
                        clientId = cid
                    )
                }
            } catch (e: Exception) {
                last = e
            }
        }
        throw AuthException("devicecode", last?.message ?: "无法获取设备码")
    }

    /** 轮询设备码直到用户在浏览器完成验证，返回微软 token JSON（access_token / refresh_token） */
    suspend fun poll(dc: DeviceCode, onTick: suspend (String) -> Unit = {}): JSONObject =
        withContext(Dispatchers.IO) {
            val deadline = System.currentTimeMillis() + dc.expiresIn * 1000L
            while (System.currentTimeMillis() < deadline) {
                onTick("等待浏览器中完成验证…")
                val body = FormBody.Builder()
                    .add("client_id", dc.clientId)
                    .add("grant_type", "urn:ietf:params:oauth:grant-type:device_code")
                    .add("device_code", dc.deviceCode)
                    .build()
                val req = Request.Builder().url("$TENANT/token").post(body).build()
                Http.jsonClient.newCall(req).execute().use { resp ->
                    val txt = resp.body?.string() ?: ""
                    val o = if (txt.isBlank()) JSONObject() else JSONObject(txt)
                    if (resp.isSuccessful) return@withContext o
                    val err = o.optString("error")
                    when (err) {
                        "authorization_pending", "slow_down" -> delay((dc.interval + 1) * 1000L)
                        else -> throw AuthException(err.ifBlank { "http_${resp.code}" }, friendly(err, txt))
                    }
                }
            }
            throw AuthException("expired", "设备码已过期，请重新点击登录")
        }

    /** 拿到微软 token 后走完 XBL -> XSTS -> MC -> profile */
    suspend fun finish(msToken: JSONObject): Account = withContext(Dispatchers.IO) {
        val access = msToken.optString("access_token")
        val refresh = msToken.optString("refresh_token")
        if (access.isBlank()) throw AuthException("no_token", "微软未返回访问令牌")

        val (xbl, uhs) = xblToken(access)
        val (xsts, _) = xstsToken(xbl)
        val mcToken = mcLogin("XBL3.0 x=$uhs;$xsts")
        val (name, uuid) = profile(mcToken)
        Account(
            name = name,
            uuid = uuid,
            accessToken = mcToken,
            userType = "msa",
            type = "microsoft",
            refreshToken = refresh
        )
    }

    /** 用 refresh_token 静默续期 */
    suspend fun refresh(acc: Account): Account = withContext(Dispatchers.IO) {
        val cid = CLIENT_IDS.first()
        val body = FormBody.Builder()
            .add("client_id", cid)
            .add("grant_type", "refresh_token")
            .add("refresh_token", acc.refreshToken)
            .add("scope", SCOPE)
            .build()
        val req = Request.Builder().url("$TENANT/token").post(body).build()
        Http.jsonClient.newCall(req).execute().use { resp ->
            val txt = resp.body?.string() ?: ""
            if (!resp.isSuccessful) throw AuthException("refresh_${resp.code}", "令牌已失效，请重新登录")
            val o = JSONObject(txt)
            o.put("refresh_token", o.optString("refresh_token").ifBlank { acc.refreshToken })
            return@withContext finish(o)
        }
    }

    private fun xblToken(msAccessToken: String): Pair<String, String> {
        val json = JSONObject().apply {
            put("Properties", JSONObject().apply {
                put("AuthMethod", "RPS")
                put("SiteName", "user.auth.xboxlive.com")
                put("RpsTicket", "d=$msAccessToken")
            })
            put("RelyingParty", "http://auth.xboxlive.com")
            put("TokenType", "JWT")
        }
        val out = postJson(XBL_URL, json)
        val token = out.optString("Token")
        if (token.isBlank()) throw AuthException("xbl", "Xbox Live 未返回令牌")
        val uhs = out.optJSONObject("DisplayClaims")
            ?.optJSONArray("xui")?.optJSONObject(0)?.optString("uhs") ?: ""
        return Pair(token, uhs)
    }

    private fun xstsToken(xbl: String): Pair<String, String> {
        val json = JSONObject().apply {
            put("Properties", JSONObject().apply {
                put("SandboxId", "RETAIL")
                put("UserTokens", org.json.JSONArray().put(xbl))
            })
            put("RelyingParty", XSTS_RP)
            put("TokenType", "JWT")
        }
        val out = postJson(XSTS_URL, json, mapOf("x-xbl-contract-version" to "1"))
        val token = out.optString("Token")
        if (token.isBlank()) throw AuthException("xsts", xstsError(out))
        val uhs = out.optJSONObject("DisplayClaims")
            ?.optJSONArray("xui")?.optJSONObject(0)?.optString("uhs") ?: ""
        return Pair(token, uhs)
    }

    private fun xstsError(o: JSONObject): String {
        if (o.optString("XErr", "") == "2148916233") return "该微软账号没有 Xbox 档案，请先在 xbox.com 创建"
        if (o.optString("XErr", "") == "2148916238") return "账号未满 18 岁，需加入家庭组才能登录"
        return "XSTS 授权失败：${o.optString("Message", o.toString().take(120))}"
    }

    private fun mcLogin(identity: String): String {
        val pairs = listOf(
            "https://api.minecraftservices.com/authentication/login_with_xbox" to "identityToken",
            "https://api.minecraftservices.com/launcher/login" to "xtoken"
        )
        var last: Exception? = null
        for ((url, key) in pairs) {
            try {
                val out = postJson(url, JSONObject().put(key, identity))
                val token = out.optString("access_token")
                if (token.isNotBlank()) return token
                last = AuthException("mc_login", "Minecraft 服务未返回令牌")
            } catch (e: AuthException) {
                last = e
                val retryable = e.code.startsWith("http_") &&
                    e.code.removePrefix("http_").toIntOrNull() in listOf(400, 404, 405, 410)
                if (!retryable) throw e
            }
        }
        throw last ?: AuthException("mc_login", "Minecraft 登录失败")
    }

    private fun profile(mcToken: String): Pair<String, String> {
        val req = Request.Builder()
            .url(PROFILE_URL)
            .header("Authorization", "Bearer $mcToken")
            .get().build()
        Http.jsonClient.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) throw AuthException("profile_${resp.code}", "无法读取游戏档案")
            val o = JSONObject(resp.body?.string() ?: "{}")
            if (!o.has("name") || !o.has("id"))
                throw AuthException("no_profile", "该微软账号没有购买 Minecraft Java 版")
            return Pair(o.getString("name"), o.getString("id"))
        }
    }

    private fun postJson(url: String, json: JSONObject, headers: Map<String, String> = emptyMap()): JSONObject {
        val mt = "application/json; charset=utf-8".toMediaType()
        val req = Request.Builder()
            .url(url)
            .post(json.toString().toRequestBody(mt))
            .apply { headers.forEach { (k, v) -> header(k, v) } }
            .build()
        Http.jsonClient.newCall(req).execute().use { resp ->
            val txt = resp.body?.string() ?: ""
            if (!resp.isSuccessful) throw AuthException("http_${resp.code}", "$url -> ${resp.code} ${txt.take(200)}")
            return if (txt.isBlank()) JSONObject() else JSONObject(txt)
        }
    }

    private fun friendly(err: String, raw: String): String = when (err) {
        "expired_token" -> "设备码已超时，请重新点击登录"
        "access_denied" -> "你在浏览器里取消了授权"
        else -> raw.take(160)
    }
}

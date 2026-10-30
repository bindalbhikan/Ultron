package com.bindal.ultronphone

import org.json.JSONArray
import org.json.JSONObject
import java.net.CookieHandler
import java.net.CookieManager
import java.net.CookiePolicy
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

/**
 * Myntra's buyer side for a list of style ids, as the bot's spider does it
 * (src/ultron/workings/myntra_zero_td/spider.py): the home page first for the session cookie (the
 * product API answers 401 without it), then /gateway/v2/product/<id> per style, a few at a time.
 * Each answer is the API's "style" object cut down to what the bot reads (id, mrp, sellers, sizes),
 * or "NOT FOUND" / "HTTP <code>" / an error text.
 */
class MyntraLookup(private val threads: Int = 6, private val onProgress: (Int, Int) -> Unit = { _, _ -> }) {

    private val cookies = CookieManager(null, CookiePolicy.ACCEPT_ALL)
    @Volatile private var warmedAt = 0L

    fun run(ids: List<Long>): Map<String, Any> {
        CookieHandler.setDefault(cookies)
        home()
        val out = java.util.concurrent.ConcurrentHashMap<String, Any>()
        val done = AtomicInteger()
        val pool = Executors.newFixedThreadPool(threads)
        for (id in ids) {
            pool.execute {
                out[id.toString()] = try { style(id) } catch (e: Exception) { "${e.javaClass.simpleName}: ${e.message?.take(80)}" }
                val n = done.incrementAndGet()
                if (n % 100 == 0 || n == ids.size) onProgress(n, ids.size)
            }
        }
        pool.shutdown()
        pool.awaitTermination(2, TimeUnit.HOURS)
        return out
    }

    @Synchronized
    private fun home() {
        if (System.currentTimeMillis() - warmedAt < 20_000) return      // another thread just did it
        val c = open(HOME)
        try { c.inputStream.use { it.readBytes() } } catch (_: Exception) { } finally { c.disconnect() }
        warmedAt = System.currentTimeMillis()
    }

    private fun style(id: Long): Any {
        var again = false
        for (attempt in 1..4) {
            val c = open(API + id).apply {
                setRequestProperty("x-meta-app", "channel=web")
                setRequestProperty("x-myntraweb", "Yes")
                setRequestProperty("Accept", "application/json")
            }
            try {
                val code = c.responseCode
                when {
                    code == 200 -> {
                        val text = c.inputStream.bufferedReader().use { it.readText() }
                        return trim(JSONObject(text).getJSONObject("style"))
                    }
                    code == 404 -> return "NOT FOUND"
                    code == 401 && !again -> { again = true; warmedAt = 0; home() }
                    code == 429 || code >= 500 -> Thread.sleep(1500L * attempt)
                    else -> return "HTTP $code"
                }
            } finally {
                c.disconnect()
            }
        }
        return "no answer"
    }

    /** Only what the bot's check() reads: id, mrp, sellers' names, sizes with their sellers' stock and prices. */
    private fun trim(s: JSONObject): JSONObject {
        val sellers = JSONArray()
        s.optJSONArray("sellers")?.let { arr ->
            for (i in 0 until arr.length()) {
                val x = arr.optJSONObject(i) ?: continue
                sellers.put(JSONObject().put("displayName", x.optString("displayName"))
                    .put("sellerName", x.optString("sellerName")))
            }
        }
        val sizes = JSONArray()
        s.optJSONArray("sizes")?.let { arr ->
            for (i in 0 until arr.length()) {
                val z = arr.optJSONObject(i) ?: continue
                val data = JSONArray()
                z.optJSONArray("sizeSellerData")?.let { sd ->
                    for (j in 0 until sd.length()) {
                        val d = sd.optJSONObject(j) ?: continue
                        data.put(JSONObject().put("availableCount", d.optInt("availableCount"))
                            .put("mrp", d.opt("mrp")).put("discountedPrice", d.opt("discountedPrice")))
                    }
                }
                sizes.put(JSONObject().put("label", z.optString("label")).put("available", z.optBoolean("available"))
                    .put("sizeSellerData", data))
            }
        }
        return JSONObject().put("id", s.opt("id")).put("mrp", s.opt("mrp")).put("sellers", sellers).put("sizes", sizes)
    }

    private fun open(url: String) = (URL(url).openConnection() as HttpURLConnection).apply {
        connectTimeout = 20_000
        readTimeout = 30_000
        instanceFollowRedirects = true
        setRequestProperty("User-Agent", UA)
        setRequestProperty("Accept-Language", "en-IN,en;q=0.9")
    }

    companion object {
        const val HOME = "https://www.myntra.com/"
        const val API = "https://www.myntra.com/gateway/v2/product/"
        const val UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) " +
            "Chrome/141.0.0.0 Mobile Safari/537.36"
    }
}

package com.bindal.ultronphone

import android.content.Context
import android.util.Base64
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.pdmodel.PDDocument
import com.tom_roush.pdfbox.text.PDFTextStripper
import java.net.HttpURLConnection
import java.net.URL

/**
 * The POD behind a courier SMS link (Delhivery summary / final POD, Shadowfax shipment details,
 * Xpressbees proforma), fetched by the phone the moment the SMS is sent on: the links expire
 * (Shadowfax answers 410 after a while). The Apps Script gets the PDF and its text, saves the PDF in
 * Drive and reads the AWBs and portals from the text.
 */
object Pod {
    private val COURIERS = Regex("DLHVRY|SFX|XPBEES|EKART", RegexOption.IGNORE_CASE)
    private val LINK = Regex("https?://[^\\s]+")
    private const val MAX_BYTES = 15 * 1024 * 1024

    class Result(val pdfBase64: String = "", val text: String = "", val error: String = "")

    /** null when the SMS is not a courier's or has no link. */
    fun fetch(context: Context, from: String, body: String): Result? {
        if (!COURIERS.containsMatchIn(from)) return null
        val link = LINK.find(body)?.value?.trimEnd('.', ',', ')') ?: return null
        return try {
            val bytes = download(link)
            if (bytes.size < 5 || String(bytes, 0, 5, Charsets.ISO_8859_1) != "%PDF-") {
                return Result(error = "link is not a PDF")
            }
            PDFBoxResourceLoader.init(context.applicationContext)
            val text = PDDocument.load(bytes).use { PDFTextStripper().getText(it) }
            Result(Base64.encodeToString(bytes, Base64.NO_WRAP), text)
        } catch (e: Exception) {
            Result(error = (e.message ?: e.javaClass.simpleName).take(80))
        }
    }

    private fun download(link: String): ByteArray {
        var url = URL(link)
        repeat(6) {                     // short link -> courier page -> storage: followed by hand across hosts
            val conn = (url.openConnection() as HttpURLConnection).apply {
                instanceFollowRedirects = false
                connectTimeout = 20_000
                readTimeout = 40_000
                setRequestProperty("User-Agent", "Mozilla/5.0 (Linux; Android) UltronPhone")
            }
            try {
                val code = conn.responseCode
                if (code in 300..399) {
                    url = URL(url, conn.getHeaderField("Location") ?: throw IllegalStateException("redirect without a target"))
                    return@repeat
                }
                if (code != 200) throw IllegalStateException("HTTP $code")
                return conn.inputStream.use { input ->
                    val out = java.io.ByteArrayOutputStream()
                    val buf = ByteArray(64 * 1024)
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        out.write(buf, 0, n)
                        if (out.size() > MAX_BYTES) throw IllegalStateException("PDF too large")
                    }
                    out.toByteArray()
                }
            } finally {
                conn.disconnect()
            }
        }
        throw IllegalStateException("too many redirects")
    }
}

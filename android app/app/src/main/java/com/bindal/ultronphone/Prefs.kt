package com.bindal.ultronphone

import android.content.Context
import android.content.SharedPreferences
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** Settings and the activity log, in one private SharedPreferences file. */
object Prefs {
    private const val FILE = "ultron_phone"
    private const val KEY_URL = "url"
    private const val KEY_SECRET = "secret"
    private const val KEY_FILTER = "filter"
    private const val KEY_WORKER = "worker"
    private const val KEY_TOKEN = "token"
    private const val KEY_AGENT = "agent"
    private const val KEY_LAST_POLL = "last_poll"
    private const val KEY_LAST_JOB = "last_job"
    private const val KEY_LOG = "log"
    private const val MAX_LOG_LINES = 40

    private fun sp(context: Context): SharedPreferences =
        context.applicationContext.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    private fun str(context: Context, key: String) = sp(context).getString(key, "") ?: ""

    // SMS to Sheet (Apps Script web app)
    fun getUrl(context: Context) = str(context, KEY_URL)
    fun getSecret(context: Context) = str(context, KEY_SECRET)
    fun getFilter(context: Context) = str(context, KEY_FILTER)

    // Agent mode (the Telegram worker's /api/phone routes)
    fun getWorker(context: Context) = str(context, KEY_WORKER).trimEnd('/')
    fun getToken(context: Context) = str(context, KEY_TOKEN)
    fun agentOn(context: Context) = sp(context).getBoolean(KEY_AGENT, false)
    fun setAgentOn(context: Context, on: Boolean) = sp(context).edit().putBoolean(KEY_AGENT, on).apply()

    fun save(context: Context, url: String, secret: String, filter: String, worker: String, token: String) {
        sp(context).edit()
            .putString(KEY_URL, url.trim())
            .putString(KEY_SECRET, secret.trim())
            .putString(KEY_FILTER, filter.trim())
            .putString(KEY_WORKER, worker.trim())
            .putString(KEY_TOKEN, token.trim())
            .apply()
    }

    fun markPoll(context: Context) = sp(context).edit().putLong(KEY_LAST_POLL, System.currentTimeMillis()).apply()
    fun lastPoll(context: Context) = sp(context).getLong(KEY_LAST_POLL, 0)
    fun setLastJob(context: Context, text: String) = sp(context).edit().putString(KEY_LAST_JOB, text).apply()
    fun lastJob(context: Context) = str(context, KEY_LAST_JOB)

    /** Comma-separated sender keywords ("MYNTRA, DELHIVERY"); empty = every SMS goes to the sheet. */
    fun senderAllowed(context: Context, from: String): Boolean {
        val keywords = getFilter(context).split(",").map { it.trim().lowercase(Locale.ROOT) }.filter { it.isNotEmpty() }
        if (keywords.isEmpty()) return true
        val sender = from.lowercase(Locale.ROOT)
        return keywords.any { sender.contains(it) }
    }

    @Synchronized
    fun addLog(context: Context, line: String) {
        val time = SimpleDateFormat("dd-MMM HH:mm:ss", Locale.ENGLISH).format(Date())
        val lines = (listOf("$time  $line") + str(context, KEY_LOG).lines().filter { it.isNotBlank() })
            .take(MAX_LOG_LINES)
        sp(context).edit().putString(KEY_LOG, lines.joinToString("\n")).apply()
    }

    fun getLog(context: Context) = str(context, KEY_LOG)
}

package com.ultron.ultron_app.sms

import android.content.Context
import android.content.SharedPreferences
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.UUID

/**
 * "SMS only" mode settings and its activity log, in one private SharedPreferences file. No account and
 * no secret: the phone sends its random id and the name its person typed; the worker holds the sheet's key.
 */
object SmsPrefs {
    private const val FILE = "ultron_sms"
    private const val KEY_ON = "on"
    private const val KEY_NAME = "name"
    private const val KEY_ID = "phone_id"
    private const val KEY_SIM = "sim"
    private const val KEY_WORKER = "worker"
    private const val KEY_SENT = "sent"
    private const val KEY_LAST = "last_sent"
    private const val KEY_LOG = "log"
    private const val MAX_LOG_LINES = 60

    private fun sp(context: Context): SharedPreferences =
        context.applicationContext.getSharedPreferences(FILE, Context.MODE_PRIVATE)

    private fun str(context: Context, key: String) = sp(context).getString(key, "") ?: ""

    fun isOn(context: Context) = sp(context).getBoolean(KEY_ON, false)
    fun name(context: Context) = str(context, KEY_NAME)
    fun worker(context: Context) = str(context, KEY_WORKER).trimEnd('/')

    /** "" = both SIMs, else "SIM 1" / "SIM 2": only SMS that came in on that SIM go to the sheet. */
    fun sim(context: Context) = str(context, KEY_SIM)

    /** An SMS on [sim] passes the SIM choice; one whose SIM is unknown passes only when both SIMs are chosen. */
    fun simAllowed(context: Context, sim: String) = sim(context).let { it.isEmpty() || it == sim }

    /** The phone's random id, made once and kept: the worker and the control panel know the phone by it. */
    @Synchronized
    fun phoneId(context: Context): String {
        val saved = str(context, KEY_ID)
        if (saved.isNotEmpty()) return saved
        val made = UUID.randomUUID().toString()
        sp(context).edit().putString(KEY_ID, made).apply()
        return made
    }

    fun turnOn(context: Context, name: String, sim: String, worker: String) {
        sp(context).edit()
            .putBoolean(KEY_ON, true)
            .putString(KEY_NAME, name.replace(Regex("\\s+"), " ").trim())
            .putString(KEY_SIM, sim)
            .putString(KEY_WORKER, worker.trim())
            .apply()
    }

    fun turnOff(context: Context) = sp(context).edit().putBoolean(KEY_ON, false).apply()

    @Synchronized
    fun countSent(context: Context) {
        val p = sp(context)
        p.edit().putInt(KEY_SENT, p.getInt(KEY_SENT, 0) + 1).putLong(KEY_LAST, System.currentTimeMillis()).apply()
    }

    fun sent(context: Context) = sp(context).getInt(KEY_SENT, 0)
    fun lastSent(context: Context) = sp(context).getLong(KEY_LAST, 0)

    @Synchronized
    fun addLog(context: Context, line: String) {
        val time = SimpleDateFormat("dd-MMM HH:mm:ss", Locale.ENGLISH).format(Date())
        val lines = (listOf("$time  $line") + str(context, KEY_LOG).lines().filter { it.isNotBlank() })
            .take(MAX_LOG_LINES)
        sp(context).edit().putString(KEY_LOG, lines.joinToString("\n")).apply()
    }

    fun log(context: Context) = str(context, KEY_LOG)
}

package com.ultron.ultron_app.sms

import android.content.Context
import android.provider.Telephony
import android.telephony.SubscriptionManager

/**
 * "Send old SMS": the inbox of the last [days] days (the SIM choice applies) queued to the sheet like new
 * ones, oldest first, each with its SIM. The sheet skips any already there, so a second run adds only what is new.
 */
object SmsImport {

    fun run(context: Context, days: Int): Int {
        val since = System.currentTimeMillis() - days * 24L * 60 * 60 * 1000
        val columns = arrayOf(Telephony.Sms.ADDRESS, Telephony.Sms.BODY, Telephony.Sms.DATE, Telephony.Sms.SUBSCRIPTION_ID)
        var n = 0
        context.contentResolver.query(
            Telephony.Sms.Inbox.CONTENT_URI, columns,
            "${Telephony.Sms.DATE} >= ?", arrayOf(since.toString()), "${Telephony.Sms.DATE} ASC"
        )?.use { c ->
            while (c.moveToNext()) {
                val sim = simOf(c.getInt(3))
                if (!SmsPrefs.simAllowed(context, sim)) continue
                SmsUpload.enqueue(context, c.getString(0) ?: "", c.getString(1) ?: "", c.getLong(2), sim)
                n++
            }
        }
        SmsPrefs.addLog(context, "Old SMS: $n of the last $days days queued")
        return n
    }

    /** "SIM 1" / "SIM 2" of a subscription id (the slot index needs no permission from Android 10). */
    fun simOf(subId: Int): String {
        if (subId < 0 || android.os.Build.VERSION.SDK_INT < 29) return "SIM ?"
        val slot = SubscriptionManager.getSlotIndex(subId)
        return if (slot >= 0) "SIM ${slot + 1}" else "SIM ?"
    }
}

package com.bindal.ultronphone

import android.content.Context
import android.os.Build
import android.provider.Telephony
import android.telephony.SubscriptionManager

/**
 * "Import old SMS": the inbox of the last [days] days (the Senders filter and SIM choice apply) queued to the sheet
 * like new ones, oldest first, each with its SIM. The script skips any already there, so a second
 * import adds only what is new.
 */
object SmsImport {

    fun run(context: Context, days: Int = 60): Int {
        val since = System.currentTimeMillis() - days * 24L * 60 * 60 * 1000
        val columns = mutableListOf(Telephony.Sms.ADDRESS, Telephony.Sms.BODY, Telephony.Sms.DATE)
        val hasSub = Build.VERSION.SDK_INT >= 22
        if (hasSub) columns += Telephony.Sms.SUBSCRIPTION_ID
        var n = 0
        context.contentResolver.query(
            Telephony.Sms.Inbox.CONTENT_URI, columns.toTypedArray(),
            "${Telephony.Sms.DATE} >= ?", arrayOf(since.toString()), "${Telephony.Sms.DATE} ASC"
        )?.use { c ->
            while (c.moveToNext()) {
                val from = c.getString(0) ?: ""
                if (!Prefs.senderAllowed(context, from)) continue
                val sim = if (hasSub) simOf(c.getInt(3)) else "SIM ?"
                if (!Prefs.simAllowed(context, sim)) continue
                UploadWorker.enqueue(context, from, c.getString(1) ?: "", c.getLong(2), sim)
                n++
            }
        }
        Prefs.addLog(context, "SMS import: $n messages of the last $days days queued")
        return n
    }

    /** "SIM 1" / "SIM 2" of a subscription id (the slot index needs no permission from Android 10). */
    fun simOf(subId: Int): String {
        if (subId < 0 || Build.VERSION.SDK_INT < 29) return "SIM ?"
        val slot = SubscriptionManager.getSlotIndex(subId)
        return if (slot >= 0) "SIM ${slot + 1}" else "SIM ?"
    }
}

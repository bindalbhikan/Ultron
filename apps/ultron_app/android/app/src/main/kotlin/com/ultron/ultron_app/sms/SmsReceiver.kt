package com.ultron.ultron_app.sms

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony

/**
 * Woken by Android only when an SMS arrives. It does no network work itself: when "SMS only" mode is on it
 * hands the message (with the SIM it came in on) to WorkManager (SmsUpload) and returns at once.
 */
class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION || !SmsPrefs.isOn(context)) return
        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (parts.isNullOrEmpty()) return
        val sim = simOf(intent)

        // a long SMS arrives as several parts: joined per sender
        parts.groupBy { it.originatingAddress ?: "" }.forEach { (from, msgParts) ->
            val body = msgParts.joinToString("") { it.messageBody ?: "" }
            if (!SmsPrefs.simAllowed(context, sim)) {
                SmsPrefs.addLog(context, "Skipped $from ($sim; this phone sends ${SmsPrefs.sim(context)})")
                return@forEach
            }
            SmsUpload.enqueue(context, from, body, msgParts.first().timestampMillis, sim)
            SmsPrefs.addLog(context, "Queued $from ($sim)")
        }
    }

    /** "SIM 1" / "SIM 2" from the slot index the phone puts on the broadcast (makers use different extras). */
    private fun simOf(intent: Intent): String {
        val slot = listOf("android.telephony.extra.SLOT_INDEX", "slot", "simSlot", "slot_id", "simId")
            .map { intent.getIntExtra(it, -1) }
            .firstOrNull { it >= 0 }
        if (slot != null) return "SIM ${slot + 1}"
        val subId = listOf("android.telephony.extra.SUBSCRIPTION_INDEX", "subscription")
            .map { intent.getIntExtra(it, -1) }
            .firstOrNull { it >= 0 } ?: -1
        return SmsImport.simOf(subId)
    }
}

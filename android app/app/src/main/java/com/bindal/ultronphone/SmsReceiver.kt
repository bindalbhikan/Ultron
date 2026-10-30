package com.bindal.ultronphone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony

/**
 * Invoked by Android only when an SMS arrives. It does no network work itself: it hands the
 * message (with the SIM it came in on) to WorkManager and returns immediately.
 */
class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (parts.isNullOrEmpty()) return
        val sim = simOf(intent)

        // Long SMS arrive as multiple parts; join them per sender.
        parts.groupBy { it.originatingAddress ?: "" }.forEach { (from, msgParts) ->
            val body = msgParts.joinToString("") { it.messageBody ?: "" }
            val timestamp = msgParts.first().timestampMillis

            if (!Prefs.senderAllowed(context, from)) {
                Prefs.addLog(context, "SMS skipped (filter) $from")
                return@forEach
            }
            if (!Prefs.simAllowed(context, sim)) {
                Prefs.addLog(context, "SMS skipped ($sim, sheet takes ${Prefs.getSim(context)}) $from")
                return@forEach
            }

            UploadWorker.enqueue(context, from, body, timestamp, sim)
            Prefs.addLog(context, "SMS queued $from ($sim)")
        }
    }

    /**
     * "SIM 1" / "SIM 2" from the slot index the phone puts on the broadcast (makers use different
     * extras), else from its subscription id.
     */
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

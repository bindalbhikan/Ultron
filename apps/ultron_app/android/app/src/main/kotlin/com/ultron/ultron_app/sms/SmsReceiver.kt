package com.ultron.ultron_app.sms

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.provider.Telephony
import kotlin.concurrent.thread

/**
 * Woken by Android only when an SMS arrives. Real time (owner, 25 Nov 2026: an OTP must reach the sheet at once):
 * the SMS is sent to the worker right here, on a background thread while Android keeps the app awake for this
 * SMS (goAsync), with no queue in between. Only when that send cannot go through (no internet, a timeout, a server
 * error) is it queued in WorkManager (SmsUpload), which sends it the moment the network is back and keeps trying.
 * A courier SMS with a POD link is sent at once too (its OTP reaches the sheet first); right after, SmsUpload
 * (expedited, so at once) reads its POD and sends it again with the POD (rework), which names the OTP's portals.
 */
class SmsReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION || !SmsPrefs.isOn(context)) return
        val parts = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (parts.isNullOrEmpty()) return
        val sim = simOf(intent)
        val instant = mutableListOf<Pair<Triple<String, String, Long>, String>>()

        // a long SMS arrives as several parts: joined per sender
        parts.groupBy { it.originatingAddress ?: "" }.forEach { (from, msgParts) ->
            val body = msgParts.joinToString("") { it.messageBody ?: "" }
            if (!SmsPrefs.simAllowed(context, sim)) {
                SmsPrefs.addLog(context, "Skipped $from ($sim; this phone sends ${SmsPrefs.sim(context)})")
                return@forEach
            }
            instant.add(Triple(from, body, msgParts.first().timestampMillis) to sim)
        }
        if (instant.isEmpty()) return
        val pending = goAsync()
        val app = context.applicationContext
        thread(name = "ultron-sms-now") {
            try {
                for ((msg, sim) in instant) {
                    val (from, body, time) = msg
                    // within Android's time for a receiver: 8 s to connect, 25 s for the sheet's answer
                    val outcome = SmsUpload.send(app, from, body, time, sim, null, "at once", 8_000, 25_000)
                    when {
                        outcome == SmsUpload.Outcome.AGAIN -> {       // the queue sends it (with its POD) later
                            SmsUpload.enqueue(app, from, body, time, sim)
                            SmsPrefs.addLog(app, "Queued $from ($sim): sent the moment the network is back")
                        }
                        outcome == SmsUpload.Outcome.DONE && Pod.needed(from, body) ->
                            SmsUpload.enqueue(app, from, body, time, sim, rework = true)
                    }
                }
            } finally {
                pending.finish()
            }
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

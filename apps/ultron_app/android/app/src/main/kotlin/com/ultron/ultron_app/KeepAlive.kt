package com.ultron.ultron_app

import android.content.Context
import androidx.work.ExistingPeriodicWorkPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.PeriodicWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.Worker
import androidx.work.WorkerParameters
import com.ultron.ultron_app.agent.AgentPrefs
import com.ultron.ultron_app.agent.AgentService
import com.ultron.ultron_app.sms.SmsPrefs
import com.ultron.ultron_app.sms.SmsService
import java.util.concurrent.TimeUnit

/**
 * Keeps SMS only and Agent mode running after the app is closed. Their services already come back after a
 * reboot (SmsBootReceiver); this also brings them back when the app is swiped away or a phone maker
 * (Xiaomi, Oppo, Vivo, Realme) stops them: when the app opens, one minute after the app is swiped away,
 * and every 15 minutes (WorkManager, which Android runs even when the app is closed).
 */
object KeepAlive {
    private const val EVERY = "ultron-keepalive"
    private const val SOON = "ultron-keepalive-soon"

    /** Starts whichever of the two is on but not running. */
    fun ensure(context: Context, why: String) {
        val c = context.applicationContext
        if (SmsPrefs.isOn(c) && !SmsService.alive) {
            try { SmsService.start(c); SmsPrefs.addLog(c, "SMS only running again ($why)") }
            catch (e: Exception) { SmsPrefs.addLog(c, "SMS only not restarted ($why): ${e.javaClass.simpleName}; open ULTRON once") }
        }
        if (AgentPrefs.isOn(c) && !AgentService.alive) {
            try { AgentService.start(c); AgentPrefs.addLog(c, "Agent running again ($why)") }
            catch (e: Exception) { AgentPrefs.addLog(c, "Agent not restarted ($why): ${e.javaClass.simpleName}; open ULTRON once") }
        }
        if (SmsPrefs.isOn(c) || AgentPrefs.isOn(c)) schedule(c)
    }

    /** The 15-minute check (kept, not restarted, when it is already scheduled). */
    fun schedule(context: Context) {
        WorkManager.getInstance(context.applicationContext).enqueueUniquePeriodicWork(
            EVERY, ExistingPeriodicWorkPolicy.KEEP,
            PeriodicWorkRequestBuilder<KeepAliveWork>(15, TimeUnit.MINUTES).build())
    }

    /** A check one minute from now: the app was swiped away and the phone may stop its services. */
    fun soon(context: Context) {
        WorkManager.getInstance(context.applicationContext).enqueueUniqueWork(
            SOON, ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<KeepAliveWork>().setInitialDelay(1, TimeUnit.MINUTES).build())
    }

    fun cancel(context: Context) {
        WorkManager.getInstance(context.applicationContext).cancelUniqueWork(EVERY)
    }
}

class KeepAliveWork(context: Context, params: WorkerParameters) : Worker(context, params) {
    override fun doWork(): Result {
        val c = applicationContext
        if (!SmsPrefs.isOn(c) && !AgentPrefs.isOn(c)) KeepAlive.cancel(c)   // both off: nothing to keep
        else KeepAlive.ensure(c, "watchdog")
        return Result.success()
    }
}

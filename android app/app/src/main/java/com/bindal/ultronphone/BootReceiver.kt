package com.bindal.ultronphone

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** After a reboot (or an app update) Agent mode comes back on by itself when it was on. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action in listOf(Intent.ACTION_BOOT_COMPLETED, Intent.ACTION_MY_PACKAGE_REPLACED) && Prefs.agentOn(context)) {
            AgentService.start(context)
        }
    }
}

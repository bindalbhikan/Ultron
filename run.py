#!/usr/bin/env python
"""Entry point for every bot:  python run.py <bot> [options]

  sale       daily sale report            python run.py sale --help
  vms        Myntra VMS report            python run.py vms --help
  ajio-tat   AJIO dispatch TAT            python run.py ajio-tat --help
  ajio-spf   AJIO SPF claims              python run.py ajio-spf --help
  returns    monthly return analysis      python run.py returns --help
  myntra-spf Myntra SPF master            python run.py myntra-spf --help
  ajio-ads   AJIO ads / TOT gap, monthly  python run.py ajio-ads --help
  inv-push   OMSGuru inventory push, 3-hourly  python run.py inv-push --help
  agent-watch  the agent checks a finished run  python run.py agent-watch --help
  agent-chat   answer a Telegram message      python run.py agent-chat --help
  morning    9:30 AM sale vs last week     python run.py morning --help
  sla        12 / 3 PM orders due, not RTS   python run.py sla --help
  labels     6 PM ERP labels vs OMSGuru      python run.py labels --help
  stock      10 AM SKUs selling, running out python run.py stock --help
  evening    8 PM summary of the day        python run.py evening --help
  weekly     Monday business review         python run.py weekly --help
  deadstock  monthly dead / slow stock      python run.py deadstock --help
  myntra-otp 10 / 11 AM Myntra pickup / return OTPs python run.py myntra-otp --help
  listings   11:30 AM listing health        python run.py listings --help
  myntra-tat 6:30 PM Myntra courier pickups   python run.py myntra-tat --help
  mis        monthly MIS and plan           python run.py mis --help
  myntra-reports 10 AM Myntra orders / returns / listings  python run.py myntra-reports --help
  myntra-zero-td 10 AM / 2 PM / 5 PM styles live at MRP  python run.py myntra-zero-td --help
"""
import importlib
import sys

BOTS = {"sale": "ultron.workings.sale.pipeline", "vms": "ultron.workings.vms.pipeline",
        "ajio-tat": "ultron.workings.ajio_tat.pipeline", "ajio-spf": "ultron.workings.ajio_spf.pipeline",
        "returns": "ultron.workings.return_analysis.pipeline", "myntra-spf": "ultron.workings.myntra_spf.pipeline",
        "ajio-ads": "ultron.workings.ajio_ads.pipeline", "inv-push": "ultron.workings.inv_push.pipeline",
        "agent-watch": "ultron.agents.watch", "agent-chat": "ultron.agents.chat", "morning": "ultron.workings.morning.pipeline",
        "sla": "ultron.workings.sla.pipeline", "labels": "ultron.workings.labels.pipeline",
        "stock": "ultron.workings.stock.pipeline", "evening": "ultron.workings.evening.pipeline",
        "weekly": "ultron.workings.weekly.pipeline", "deadstock": "ultron.workings.deadstock.pipeline",
        "listings": "ultron.workings.listings.pipeline", "myntra-tat": "ultron.workings.myntra_tat.pipeline",
        "mis": "ultron.workings.mis.pipeline", "myntra-otp": "ultron.workings.myntra_otp.pipeline",
        "myntra-reports": "ultron.workings.myntra_reports.pipeline",
        "myntra-zero-td": "ultron.workings.myntra_zero_td.pipeline",
        "work-schedule": "ultron.workings.work_schedule.pipeline",
        "myntra-history": "ultron.workings.myntra_history.pipeline"}


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in BOTS:
        print(__doc__)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    return importlib.import_module(BOTS[argv[0]]).main(argv[1:])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

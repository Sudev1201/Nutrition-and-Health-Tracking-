"""Send the meal reminders due now, once each, and exit. This is the reminder loop for cron.

The API can run the reminders itself, with SCHEDULER_ENABLED=true. A deployment
that would rather keep them out of the web process runs this every minute:

    * * * * *  cd /path/to/backend && uv run python -m scripts.send_reminders

Running both is safe. Each reminder is claimed in the database before it is
sent, and only the runner that claims it sends it.

Usage:
    uv run python -m scripts.send_reminders
"""

import sys

from app.config import settings
from app.reminders.channels import WebPushChannel
from app.reminders.runner import run_once


def main() -> int:
    if not settings.vapid_private_key:
        print(
            "VAPID_PRIVATE_KEY is not set, so there is no key to sign a push with.",
            file=sys.stderr,
        )
        return 1
    sent = run_once(WebPushChannel(settings.vapid_private_key, settings.vapid_subject))
    print(f"reminders sent: {sent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

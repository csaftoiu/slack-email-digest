import datetime

import tzlocal
import pytz


def tzdt_from_timestamp(ts, tz=None):
    """Return a timezone-aware datetime from a timestamp.
    :param ts: UTC timestamp in seconds from the epoch.
    :param tz: Timezone to use, defaults to tzlocal.get_localzone()
    """
    tz = tz or tzlocal.get_localzone()
    return datetime.datetime.utcfromtimestamp(ts).replace(tzinfo=pytz.utc).astimezone(tz)

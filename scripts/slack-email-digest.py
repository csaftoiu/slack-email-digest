#!/usr/bin/env python3
"""
Usage: slack-email-digest.py [options]

Options:
    -t --token=<token>       Slack API token to use (required)
    -c --channel=<name>      Channel to export. [default: general]
    -s --start-ts=<ts>       UTC timestamp of the first message to include.
                             Defaults to the start of yesterday in the local timezone.
    -e --end-ts=<ts>         UTC timestamp of the last message to include.
                             Defaults to 1 day after --start-ts.
    -o --out-file=<file>     Filename to output. [default: digest.html]
    -v --verbose             Whether to provide verbose output
"""

import datetime
import sys

from docopt import docopt

from slack_email_digest import SlackScraper, HTMLRenderer


def main():
    args = docopt(__doc__)

    yest = datetime.datetime.now() - datetime.timedelta(days=1)
    start_ts = args['--start-ts'] or datetime.datetime(yest.year, yest.month, yest.day).timestamp()
    end_ts = args['--end-ts'] or (
        (datetime.datetime.fromtimestamp(start_ts) + datetime.timedelta(days=1)).timestamp()
    )
    token = args['--token']
    verbose = args['--verbose']
    out_file = args['--out-file']

    if not token:
        sys.exit("Must provide --token")

    scraper = SlackScraper(token, verbose=verbose)
    hist = scraper.get_channel_history(
        args['--channel'],
        oldest=start_ts, latest=end_ts)

    hist.sort(key=lambda msg: float(msg['ts']))

    renderer = HTMLRenderer(scraper)
    # render as ascii with xmlcharrefreplace, so don't have to deal with encoding
    with open(out_file, 'wb') as f:
        f.write(renderer.render_messages(hist).encode('ascii', errors='xmlcharrefreplace'))


if __name__ == '__main__':
    main()

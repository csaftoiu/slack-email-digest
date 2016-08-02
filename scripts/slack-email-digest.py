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

    args['--start-ts'] = args['--start-ts'] or datetime.datetime(yest.year, yest.month, yest.day).timestamp()
    args['--end-ts'] = args['--end-ts'] or (
        (datetime.datetime.fromtimestamp(args['--start-ts']) + datetime.timedelta(days=1)).timestamp()
    )

    if not args['--token']:
        sys.exit("Must provide --token")

    scraper = SlackScraper(args['--token'], verbose=args['--verbose'])
    hist = scraper.get_channel_history(
        args['--channel'],
        oldest=args['--start-ts'], latest=args['--end-ts'])

    hist.sort(key=lambda msg: float(msg['ts']))

    renderer = HTMLRenderer(scraper)

    for msg in hist:
        print(renderer.render_message(msg))


if __name__ == '__main__':
    main()

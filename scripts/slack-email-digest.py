#!/usr/bin/env python3
"""
Usage: slack-email-digest.py [options] [--from=<email> --to=<email> --token=<token>]

Options can be specified in three ways, with this order of precedence:
    INI config file,      e.g. "from=foo@foo.com"
    environment variable, e.g. "SLACKEMAILDIGEST_FROM=foo@foo.com"
    command-line option,  e.g. "--from=foo@foo.com"

Options:
    -c --config=<file.ini>   INI file to use for configuration
    -v --verbose             Whether to provide verbose output

Slack Options:
    -t --token=<token>       Slack API token to use
    --channel=<name>         Channel to export. [default: general]

Exporting Options:
    --invite-link=<url>      If provided, a message will be rendered in the
                             header inviting readers to click on the link
                             to get an invite to the Slack team.
    --date=<YYYY-mm-dd>      Date to export in YYYY-mm-dd format.
                             Defaults to yesterday. Messages are exported
                             from the start of the day to the end of the
                             day, in UTC.
    --timezone=<tz>          Timezone to use for start and end
                             of day and to display messages in.
                             [default: UTC]

Mailing Options:
    --from=<name>            Email to send from.
    --to=<email>             Destination email.
    --delay=<seconds>        Number of seconds to wait in between
                             sending messages. [default: 5]
    --from-name=<name>       Name to send from. e.g. appears in "Name" part
                             as "Name <foo@foo.com>"
                             [default: Slack DigestBot]
    --delivery=<method>      Delivery method. Valid options
                             are "stdout", "local_files", "smtp", "postmark".
                             See delivery options for more.
                             [default: stdout]

SMTP Delivery Options:
    --smtp-user=<user>       SMTP login
    --smtp-password=<pwd>    SMTP password
    --smtp-host=<host>       SMTP host
    --smtp-port=<port>       SMTP port [default: 587]
"""

import calendar
import datetime
import os
import pprint
import sys
import time

from clint.textui import progress
from docoptcfg import docoptcfg
from postmark import PMMail
import pytz

from slack_email_digest import SlackScraper, HTMLRenderer, EmailRenderer


def format_last_message_id(date):
    return '<digest-%s-lastpart@slackemaildigest.com>' % date.strftime('%Y-%m-%d')


class DecoratorDictRegister(dict):
    def __init__(self):
        super(DecoratorDictRegister, self).__init__()

    def register(self, name):
        def decorator(f):
            self[name] = f
            return f
        return decorator
delivery_methods = DecoratorDictRegister()


@delivery_methods.register('stdout')
def deliver_stdout(args, message):
    # Strip long messages
    if len(message['html_body']) > 40:
        message['html_body'] = message['html_body'][:40] + '...'
    if len(message['text_body']) > 40:
        message['text_body'] = message['text_body'][:40] + '...'
    pprint.pprint(message)


@delivery_methods.register('local_files')
def deliver_files(args, message):
    import re

    def slugify(value):
        # from http://stackoverflow.com/a/295466/15055
        """
        Normalizes string, converts to lowercase, removes non-alpha characters,
        and converts spaces to hyphens.
        """
        import unicodedata
        value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore')
        value = re.sub(b'[^\w\s-]', b'', value).strip().lower().decode('ascii')
        value = value.replace(" ", "-")
        return value

    fn = "%s.html" % (slugify(message['subject']),)
    print("Writing email to %s..." % (fn,))
    open(fn, 'w').write(message['html_body'])


@delivery_methods.register('postmark')
def deliver_postmark(args, email):
    if not os.environ.get('POSTMARK_API_TOKEN'):
        sys.exit("Missing POSTMARK_API_TOKEN variable")

    message = PMMail(
        api_key=os.environ.get('POSTMARK_API_TOKEN'),
        subject=email['subject'],
        sender=email['sender'],
        to=email['to'],
        text_body=email['text_body'],
        html_body=email['html_body'],
        tag="slack_digest",
        custom_headers=email["custom_headers"],
    )

    message.send()


@delivery_methods.register('smtp')
def deliver_smtp(args, email_msg):
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    import smtplib

    def get_option(option_name):
        full_opt = '--smtp-%s' % option_name
        if args[full_opt] is None:
            sys.exit("Missing SMTP option %s" % (full_opt,))
        return args[full_opt]

    from_email = args['--from']
    to = args['--to']

    user = get_option('user')
    password = get_option('password')
    host = get_option('host')
    port = int(get_option('port'))

    mime_msg = MIMEMultipart('alternative')
    mime_msg['Subject'] = email_msg['subject']
    mime_msg['From'] = email_msg['sender']
    mime_msg['To'] = email_msg['to']
    for key, val in email_msg.get('custom_headers', {}).items():
        mime_msg[key] = val

    mime_msg.attach(MIMEText(email_msg['text_body'], 'plain'))
    mime_msg.attach(MIMEText(email_msg['html_body'], 'html'))

    server = smtplib.SMTP(host, port)
    server.ehlo()
    server.starttls()
    server.login(user, password)
    server.sendmail(from_email, to, mime_msg.as_string())
    server.close()


def main():
    args = docoptcfg(__doc__, env_prefix="SLACKEMAILDIGEST_", config_option='--config')

    # process args
    tz_str = args['--timezone']
    tz = pytz.timezone(tz_str)

    # for date, make naive timetuples, use calendar.timegm to convert them to
    # the proper timestamps (which are always UTC)
    if args['--date']:
        date = datetime.datetime.strptime(args['--date'], '%Y-%m-%d')
    else:
        date = datetime.datetime.utcfromtimestamp(time.time()) - datetime.timedelta(days=1)
        date = date.replace(hour=0, minute=0, second=0, microsecond=0)

    date = tz.localize(date)

    start_ts = calendar.timegm(date.utctimetuple())
    end_ts = calendar.timegm((date + datetime.timedelta(days=1)).utctimetuple())

    # work-around docoptcfg not taking required arguments from a config file
    for required in ['--token', '--from', '--to']:
        if not args[required]:
            sys.exit("Must provide {}".format(required))

    token = args['--token']
    verbose = args['--verbose']
    delivery = args['--delivery']
    from_email = args['--from']
    to = args['--to']
    from_name = args['--from-name']
    delay = int(args['--delay'])
    slack_channel = args['--channel']
    invite_link = args['--invite-link']

    if delivery not in delivery_methods:
        sys.exit("Unknown delivery method: %s" % (delivery,))

    # scrape
    print("Fetching Slack messages for #%s from %s (%s) to %s (%s) " % (
        slack_channel,
        pytz.utc.localize(datetime.datetime.utcfromtimestamp(start_ts)).astimezone(tz),
        pytz.utc.localize(datetime.datetime.utcfromtimestamp(start_ts)).astimezone(tz).strftime("%Z"),
        pytz.utc.localize(datetime.datetime.utcfromtimestamp(end_ts)).astimezone(tz),
        pytz.utc.localize(datetime.datetime.utcfromtimestamp(end_ts)).astimezone(tz).strftime("%Z"),
        ), file=sys.stderr)

    scraper = SlackScraper(token, verbose=verbose)
    scraper.set_invite_link(invite_link)
    team_id = scraper.get_team_id()
    channel_id = scraper.get_channel_id(slack_channel)

    hist = scraper.get_channel_history(
        slack_channel,
        oldest=start_ts, latest=end_ts,
    )

    hist.sort(key=lambda msg: float(msg['ts']))

    html_renderer = HTMLRenderer(scraper, tz)
    email_renderer = EmailRenderer(html_renderer)

    # render emails, replying to the last day's digest, and setting the last
    # id to be reply-able from the next day's digest
    emails = email_renderer.render_digest_emails(
        hist, date, team_id, channel_id,
    )
    for email in emails:
        email['sender'] = ("%s <%s>" % (from_name, from_email)) if from_name else from_email
        email['to'] = to

    delivery_method = delivery_methods[delivery]
    print("Delivering in %d parts... via %s" % (len(emails), delivery_method.__name__), file=sys.stderr)
    
    for email in emails:    
        delivery_method(args, email)
        for _ in progress.bar(range(delay), label="Waiting to send next message... "):
            time.sleep(1)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Usage: slack-email-digest.py [options] [--from=<email> --to=<email> --token=<token>]

Options:
    -c --config=<file.ini>   INI file to use for configuration
    -v --verbose             Whether to provide verbose output

    -t --token=<token>       Slack API token to use
    --channel=<name>         Channel to export. [default: general]
    --date=<YYYY-mm-dd>      Date to export in YYYY-mm-dd format.
                             Defaults to yesterday.

    --from=<name>            Email to send from.
    --to=<email>             Destination email.
    --delay=<seconds>        Number of seconds to wait in between
                             sending messages. [default: 5]
    --from-name=<name>       Name to send from. e.g. appears in "Name" part
                             as "Name <foo@foo.com>"
                             [default: Slack DigestBot]
    --delivery=<method>      Delivery method. Valid options
                             are "stdout", "smtp", "postmark".
                             See delivery options for more.
                             [default: stdout]

SMTP Delivery Options:
    --smtp-user=<user>       SMTP login
    --smtp-password=<pwd>    SMTP password
    --smtp-host=<host>       SMTP host
    --smtp-port=<port>       SMTP port [default: 587]
"""

import datetime
import pprint
import sys
import time

from clint.textui import progress
from docoptcfg import docoptcfg

from slack_email_digest import SlackScraper, HTMLRenderer, EmailRenderer
from slack_email_digest.datetime import tzdt_from_timestamp


def format_last_message_id(date):
    return '<digest-%s-lastpart@slackemaildigest.com>' % date.strftime('%Y-%m-%d')


delivery_methods = {}
def register_delivery_method(name):
    def decorator(f):
        delivery_methods[name] = f
        return f
    return decorator


@register_delivery_method('stdout')
def deliver_stdout(args, messages):
    pprint.pprint(messages)


@register_delivery_method('smtp')
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
    args = docoptcfg(__doc__, env_prefix="SLACKEMAILDIGEST", config_option='--config')

    # process args
    if args['--date']:
        date = datetime.datetime.strptime(args['--date'], '%Y-%m-%d')
    else:
        date = (tzdt_from_timestamp(time.time()) - datetime.timedelta(days=1))

    start_ts = time.mktime(date.timetuple())
    end_ts = time.mktime((date + datetime.timedelta(days=1)).timetuple())

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

    if delivery not in delivery_methods:
        sys.exit("Unknown delivery method: %s" % (delivery,))

    # scrape
    if verbose:
        print("Getting messages from %s to %s " % (
            tzdt_from_timestamp(start_ts),
            tzdt_from_timestamp(end_ts),
        ), file=sys.stderr)

    scraper = SlackScraper(token, verbose=verbose)
    hist = scraper.get_channel_history(
        args['--channel'],
        oldest=start_ts, latest=end_ts)

    hist.sort(key=lambda msg: float(msg['ts']))

    html_renderer = HTMLRenderer(scraper)
    email_renderer = EmailRenderer(html_renderer)

    # render emails, replying to the last day's digest, and setting the last
    # id to be reply-able from the next day's digest
    in_reply_to = None
    last_message_id = format_last_message_id(date)
    if date.day > 1:
        in_reply_to = format_last_message_id(date - datetime.timedelta(days=1))

    emails = email_renderer.render_digest_emails(hist, in_reply_to=in_reply_to, last_message_id=last_message_id)
    for email in emails:
        email['sender'] = ("%s <%s>" % (from_name, from_email)) if from_name else from_email
        email['to'] = to

    if verbose:
        print("Delivering in %d parts..." % (len(emails,)), file=sys.stderr)

    for email in emails:
        delivery_methods[delivery](args, email)
        for _ in progress.bar(range(delay), label="Waiting to send next message... "):
            time.sleep(1)


if __name__ == '__main__':
    main()

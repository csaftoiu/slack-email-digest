import datetime
import re

import emoji
import jinja2
import pytz
import tzlocal


TEMPLATES = {
    'full_html': """\
<html>
<head>
<style type="text/css">
body {
    font-family: Slack-Lato,appleLogo,sans-serif;
    font-size: .9375rem;
    line-height: 1.375rem;
}
code {
    white-space: normal;
    color: #c25;
    padding: 1px 3px;
    background-color: #f7f7f9;
    border: 1px solid #e1e1e8;
    border-radius: 3px;
    box-sizing: border-box;
}
pre {
    margin: .5rem 0 .2rem;
    font-size: .75rem;
    line-height: 1.15rem;
    background: #fbfaf8;
    padding: .5rem;
    display: block;
    word-wrap: break-word;
    white-space: pre-wrap;
    border: 1px solid rgba(0, 0, 0, .15);
    border-radius: 4px;
    font-family: Monaco,Menlo,Consolas,"Courier New",monospace;
    color; #333;
    box-sizing: border-box;
}
.at-ref {
    color: #2a80b9;
}
.channel-ref {
    color: #2a80b9;
}
</style>
</head>
<body>
<h1>Slack Digest for {{ date }}</h1>
{{ messages }}
</body>
</html>\
""",

    'announcement': """\
<div>
  <i>{{ text }}</i></b>
</div>\
""",

    'message': """\
<div>
  <b>{{ user }}</b>: {{ text }}</b>
</div>\
""",

    'at': """\
<span class="at-ref">@{{ user }}</span>\
""",

    'channel_ref': """\
<span class="channel-ref">#{{ channel }}</span>\
"""
}


ANNOUNCEMENT_TYPES = ['channel_join', 'file_share', 'channel_topic']


def fix_emoji():
    """Fix emoji's aliases as they have some typos."""
    from emoji import unicode_codes
    for key, val in list(unicode_codes.EMOJI_UNICODE.items()):
        unicode_codes.EMOJI_UNICODE[key.replace('-', '_')] = val
    for key, val in list(unicode_codes.EMOJI_ALIAS_UNICODE.items()):
        unicode_codes.EMOJI_ALIAS_UNICODE[key.replace('-', '_')] = val

    unicode_codes.UNICODE_EMOJI = {v: k for k, v in unicode_codes.EMOJI_UNICODE.items()}
    unicode_codes.UNICODE_EMOJI_ALIAS = {v: k for k, v in unicode_codes.EMOJI_ALIAS_UNICODE.items()}


fix_emoji()


class HTMLRenderer:
    """Given a SlackScraper, render messages to HTML suitable for display in
    an email client.
    """
    def __init__(self, scraper, redact_users=None):
        """
        :param scraper: A SlackScraper to get channel names, user names, etc.
        :param redact_users: List of users to redact. Defaults to ['mailclark'] to avoid
            recursion.
        """
        self.redact_users = redact_users or ['mailclark']

        self.scraper = scraper

        self.env = jinja2.Environment()
        self.env.filters['username'] = self.filter_username

        self.templates = {name: self.env.from_string(template) for name, template in TEMPLATES.items()}

    def filter_username(self, user_id):
        return self.scraper.get_username(user_id)

    def process_text(self, text):
        def sub_at(m):
            return self.templates['at'].render(user=self.scraper.get_username(m.group(1)))

        def sub_channel(m):
            return self.templates['channel_ref'].render(channel=self.scraper.get_channel_name(m.group(1)))

        def sub_custom_emoji(m, big=False):
            text = m.group(1)
            if text[1:-1] in self.scraper.emojis:
                return '<img width="%s" src="%s">' % (32 if big else 20, self.scraper.emojis[text[1:-1]])
            return text

        # # first all the < ... > specials
        # sub @ references without username
        text = re.sub(r'<@(\w+)>', sub_at, text)
        # sub @ references with username, look up the most recent username anyway
        text = re.sub(r'<@(\w+)\|[^>]+>', sub_at, text)

        # sub channel references with/without the name
        text = re.sub(r'<#(\w+)>', sub_channel, text)
        text = re.sub(r'<#(\w+)\|[^>]+>', sub_channel, text)

        # link with sub
        text = re.sub(r'<([^\| ]+)\|([^>]+)>', lambda m: '<a href="%s">%s</a>' % (
            m.group(1), m.group(2),
        ), text)
        # link without sub
        text = re.sub(r'<([^/])([^> ]+)>', lambda m: '<a href="%s%s">%s%s</a>' % (
            m.group(1), m.group(2), m.group(1), m.group(2),
        ), text)

        # # message formatting
        # multi-tick
        text = re.sub(r'```\n?(.*)```', lambda m: '<pre>%s</pre>' % (m.group(1),), text, flags=re.DOTALL)

        # bold
        text = re.sub(r'\*(\w[^\*]+)\*(\b|\W|$)', lambda m: '<b>%s</b>%s' % (m.group(1), m.group(2)), text)
        # italic
        text = re.sub(r'_(\w[^_]+)_(\b|\W|$)', lambda m: '<i>%s</i>%s' % (m.group(1), m.group(2)), text)
        # strike-through
        text = re.sub(r'~(\w[^~]+\w)~(\b|\W|$)', lambda m: '<strike>%s</strike>%s' % (m.group(1), m.group(2)), text)
        # tick
        text = re.sub(r'`(\w[^`]+)`(\b|\W|$)', lambda m: '<code>%s</code>%s' % (m.group(1), m.group(2)), text)

        # blockquotes
        text = re.sub(r"\n?&gt;(.*\w.*)\n?\n?", lambda m: '<blockquote>%s</blockquote>' % (m.group(1),), text)

        # newline
        text = text.replace('\n', '<br>')
        # spacing
        text = re.sub(r'  ', '&nbsp;&nbsp;', text)

        # emojis
        text = emoji.emojize(text, use_aliases=True)
        # custom emojis
        # nothing but whitespace - big emoji
        text = re.sub(r'^\W*(:[a-zA-Z0-9\+\-_&.ô’Åéãíç]+:)\W*$', lambda m: sub_custom_emoji(m, True), text)
        # otherwise, small emoji
        text = re.sub(r'(:[a-zA-Z0-9\+\-_&.ô’Åéãíç]+:)', sub_custom_emoji, text)

        return text

    def render_message(self, msg):
        username = self.scraper.get_username(msg['user'])
        text = msg['text']

        which = 'message'
        if msg.get('subtype') in ANNOUNCEMENT_TYPES:
            which = 'announcement'
        else:
            if username in self.redact_users:
                text = "<i>[redacted]</i>"

        return self.templates[which].render(
            user=username,
            text=self.process_text(text),
        )

    def render_messages(self, messages):
        start_dt = datetime.datetime.utcfromtimestamp(min(float(msg['ts']) for msg in messages))
        end_dt = datetime.datetime.utcfromtimestamp(max(float(msg['ts']) - 1 for msg in messages))

        local_tz = tzlocal.get_localzone()
        start_dt = start_dt.replace(tzinfo=pytz.utc).astimezone(local_tz)
        end_dt = end_dt.replace(tzinfo=pytz.utc).astimezone(local_tz)

        fmt = '%A, %B %d, %Y'

        start = start_dt.strftime(fmt)
        end = end_dt.strftime(fmt)

        if start == end:
            date_str = start
        else:
            date_str = "%s to %s" % (start, end)

        date_str = "%s (%s)" % (date_str, start_dt.strftime("%Z"))

        return self.templates['full_html'].render(
            date=date_str,
            messages="\n".join(self.render_message(msg) for msg in messages),
        )

import datetime
import pprint
import re

import emoji
import jinja2
import pyshorteners
import pytz
import tzlocal

from .memoize import memoize1_to_json_file


TEMPLATES = {
    'full_html': """\
<div style="font-family: Slack-Lato,appleLogo,sans-serif; font-size: .9375rem; line-height: 1.375rem;">
<h2>Slack Digest for {{ date }}</h2>
{{ messages }}
</div>\
""",

    'message': """\
<table><tr><td valign="top"><img {% if avatar %}src="{{ avatar }}"{% endif %} width="32"></td>
  <td><b>{{ user }}</b> <font color="#7f7f7f">{{ timestamp }}</font><br>
  {{ text }}
  </td>
</table>\
""",

    'at': """\
<font color="#2a80b9">@{{ user }}</font>\
""",

    'channel_ref': """\
<font color="#2a80b9">#{{ channel }}</font>\
""",

    'code': """\
<code style="color: #c25; border: 1px solid #e1e1e8">{{ text }}</code>{{ after }}\
""",

    'pre': """\
<pre style="margin: .5rem 0 .2rem; border: 1px solid rgba(0, 0, 0, .15);">{{ text }}</pre>{{ after }}\
""",
}


ANNOUNCEMENT_TYPES = ['channel_join', 'file_share', 'channel_topic']


@memoize1_to_json_file('shortened_url_cache.json')
def get_shortened_url(url):
    import sys
    print("Getting shortened URL for %s..." % (url,), file=sys.stderr)
    res = pyshorteners.Shortener('Isgd', timeout=5).short(url)
    print("    ... %s" % (res,), file=sys.stderr)
    return res


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
    def __init__(self, scraper, redact_users=None, redact_avatars=None):
        """
        :param scraper: A SlackScraper to get channel names, user names, etc.
        :param redact_users: List of users to redact. Defaults to ['mailclark'] to avoid
            recursion.
        :param redact_avatars: List of users whose avatar not to include. Defaults to nobody.
        """
        self.redact_users = redact_users or ['mailclark']
        self.redact_avatars = redact_avatars or []

        self.scraper = scraper

        self.env = jinja2.Environment()
        self.env.filters['username'] = self.filter_username

        self.templates = {name: self.env.from_string(template) for name, template in TEMPLATES.items()}

        # map usernames to avatars
        self.avatars = {}
        self.load_avatars()

    def load_avatars(self):
        for name, info in self.scraper.users.items():
            self.avatars[name] = get_shortened_url(info['profile']['image_72'])

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
        def sub_fmt(which):
            return lambda m: self.templates[which].render(text=m.group(1), after=m.group(2))

        # multi-tick
        text = re.sub(r'```\n?(.*)```()', sub_fmt('pre'), text, flags=re.DOTALL)

        # bold
        text = re.sub(r'\*(\w[^\*]+)\*(\b|\W|$)', lambda m: '<b>%s</b>%s' % (m.group(1), m.group(2)), text)
        # italic
        text = re.sub(r'_(\w[^_]+)_(\b|\W|$)', lambda m: '<i>%s</i>%s' % (m.group(1), m.group(2)), text)
        # strike-through
        text = re.sub(r'~(\w[^~]+\w)~(\b|\W|$)', lambda m: '<strike>%s</strike>%s' % (m.group(1), m.group(2)), text)
        # tick
        text = re.sub(r'`(\w[^`]+)`(\b|\W|$)', sub_fmt('code'), text)

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
        if 'user' in msg:
            username = self.scraper.get_username(msg['user'])
        elif 'bot_id' in msg:
            username = "%s (BOT)" % self.scraper.get_bot_name(msg['bot_id'])
        else:
            raise ValueError("Don't know how to handle this message:\n%s" % (pprint.pformat(msg),))

        text = msg['text']

        which = 'message'
        if msg.get('subtype') in ANNOUNCEMENT_TYPES:
            pass
        else:
            if username in self.redact_users:
                text = "<i>[redacted]</i>"

        # append reactions
        if msg.get('reactions'):
            text += "\n<span style='color: #777;'>(Reactions: %s)</span>" % (
                ", ".join(":%s: %s from %s" % (
                    reaction['name'], ("x%d " % len(reaction['users'])) if len(reaction['users']) > 1 else '',
                    ", ".join("<@%s>" % user for user in reaction['users'])
                ) for reaction in msg['reactions'])
            )

        local_tz = tzlocal.get_localzone()
        message_local_dt = datetime.datetime.utcfromtimestamp(float(msg['ts'])) \
            .replace(tzinfo=pytz.utc) \
            .astimezone(local_tz)

        return self.templates[which].render(
            user=username,
            timestamp=message_local_dt.strftime("%I:%M %p"),
            avatar=self.avatars.get(username, None) if username not in self.redact_avatars else [],
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

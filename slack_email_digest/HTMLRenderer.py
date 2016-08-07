import datetime
import pprint
import re

import emoji
import jinja2
import pyshorteners

from .memoize import memoize1_to_json_file


TEMPLATES = {
    'header_text': """\
Slack Digest for {{ date }}{% if parts > 1 %} [Part {{ part + 1 }} of {{ parts }}]{% endif %}\
""",
    'full_html': """\
<div style="font-family: Slack-Lato,appleLogo,sans-serif; font-size: .9375rem; line-height: 1.375rem;">
<h2>{{ header_text }}</h2>
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

    'attachment': """\
{% if title -%}{% if service_icon -%}
            <img src="{{ service_icon }}" width=16>
        {%- endif %}{% if service_name -%}
            &nbsp;{{ service_name }}
        <br>{%- endif %}{% if title_link -%}
            <a href="{{ title_link }}">{%-
        endif %}<b>{{ title }}</b>{% if title_link -%}
            </a>
        {%- endif %}
    <br>{%- endif %}{% if text -%}
        {{ text }}<br>
    {%- endif %}
    {% if image_url -%}
        <img src="{{ image_url }}" width="{{ image_width }}" height="{{ image_height }}">
{%- endif -%}\
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
    def __init__(self, scraper, redact_users=None):
        """
        :param scraper: A SlackScraper to get channel names, user names, etc.
        :param redact_users: List of users to redact. Defaults to ['mailclark'] to avoid
            recursion.
        :param redact_avatars: List of users whose avatar not to include. Defaults to nobody.
        """
        self.redact_users = redact_users or ['mailclark']

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
                return '<img width="%s" src="%s" title="%s">' % (
                    32 if big else 20,
                    self.scraper.emojis[text[1:-1]],
                    text,
                )
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

        # multi-line blockquotes
        text = re.sub(r'&gt;&gt;&gt;(.*)', lambda m: '<blockquote>%s</blockquote>' % m.group(1), text,
                      flags=re.DOTALL)

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
        def sub_standard_emoji(m):
            text = m.group(1)
            subbed = emoji.emojize(text, use_aliases=True)
            if subbed != text:
                return "<span title='%s'>%s</span>" % (text, subbed)
            else:
                return text

        text = re.sub(r'(:[a-zA-Z0-9\+\-_&.ô’Åéãíç]+:)', sub_standard_emoji, text)

        # text = emoji.emojize(text, use_aliases=True)
        # custom emojis
        # nothing but whitespace - big emoji
        text = re.sub(r'^\W*(:[a-zA-Z0-9\+\-_&.ô’Åéãíç]+:)\W*$', lambda m: sub_custom_emoji(m, True), text)
        # otherwise, small emoji
        text = re.sub(r'(:[a-zA-Z0-9\+\-_&.ô’Åéãíç]+:)', sub_custom_emoji, text)

        return text

    def render_message(self, msg):
        """Render a message. Also recursively called with 'fake' messages to render attachments.
        :param msg: The message, from Slack, to render. Only difference from that returned
        by the Slack API is a potential '_override_username' parameter, which we use instead
        of looking up the user id.
        :return Text of the rendered message.
        """
        if '_override_username' in msg:
            username = msg['_override_username']
        elif 'user' in msg:
            username = self.scraper.get_username(msg['user'])
        elif 'bot_id' in msg:
            bot_username = msg['username'] if 'username' in msg else self.scraper.get_bot_name(msg['bot_id'])
            username = "%s (BOT)" % bot_username
        else:
            raise ValueError("Don't know how to handle this message:\n%s" % (pprint.pformat(msg),))

        text = msg['text']

        which = 'message'
        redact = False
        if msg.get('subtype') in ANNOUNCEMENT_TYPES:
            pass
        else:
            if username in self.redact_users:
                redact = True

        if redact:
            text = "<i>[redacted]</i>"

        # append reactions
        if msg.get('reactions'):
            text += "\n<span style='color: #777;'>(Reactions: %s)</span>" % (
                ", ".join(":%s: %s from %s" % (
                    reaction['name'], ("x%d " % len(reaction['users'])) if len(reaction['users']) > 1 else '',
                    ", ".join("<@%s>" % user for user in reaction['users'])
                ) for reaction in msg['reactions'])
            )

        message_utc_dt = datetime.datetime.utcfromtimestamp(float(msg['ts']))

        text = self.process_text(text)

        # attachments
        if redact:
            text += "<br><br><span style='color: #777'>Attachments redacted.</span>"
        else:
            for attachment in msg.get('attachments', []):
                attachment = dict(attachment)  # copy
                text += "<br><br><span style='color: #777'>Attachment:</span>"
                if attachment.get('is_msg_unfurl'):
                    text += "<blockquote>%s</blockquote>" % self.render_message({
                        'text': attachment['text'],
                        'ts': attachment['ts'],
                        'type': 'message',
                        '_override_username': attachment['author_subname'],
                    })
                else:
                    if 'text' in attachment.get('mrkdwn_in', []):
                        attachment['text'] = self.process_text(attachment['text'])
                    text += "<br>" + self.templates['attachment'].render(**attachment)

        return self.templates[which].render(
            user=username,
            timestamp=message_utc_dt.strftime("%I:%M %p"),
            avatar=self.avatars.get(username, None),  # bot users won't have an avatar
            text=text,
        )

    def render_header_text(self, messages, part=0, parts=1, date_hint=None):
        """Given a list of messages, render the appropriate header text.
        :param messages: List of slack messages to render.
        :param part: Which part of the total number of messages this is.
        :param parts: The total number of parts.
        :param date_hint: Date hint in case there are no messages
        :return: Text appropriate for the header/subject line
        """
        date_fmt = '%A, %B %d, %Y'

        if not messages:
            if not date_hint:
                raise ValueError("Can't get header text from no messages and no date hint")

            return self.templates['header_text'].render(date=date_hint.strftime(date_fmt), part=0, parts=1)

        # get boundary datetimes
        start_dt = datetime.datetime.utcfromtimestamp(min(float(msg['ts']) for msg in messages))
        end_dt = datetime.datetime.utcfromtimestamp(max(float(msg['ts']) - 1 for msg in messages))

        # format the boundaries
        start = start_dt.strftime(date_fmt)
        end = end_dt.strftime(date_fmt)

        # make the header
        if start == end:
            date_str = start
        else:
            date_str = "%s to %s" % (start, end)

        # add timezone
        date_str = "%s (UTC)" % (date_str,)

        return self.templates['header_text'].render(date=date_str, part=part, parts=parts)

    def render_messages(self, messages, part=0, parts=1):
        """Render messages.
        :param messages: List of slack messages to render.
        :param part: Which part of the total number of messages this is.
        :param parts: The total number of parts.
        :return HTML text of the rendered messages.
        """
        if not messages:
            return "<h2>There was no Slack activity</h2>"

        # format header
        header_text = self.render_header_text(messages, part=part, parts=parts)

        # render the messages
        message_bits = []
        last_ts = float(messages[0]['ts'])
        for msg in messages:
            # break up conversations
            if float(msg['ts']) - last_ts >= 30 * 60:
                message_bits.append("<hr>")
            last_ts = float(msg['ts'])

            message_bits.append(self.render_message(msg))

        # finalize
        return self.templates['full_html'].render(
            header_text=header_text,
            messages="\n".join(message_bits),
        )

import datetime
import pprint
import re

import emoji
import jinja2
import pyshorteners
import pytz

from .memoize import memoize1_to_json_file


TEMPLATES = {
    'header_text': """\
Slack Digest for {{ date }}{% if parts > 1 %} [Part {{ part + 1 }} of {{ parts }}]{% endif %}\
""",
    'full_html': """\
<div style="font-family: Slack-Lato,appleLogo,sans-serif; font-size: .9375rem; line-height: 1.375rem;">
<h2>{{ header_text }}</h2>
<h3><font color="#7f7f7f">\
(Click <a href="{{ visit_url }}">here</a> to view the chat live.\
{% if invite_url %} For an invite, click <a href="{{ invite_url }}">here</a>.{% endif %})</h3>
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
    # don't use <blockquote> as email clients don't show it nicely
    'blockquote': """\
<div style="margin: 10px 0px; padding: 5px 10px; border-left: 5px solid #ccc">{{ text }}</div>{{ after }}\
""",
    'bold': """\
<b>{{ text }}</b>{{ after }}\
""",
    'italic': """\
<i>{{ text }}</i>{{ after }}\
""",
    'strikethrough': """\
<strike>{{ text }}</strike>{{ after }}\
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
    def __init__(self, scraper, timezone, redact_users=None):
        """
        :param scraper: A SlackScraper to get channel names, user names, etc.
        :param timezone: Timezone info to render messages in
        :param redact_users: List of users to redact. Defaults to ['mailclark'] to avoid
            recursion.
        :param redact_avatars: List of users whose avatar not to include. Defaults to nobody.
        """
        self.redact_users = redact_users or ['mailclark']

        self.scraper = scraper
        self.timezone = timezone

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
        text = re.sub(r'^\W*&gt;&gt;&gt;(.*)()', sub_fmt('blockquote'), text, flags=re.DOTALL | re.MULTILINE)

        # multi-tick
        text = re.sub(r'```\n?(.*)```()', sub_fmt('pre'), text, flags=re.DOTALL)

        # bold
        text = re.sub(r'\*(\w[^\*]+)\*(\b|\W|$)', sub_fmt('bold'), text)
        # italic
        text = re.sub(r'_(\w[^_]+)_(\b|\W|$)', sub_fmt('italic'), text)
        # strike-through
        text = re.sub(r'~(\w[^~]+\w)~(\b|\W|$)', sub_fmt('strikethrough'), text)
        # tick
        text = re.sub(r'`(\w[^`]+)`(\b|\W|$)', sub_fmt('code'), text)

        # blockquotes
        text = re.sub(r"\n?^\W*&gt;(.*\w.*)\n?\n?()", sub_fmt('blockquote'), text, flags=re.MULTILINE)

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

        # first, standard emoji
        text = re.sub(r'(:[a-zA-Z0-9\+\-_&.ô’Åéãíç]+:)', sub_standard_emoji, text)

        # then, custom emojis
        # hackily replace colons in the title, so they don't get re-replaced
        # by an image later.
        HACKY_COLON_SUB = "---- pleaze < > forgive < > me ----04QQ!!!{{{"

        def sub_custom_emoji(m, big=False):
            text = m.group(1)
            if text[1:-1] in self.scraper.emojis:
                return '<img width="%s" src="%s" title="%s">' % (
                    32 if big else 20,
                    self.scraper.emojis[text[1:-1]],
                    text.replace(":", HACKY_COLON_SUB),
                )
            return text

        # nothing but whitespace - big emoji
        text = re.sub(r'^\W*(:[a-zA-Z0-9\+\-_&.ô’Åéãíç]+:)\W*$', lambda m: sub_custom_emoji(m, True), text)
        # otherwise, small emoji
        text = re.sub(r'(:[a-zA-Z0-9\+\-_&.ô’Åéãíç]+:)', sub_custom_emoji, text)

        # fix the colon preserving hack
        text = text.replace(HACKY_COLON_SUB, ":")

        return text

    def _render_reactions(self, reactions, text="Reactions"):
        if not reactions:
            return ""

        # use process_text to help with the emojis
        return "<span style='color: #777;'>(%s: %s)</span>" % (
            text, self.process_text(
                ", ".join(":%s: %s from %s" % (
                    reaction['name'], ("x%d " % len(reaction['users'])) if len(reaction['users']) > 1 else '',
                    ", ".join("<@%s>" % user for user in reaction['users'])
                ) for reaction in reactions)
            )
        )

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
        elif msg.get('subtype') == 'file_comment':
            username = self.scraper.get_username(msg['comment']['user'])
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

        # process markdown
        if redact:
            text = "<i>[redacted]</i>"
        else:
            text = self.process_text(text)

        # append reactions
        reactions = msg.get('reactions')
        if msg.get('subtype') == 'file_comment':
            reactions = msg['comment'].get('reactions')
        if reactions:
            text += "<br>" + self._render_reactions(reactions)

        # file share, append preview
        if msg.get('subtype') == 'file_share' and msg['file'].get('preview'):
            if redact:
                text += "<br><br><span style='color: #777'>File preview redacted.</span>"
            else:
                text += "<br><br><span style='color: #777'>File preview:</span><br>%s" % (
                    self.templates['blockquote'].render(text=msg['file']['preview']),
                )
                text += self._render_reactions(msg['file'].get('reactions'), "File reactions")

        # attachments
        if redact:
            text += "<br><br><span style='color: #777'>Attachments redacted.</span>"
        else:
            for attachment in msg.get('attachments', []):
                attachment = dict(attachment)  # copy
                text += "<br><br><span style='color: #777'>Attachment:</span>"
                if attachment.get('is_msg_unfurl'):
                    # render messages as blockquotes
                    text += self.templates['blockquote'].render(text=self.render_message({
                        'text': attachment['text'],
                        'ts': attachment['ts'],
                        'type': 'message',
                        '_override_username': attachment['author_subname'],
                    }))
                else:
                    if 'text' in attachment.get('mrkdwn_in', []):
                        attachment['text'] = self.process_text(attachment['text'])
                    text += "<br>" + self.templates['attachment'].render(**attachment)

        # render template
        message_utc_dt = datetime.datetime.utcfromtimestamp(float(msg['ts']))
        message_dt = pytz.utc.localize(message_utc_dt).astimezone(self.timezone)
        return self.templates[which].render(
            user=username,
            timestamp=message_dt.strftime("%I:%M %p"),
            avatar=self.avatars.get(username, None),  # bot users won't have an avatar
            text=text,
        )

    def render_header_text(self, messages, part=0, parts=1, date_hint=None,
                           short=False):
        """Given a list of messages, render the appropriate header text.
        :param messages: List of slack messages to render.
        :param part: Which part of the total number of messages this is.
        :param parts: The total number of parts.
        :param date_hint: Date hint in case there are no messages
        :param short: If short, provide a shortened header, as suitable for
            a subject line in an email.
        :return: Text appropriate for the header/subject line
        """
        date_fmt = '%B %d, %Y' if short else '%A, %B %d, %Y'

        if not messages:
            if not date_hint:
                raise ValueError("Can't get header text from no messages and no date hint")

            return self.templates['header_text'].render(date=date_hint.strftime(date_fmt), part=0, parts=1)

        # get boundary datetimes
        start_dt = datetime.datetime.utcfromtimestamp(min(float(msg['ts']) for msg in messages))
        start_dt = pytz.utc.localize(start_dt).astimezone(self.timezone)
        end_dt = datetime.datetime.utcfromtimestamp(max(float(msg['ts']) - 1 for msg in messages))
        end_dt = pytz.utc.localize(end_dt).astimezone(self.timezone)

        # format the boundaries
        start = start_dt.strftime(date_fmt)
        end = end_dt.strftime(date_fmt)

        # make the header
        if start == end:
            date_str = start
        else:
            date_str = "%s to %s" % (start, end)

        # add timezone
        date_str = "%s (%s)" % (date_str, start_dt.strftime("%Z"))

        return self.templates['header_text'].render(date=date_str, part=part, parts=parts)

    def render_messages(self, messages, part=0, parts=1):
        """Render messages.
        :param messages: List of slack messages to render.
        :param part: Which part of the total number of messages this is.
        :param parts: The total number of parts.
        :return HTML text of the rendered messages.
        """
        if not messages:
            header_text = "There was no Slack activity"
            message_bits = []
        else:
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

                try:
                    this_bit = self.render_message(msg)
                except Exception as e:
                    import traceback
                    print("ERROR handling message!\n%s" % (traceback.format_exc()))
                    this_bit = "&lt;ERROR HANDLING MESSAGE -- please alert your local programmer!&gt;<br>%s" % (
                        self.templates['pre'].render(text=traceback.format_exc()
                            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                                                     ),
                    )
                    # format it as a message
                    this_bit = self.templates['message'].render(
                        user="ERROR",
                        text=this_bit,
                    )

                message_bits.append(this_bit)

        # finalize
        return self.templates['full_html'].render(
            header_text=header_text,
            messages="\n".join(message_bits),
            visit_url="https://%s.slack.com" % self.scraper.get_team_subdomain(),
            invite_url=self.scraper.get_invite_link(),
        )

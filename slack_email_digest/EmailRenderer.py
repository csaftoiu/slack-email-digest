import time

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def n_even_chunks(l, n):
    """Yield n as even chunks as possible from l."""
    last = 0
    for i in range(1, n+1):
        cur = int(round(i * (len(l) / n)))
        yield l[last:cur]
        last = cur


class EmailRenderer:
    """Use an HTMLRenderer to render emails.
    """
    def __init__(self, message_renderer, max_email_size=64000):
        """:param message_renderer: renderer to use to render the
            messages, e.g. an HTMLRenderer instance.
        :param max_email_size Maximum email size to allow in one email
        """
        self.renderer = message_renderer
        self.max_email_size = max_email_size

    @classmethod
    def estimate_email_size(cls, html_body, text_body, header_size=4500):
        """Estimate how many bytes an email will take.
        :param html_body: HTML body to send
        :param text_body: Text body to send
        :param header_size: Number of bytes to allow for the headers.
        """
        msg = MIMEMultipart('alternative')

        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))

        return len(msg.as_string()) + header_size

    def _render_message_part(self, part_messages, part_i, num_parts):
        header_text = self.renderer.render_header_text(part_messages, part=part_i, parts=num_parts)
        html = self.renderer.render_messages(part_messages, part=part_i)

        # subject should have no special characters
        subject = text_body = header_text.encode('ascii').decode('ascii')
        # xmlcharref-encode everything to avoid encoding issues
        html_body = html.encode('ascii', 'xmlcharrefreplace').decode('ascii')

        return {
            # encode with ascii & xml char refs to avoid encoding issues
            'subject': subject,
            'html_body': html_body,
            # fall back on the header text only, this displays nicely if the mail client
            # uses this text for a snippet, and doesn't take up much space
            'text_body': text_body,
            'custom_headers': {},
        }

    def _render_messages_in_parts(self, messages, num_parts):
        """Render messages into given number of parts."""
        return [self._render_message_part(part_messages, part_i, num_parts)
                for part_i, part_messages in enumerate(n_even_chunks(messages, num_parts))]

    def render_digest_emails(self, messages, in_reply_to=None, last_message_id=None):
        """Render digest emails for the given messages. Return format is a dict which
        can be used to construct the email messages.

        This estimates and splits messages into multiple emails such that no email
        is likely to be larger than the max email size.

        :param messages: List of Slack messages
        :param in_reply_to: If given, first message will be In-Reply-To this.
        :param last_message_id: If given, the last message will have this Message-ID.
        """
        if not messages:
            raise NotImplementedError("No messages NYI")

        # split into evenly-sized chunks until all are under the size limit
        num_parts = 0
        parts = []
        while True:
            num_parts += 1
            if num_parts > len(messages):
                raise ValueError("Have one too-large message, cannot split further")

            parts = self._render_messages_in_parts(messages, num_parts)
            # estimate, decoding with ascii should work as per how messages are rendered
            if all(self.estimate_email_size(part['html_body'],
                                            part['text_body']) <= self.max_email_size
                   for part in parts):
                break

        # chain the messages so they reply to each other
        if in_reply_to:
            parts[0]['custom_headers']['In-Reply-To'] = in_reply_to

        # inner IDs don't matter, keep them unique
        now = int(time.time())
        for i, part in enumerate(parts):
            part['custom_headers']['Message-ID'] = '<digest-%d-part%d@slackemaildigest.com>' % (
                now, i,
            )
            if i > 0:
                part['custom_headers']['In-Reply-To'] = '<digest-%d-part%d@slackemaildigest.com>' % (
                    now, i - 1,
                )

        if last_message_id:
            parts[-1]['custom_headers']['Message-ID'] = last_message_id

        return parts

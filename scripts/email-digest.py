import os
import time

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib


SIZE_LIMIT = 64000


def send_digest(user, pwd, subject, recipient, digest, fallback_text):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = user
    msg['To'] = recipient

    msg.attach(MIMEText(fallback_text, 'plain'))
    msg.attach(MIMEText(digest, 'html'))

    message_body = msg.as_string()
    print("Message is %.2f kB" % (len(message_body) / 1024.0))
    if len(message_body) > SIZE_LIMIT:
        raise ValueError("Message exceeds size limit size of 64000 bytes")

    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.ehlo()
    server.starttls()
    server.login(user, pwd)
    server.sendmail(user, recipient, msg.as_string())
    server.close()


def main():
    prefix = 'digest'

    parts = []
    part_i = 0
    while True:
        fn = '%s-part%d.html' % (prefix, part_i)
        if not os.path.exists(fn):
            break
        parts.append(fn)
        part_i += 1

    for part_i, fn in enumerate(parts):
        if part_i > 0:
            print("Sleeping before sending next message..")
            time.sleep(20)

        print("Mailing %s (part %d of %d)..." % (fn, part_i + 1, len(parts)))

        subject = 'Slack Digest for August 02, 2016 (PDT)'
        if len(parts) > 1:
            subject += " [Part %d of %d]" % (part_i + 1, len(parts))

        send_digest(
            'csaftoiu@gmail.com', open('gmail_app_pwd', 'r').read().strip(),
            subject,
            # 'actualfreedom@yahoogroups.com',
            'csaftoiu@gmail.com',
            open(fn).read(),
            # mail client may use this to show snippet text, so just place the subject here for the
            # alternative text. It's not a true fallback but ah well
            subject,
        )


if __name__ == "__main__":
    main()

import os
import smtplib
import ssl
import re
from email.message import EmailMessage
from email.utils import make_msgid

def send_email(to: str, subject: str, body: str, bcc_self: bool = True, in_reply_to: str = None) -> str:
    msg = EmailMessage()
    msg["From"] = os.environ["GMAIL_USER"]
    msg["To"] = to
    if bcc_self:
        msg["Bcc"] = os.environ["GMAIL_USER"]
    msg["Subject"] = subject

    new_msg_id = make_msgid()
    msg["Message-ID"] = new_msg_id

    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to

    msg.set_content(body)

    html_body = body.replace('\n\n', '<br><br>').replace('\n', '<br>')
    url_pattern = re.compile(r'((?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}(?:/[^\s]*)?)')
    
    def replace_url(match):
        url = match.group(1)
        if '@' in url:
            return url
        trailing = ""
        while url and url[-1] in ".,;:!?()[]{}":
            trailing = url[-1] + trailing
            url = url[:-1]
        return f'<a href="https://{url}">{url}</a>{trailing}'
        
    html_body = url_pattern.sub(replace_url, html_body)
    msg.add_alternative(html_body, subtype='html')

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)
        
    return new_msg_id
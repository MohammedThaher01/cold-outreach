import os
import smtplib
import ssl
import re
from email.message import EmailMessage

def send_email(to: str, subject: str, body: str, bcc_self: bool = True) -> None:
    msg = EmailMessage()
    msg["From"] = os.environ["GMAIL_USER"]
    msg["To"] = to
    if bcc_self:
        msg["Bcc"] = os.environ["GMAIL_USER"]
    msg["Subject"] = subject

    # 1. Plain text version (fallback)
    msg.set_content(body)

    # 2. HTML version (guarantees clickable links)
    html_body = body.replace('\n\n', '<br><br>').replace('\n', '<br>')
    
    url_pattern = re.compile(r'((?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}(?:/[^\s]*)?)')
    
    def replace_url(match):
        url = match.group(1)
        if '@' in url:
            return url
            
        # THE FIX: Strip trailing punctuation from the URL
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
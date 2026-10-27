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
    # Replace newlines with HTML breaks
    html_body = body.replace('\n\n', '<br><br>').replace('\n', '<br>')
    
    # Regex to find bare URLs (like trendly-agent-1.onrender.com/ui or your modulify link)
    url_pattern = re.compile(r'((?:[a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}(?:/[^\s]*)?)')
    
    def replace_url(match):
        url = match.group(1)
        # Ignore email addresses (they have an @ symbol)
        if '@' in url:
            return url
        # Wrap in an <a> tag with https:// so it becomes a blue hyperlink
        return f'<a href="https://{url}">{url}</a>'
        
    # Apply the link replacement
    html_body = url_pattern.sub(replace_url, html_body)
    
    # Add the HTML version to the email
    msg.add_alternative(html_body, subtype='html')

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)
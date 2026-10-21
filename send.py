import os
import smtplib
import ssl
from email.message import EmailMessage


def send_email(to: str, subject: str, body: str, bcc_self: bool = True) -> None:
    msg = EmailMessage()
    msg["From"] = os.environ["GMAIL_USER"]
    msg["To"] = to
    if bcc_self:
        msg["Bcc"] = os.environ["GMAIL_USER"]
    msg["Subject"] = subject
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ctx) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)
from email.mime.text import MIMEText
import smtplib


def send_email(to, sender, subject, body, host='localhost'):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to
    s = smtplib.SMTP(host)
    s.sendmail(sender, [to], msg.as_string())
    s.quit()

"""
Email service — sends via SmtpSettings stored in the database.

Usage:
    from core.services.email import send_email, send_invitation
    send_email(to='user@example.com', subject='Hello', body='Plain text body')
    send_invitation(to='user@example.com', username='alice', password='s3cr3t', login_url='https://…/login/', app_name='Job Tracker')
"""
from django.core.mail import EmailMultiAlternatives, get_connection


def send_email(to, subject, body='', html_body=None):
    """
    Send an email using SMTP settings from the database.

    Args:
        to: str or list of recipient addresses
        subject: email subject
        body: plain-text body (used as fallback when html_body is provided)
        html_body: optional HTML body; if provided, sent as text/html with body as text/plain alternative

    Raises:
        ValueError: if SMTP is not enabled
        smtplib.SMTPException / socket errors: on connection/send failure
    """
    from core.models import SmtpSettings
    smtp = SmtpSettings.get()
    if not smtp.is_enabled:
        raise ValueError("SMTP is not enabled. Configure it under Settings > SMTP.")

    if isinstance(to, str):
        to = [to]

    connection = get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=smtp.host,
        port=smtp.port,
        username=smtp.username,
        password=smtp.password,
        use_tls=smtp.use_tls,
        use_ssl=smtp.use_ssl,
        fail_silently=False,
    )

    from_email = smtp.sender
    msg = EmailMultiAlternatives(
        subject=subject,
        body=body or (html_body or ''),
        from_email=from_email,
        to=to,
        connection=connection,
    )
    if html_body:
        msg.attach_alternative(html_body, 'text/html')

    msg.send()


def send_magic_link(to, magic_url, app_name='Job Tracker', expiry_minutes=15):
    """Send a magic login link email."""
    subject = f"Your {app_name} login link"

    plain = (
        f"Hi,\n\n"
        f"Click the link below to log in to {app_name}. "
        f"This link expires in {expiry_minutes} minutes and can only be used once.\n\n"
        f"  {magic_url}\n\n"
        f"If you did not request this, you can safely ignore this email.\n"
    )

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;color:#333;max-width:520px;margin:0 auto;padding:24px;">
  <h2 style="color:#0d6efd;margin-bottom:4px;">Log in to {app_name}</h2>
  <p>Click the button below to sign in. This link expires in <strong>{expiry_minutes} minutes</strong> and can only be used once.</p>
  <p style="text-align:center;margin:32px 0;">
    <a href="{magic_url}"
       style="background:#0d6efd;color:#fff;text-decoration:none;padding:12px 28px;border-radius:6px;font-size:16px;display:inline-block;">
      Sign In
    </a>
  </p>
  <p style="font-size:13px;color:#6c757d;">
    Or copy this link into your browser:<br>
    <a href="{magic_url}" style="color:#0d6efd;word-break:break-all;">{magic_url}</a>
  </p>
  <p style="margin-top:20px;font-size:13px;color:#6c757d;">
    If you did not request this, you can safely ignore this email.<br>
    This message was sent automatically — do not reply.
  </p>
</body>
</html>"""

    send_email(to=to, subject=subject, body=plain, html_body=html)


def send_invitation(to, username, password, login_url, app_name='Job Tracker'):
    """Send a welcome / credential email to a newly created user."""
    subject = f"Your {app_name} account is ready"

    plain = (
        f"Welcome to {app_name}!\n\n"
        f"Your account has been created. Here are your login details:\n\n"
        f"  Login URL : {login_url}\n"
        f"  Username  : {username}\n"
        f"  Password  : {password}\n\n"
        f"Please change your password after your first login.\n"
    )

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;color:#333;max-width:520px;margin:0 auto;padding:24px;">
  <h2 style="color:#0d6efd;margin-bottom:4px;">Welcome to {app_name}</h2>
  <p>Hi <strong>{username}</strong>,</p>
  <p>Your account has been created. Use the credentials below to sign in.</p>
  <table style="background:#f8f9fa;border-radius:8px;padding:16px 20px;width:100%;border-collapse:collapse;">
    <tr>
      <td style="padding:6px 12px 6px 0;white-space:nowrap;"><strong>Login URL</strong></td>
      <td style="padding:6px 0;"><a href="{login_url}">{login_url}</a></td>
    </tr>
    <tr>
      <td style="padding:6px 12px 6px 0;"><strong>Username</strong></td>
      <td style="padding:6px 0;font-family:monospace;">{username}</td>
    </tr>
    <tr>
      <td style="padding:6px 12px 6px 0;"><strong>Password</strong></td>
      <td style="padding:6px 0;font-family:monospace;">{password}</td>
    </tr>
  </table>
  <p style="margin-top:20px;font-size:13px;color:#6c757d;">
    Please change your password after your first login.<br>
    This message was sent automatically — do not reply.
  </p>
</body>
</html>"""

    send_email(to=to, subject=subject, body=plain, html_body=html)

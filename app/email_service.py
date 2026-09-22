import logging
import smtplib
from email.message import EmailMessage

from .config import settings

logger = logging.getLogger("recipebox")


def send_verification_email(to_email: str, full_name: str, raw_token: str) -> None:
    """Sends (or, in dev, logs) an email verification link. The link
    format is EMAIL_VERIFICATION_BASE_URL?token=<raw_token> — your
    frontend (or a deep link handler) reads that query param and calls
    POST /auth/verify-email with it."""
    verify_url = f"{settings.EMAIL_VERIFICATION_BASE_URL}?token={raw_token}"
    subject = "Verify your Recipe Box email"
    body = (
        f"Hi {full_name},\n\n"
        f"Confirm your email to finish setting up Recipe Box:\n{verify_url}\n\n"
        f"This link expires in {settings.EMAIL_VERIFICATION_EXPIRE_HOURS} hours.\n"
        f"If you didn't create this account, you can ignore this email."
    )

    if settings.EMAIL_BACKEND == "smtp":
        _send_smtp(to_email, subject, body)
    else:
        # Console backend — good enough for local dev so you can copy the
        # link straight out of the server log without real mail infra.
        logger.info("=== VERIFICATION EMAIL (console backend) ===")
        logger.info("To: %s", to_email)
        logger.info("Subject: %s", subject)
        logger.info("%s", body)
        logger.info("=============================================")


def _send_smtp(to_email: str, subject: str, body: str) -> None:
    if not settings.SMTP_HOST:
        logger.warning("EMAIL_BACKEND=smtp but SMTP_HOST is not set — email not sent.")
        return

    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(msg)

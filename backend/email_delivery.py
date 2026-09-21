"""Transactional verification messages via Brevo; secrets stay server-side."""
import json
import os
from urllib import error, request


def configured():
    return bool(os.getenv('BREVO_API_KEY') and os.getenv('HAVENLY_MAIL_FROM'))


def send_code(destination: str, code: str, purpose: str):
    if not configured():
        raise RuntimeError('Email delivery is not configured. Set BREVO_API_KEY and HAVENLY_MAIL_FROM on the server.')
    labels = {
        'signup': 'Verify your Havenly sign-up',
        'reset': 'Reset your Havenly password',
        'change_password': 'Confirm your Havenly password change',
        'change_email_old': 'Approve your Havenly email change',
        'change_email_new': 'Verify your new Havenly email address',
    }
    payload = json.dumps({
        'sender': {'email': os.environ['HAVENLY_MAIL_FROM'], 'name': 'Havenly'},
        'to': [{'email': destination}],
        'subject': labels[purpose],
        'textContent': f'Your Havenly verification code is {code}. It expires in 10 minutes. If you did not request this, ignore this email.',
    }).encode()
    req = request.Request('https://api.brevo.com/v3/smtp/email', data=payload, headers={
        'api-key': os.environ['BREVO_API_KEY'], 'content-type': 'application/json', 'accept': 'application/json',
    }, method='POST')
    try:
        with request.urlopen(req, timeout=12) as response:
            if response.status not in (200, 201, 202):
                raise RuntimeError('Email provider rejected the request.')
    except (error.HTTPError, error.URLError, TimeoutError) as exc:
        raise RuntimeError('Could not send the verification email. Check the sender and provider configuration.') from exc

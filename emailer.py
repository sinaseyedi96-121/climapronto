"""
Email sending via Resend (https://resend.com)
=============================================
Free tier: 3,000 emails/month, 100/day — more than enough to launch.

SETUP (5 minutes):
  1. Create a free account at resend.com
  2. Dashboard -> API Keys -> Create API Key -> copy it
  3. Set it as an environment variable:  RESEND_API_KEY
  4. TESTING: with no domain verified, Resend only lets you send FROM
     "onboarding@resend.dev" TO the email address of your own Resend
     account. Perfect for testing the pipeline.
  5. PRODUCTION: buy the domain (e.g. climapronto.it), add it in
     Resend -> Domains, set the DNS records they show you, then change
     FROM_ADDRESS below to e.g. "ClimaPronto <avvisi@climapronto.it>".
"""

import os

import requests

# ----------------------------------------------------------------------
# CONFIG
# ----------------------------------------------------------------------
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_ENDPOINT = "https://api.resend.com/emails"

# Testing value. After verifying your domain in Resend, change to:
# FROM_ADDRESS = "ClimaPronto <avvisi@climapronto.it>"
FROM_ADDRESS = "ClimaPronto <onboarding@resend.dev>"

SITE_URL = "https://climapronto.netlify.app"  # update after you deploy
# ----------------------------------------------------------------------


def send_restock_email(to_email: str, product: dict) -> None:
    """Send the 'it's back in stock' email. Raises on failure."""
    if not RESEND_API_KEY:
        raise RuntimeError("RESEND_API_KEY environment variable is not set")

    subject = f"🟢 Tornato disponibile: {product['name']}"

    html = f"""
    <div style="font-family:Arial,Helvetica,sans-serif;max-width:520px;margin:0 auto;color:#10222E">
      <h2 style="letter-spacing:-0.02em">È tornato disponibile!</h2>
      <p style="font-size:16px;line-height:1.5">
        <strong>{product['name']}</strong><br>
        {product['retailer']}{' · ' + product['price'] if product.get('price') else ''}
      </p>
      <p style="font-size:15px;line-height:1.5;color:#5E7480">
        Lo stock potrebbe esaurirsi di nuovo in poche ore: ti consigliamo di
        completare l'acquisto il prima possibile.
      </p>
      <p style="margin:28px 0">
        <a href="{product['url']}"
           style="background:#10222E;color:#fff;text-decoration:none;
                  padding:14px 28px;border-radius:99px;font-weight:bold;display:inline-block">
          Vai al prodotto →
        </a>
      </p>
      <hr style="border:none;border-top:1px solid #DCE6EA;margin:28px 0">
      <p style="font-size:12px;color:#8CA0AB">
        Ricevi questa email perché hai attivato un avviso su
        <a href="{SITE_URL}" style="color:#2E9DBB">ClimaPronto</a>.
        Per non ricevere più avvisi, rispondi a questa email con "STOP".
      </p>
    </div>
    """

    resp = requests.post(
        RESEND_ENDPOINT,
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": FROM_ADDRESS,
            "to": [to_email],
            "subject": subject,
            "html": html,
        },
        timeout=20,
    )
    resp.raise_for_status()

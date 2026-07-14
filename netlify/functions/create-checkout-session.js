// Creates a Stripe Checkout session when someone clicks "Attiva avviso".
// Called by the website via POST /api/create-checkout-session.
// Runs on Netlify (serverless), NOT on the Oracle VM / GitHub Actions.

const Stripe = require('stripe');
const stripe = Stripe(process.env.STRIPE_SECRET_KEY);

// ----------------------------------------------------------------------
// CONFIG — the price lives here, not in the Stripe dashboard, so it's a
// one-line change. No Stripe "Product" needs to be pre-created.
// ----------------------------------------------------------------------
const ALERT_PRICE_CENTS = 490;   // 4,90 €
const CURRENCY = 'eur';
// ----------------------------------------------------------------------

exports.handler = async (event) => {
  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, body: 'Method not allowed' };
  }

  let body;
  try {
    body = JSON.parse(event.body);
  } catch {
    return { statusCode: 400, body: JSON.stringify({ error: 'Invalid JSON' }) };
  }

  const { productId, productName } = body;
  if (!productId) {
    return { statusCode: 400, body: JSON.stringify({ error: 'productId is required' }) };
  }

  const siteUrl = process.env.SITE_URL || `https://${event.headers.host}`;

  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      line_items: [{
        price_data: {
          currency: CURRENCY,
          unit_amount: ALERT_PRICE_CENTS,
          product_data: {
            name: `Avviso disponibilità — ${productName || productId}`,
            description: "Ti scriviamo via email non appena questo prodotto torna disponibile.",
          },
        },
        quantity: 1,
      }],
      // Stripe's hosted page asks for the email itself — no need to
      // collect it on our own form.
      metadata: { product_id: productId },
      success_url: `${siteUrl}/grazie.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${siteUrl}/#avvisi`,
    });

    return { statusCode: 200, body: JSON.stringify({ url: session.url }) };
  } catch (err) {
    console.error('create-checkout-session error:', err);
    return { statusCode: 500, body: JSON.stringify({ error: 'Impossibile avviare il pagamento.' }) };
  }
};

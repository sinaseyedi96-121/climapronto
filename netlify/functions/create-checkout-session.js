// Creates a Stripe Checkout session when someone clicks "Attiva avviso".
// Called by the website via POST /api/create-checkout-session.
// Runs on Netlify (serverless), NOT on the Oracle VM / GitHub Actions.

const Stripe = require('stripe');
const stripe = Stripe(process.env.STRIPE_SECRET_KEY);

// ----------------------------------------------------------------------
// CONFIG — prices live here, not in the Stripe dashboard, so they're a
// one-line change. No Stripe "Product" needs to be pre-created.
// ----------------------------------------------------------------------
const CURRENCY = 'eur';
const PLANS = {
  week:      { days: 7,  cents: 290, label: '1 settimana' },
  month:     { days: 30, cents: 590, label: '1 mese' },
  twomonths: { days: 60, cents: 890, label: '2 mesi' },
};
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

  const { productId, productName, plan, email } = body;
  if (!productId) {
    return { statusCode: 400, body: JSON.stringify({ error: 'productId is required' }) };
  }
  const chosenPlan = PLANS[plan];
  if (!chosenPlan) {
    return { statusCode: 400, body: JSON.stringify({ error: 'plan non valido' }) };
  }

  const siteUrl = process.env.SITE_URL || `https://${event.headers.host}`;

  try {
    const session = await stripe.checkout.sessions.create({
      mode: 'payment',
      line_items: [{
        price_data: {
          currency: CURRENCY,
          unit_amount: chosenPlan.cents,
          product_data: {
            name: `Avvisi disponibilità (${chosenPlan.label}) — ${productName || productId}`,
            description: "Ti scriviamo via email ogni volta che questo prodotto torna disponibile, per la durata del piano scelto.",
          },
        },
        quantity: 1,
      }],
      // Prefill the email if we already collected it on our own page —
      // still shown/editable on Stripe's hosted page, just not asked twice.
      ...(email ? { customer_email: email } : {}),
      metadata: { product_id: productId, plan, days: String(chosenPlan.days) },
      success_url: `${siteUrl}/grazie.html?session_id={CHECKOUT_SESSION_ID}`,
      cancel_url: `${siteUrl}/avvisi.html`,
    });

    return { statusCode: 200, body: JSON.stringify({ url: session.url }) };
  } catch (err) {
    console.error('create-checkout-session error:', err);
    return { statusCode: 500, body: JSON.stringify({ error: 'Impossibile avviare il pagamento.' }) };
  }
};

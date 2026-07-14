// Stripe calls this after a successful payment. It verifies the payment
// is genuine, then appends the subscriber to data/subscribers.json IN THE
// GITHUB REPO (via the GitHub API) — the crawler reads that file directly
// on its next run. Same "state lives as committed JSON" pattern used for
// stock.json, just written by a different actor.
//
// SETUP: Stripe Dashboard -> Developers -> Webhooks -> Add endpoint
//   URL:    https://<your-site>.netlify.app/.netlify/functions/stripe-webhook
//   Events: checkout.session.completed
// Copy the "Signing secret" it gives you into STRIPE_WEBHOOK_SECRET.

const Stripe = require('stripe');
const stripe = Stripe(process.env.STRIPE_SECRET_KEY);

// ----------------------------------------------------------------------
// CONFIG
// ----------------------------------------------------------------------
const GITHUB_REPO = process.env.GITHUB_REPO;   // e.g. "sinaseyedi96-121/climapronto"
const GITHUB_TOKEN = process.env.GITHUB_TOKEN; // fine-grained PAT, Contents: Read & write, this repo only
const SUBSCRIBERS_PATH = 'data/subscribers.json';
// ----------------------------------------------------------------------

exports.handler = async (event) => {
  const signature = event.headers['stripe-signature'];
  let stripeEvent;

  try {
    stripeEvent = stripe.webhooks.constructEvent(
      event.body,
      signature,
      process.env.STRIPE_WEBHOOK_SECRET
    );
  } catch (err) {
    console.error('Signature verification failed:', err.message);
    return { statusCode: 400, body: `Webhook Error: ${err.message}` };
  }

  if (stripeEvent.type !== 'checkout.session.completed') {
    return { statusCode: 200, body: 'ignored (not a completed checkout)' };
  }

  const session = stripeEvent.data.object;
  const email = session.customer_details?.email || session.customer_email;
  const productId = session.metadata?.product_id;

  if (!email || !productId) {
    console.error('Completed session missing email or product_id:', session.id);
    return { statusCode: 200, body: 'ignored (missing data)' };
  }

  try {
    await addSubscriber(email, productId);
    return { statusCode: 200, body: 'ok' };
  } catch (err) {
    console.error('Failed to record subscriber:', err);
    // Return 500 so Stripe retries the webhook automatically.
    return { statusCode: 500, body: 'failed to record subscriber' };
  }
};

async function addSubscriber(email, productId) {
  const apiUrl = `https://api.github.com/repos/${GITHUB_REPO}/contents/${SUBSCRIBERS_PATH}`;
  const headers = {
    Authorization: `Bearer ${GITHUB_TOKEN}`,
    Accept: 'application/vnd.github+json',
  };

  // 1. Read the current file (need its sha to update it; 404 = doesn't exist yet)
  const getRes = await fetch(apiUrl, { headers });
  let subscribers = [];
  let sha;
  if (getRes.status === 200) {
    const file = await getRes.json();
    sha = file.sha;
    subscribers = JSON.parse(Buffer.from(file.content, 'base64').toString('utf-8'));
  } else if (getRes.status !== 404) {
    throw new Error(`GitHub GET failed: ${getRes.status}`);
  }

  subscribers.push({
    email: email.toLowerCase().trim(),
    prodotto: productId,
    paid_at: new Date().toISOString(),
  });

  // 2. Write it back (create or update)
  const putRes = await fetch(apiUrl, {
    method: 'PUT',
    headers: { ...headers, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: `alert paid: ${email} -> ${productId}`,
      content: Buffer.from(JSON.stringify(subscribers, null, 2)).toString('base64'),
      sha, // omit-if-undefined is fine — GitHub treats missing sha as "create new"
    }),
  });

  if (!putRes.ok) {
    throw new Error(`GitHub PUT failed: ${putRes.status} ${await putRes.text()}`);
  }
}

#!/bin/bash
# ======================================================================
# Oracle VM runner — called by cron every 10 minutes (see README.md).
# Runs the crawler, then pushes the updated data/ files to GitHub so
# the Netlify site (which reads stock.json from raw.githubusercontent.com)
# shows fresh data.
#
# ONE-TIME SETUP ON THE VM:
#   git clone https://github.com/sinaseyedi96-121/climapronto.git
#   cd climapronto
#   pip3 install -r requirements.txt --break-system-packages
#   nano .env            # put the keys here (see .env.example)
#   chmod +x run_and_push.sh
#   crontab -e           # add:  */10 * * * * /home/ubuntu/climapronto/run_and_push.sh >> /home/ubuntu/climapronto/cron.log 2>&1
#
# For pushing, store a GitHub token once:
#   git config credential.helper store
#   git push   # it asks for username + token (a fine-grained PAT with
#              # contents:write on this repo) once, then remembers it.
# ======================================================================

set -e
cd "$(dirname "$0")"

# load API keys
set -a
source .env
set +a

# make sure we're not fighting a stale local state
git pull --rebase --quiet

python3 crawler.py

git add data/
if ! git diff --cached --quiet; then
  git commit -m "stock update $(date -u +'%Y-%m-%d %H:%M')" --quiet
  git push --quiet
fi

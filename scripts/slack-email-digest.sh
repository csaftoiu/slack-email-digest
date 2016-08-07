#!/bin/sh -e

echo "Running slack-email-digest.py with from=${SLACKEMAILDIGEST_FROM} to=${SLACKEMAILDIGEST_TO} delivery=${SLACKEMAILDIGEST_DELIVERY}"

python scripts/slack-email-digest.py \
    --from="${SLACKEMAILDIGEST_FROM}" \
    --to="${SLACKEMAILDIGEST_TO}" \
    --token "${SLACKEMAILDIGEST_TOKEN}" \
    --delivery=${SLACKEMAILDIGEST_DELIVERY}

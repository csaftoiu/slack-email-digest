#!/bin/sh -xe

python scripts/slack-email-digest.py --from="${SLACKEMAILDIGEST_FROM}" --to="${SLACKEMAILDIGEST_TO}" --token "${SLACKEMAILDIGEST_TOKEN}" --delivery=${SLACKEMAILDIGEST_DELIVERY}
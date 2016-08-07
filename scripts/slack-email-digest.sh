#!/bin/sh -xe

python scripts/slack-email-digest.py -v --from=${SLACKEMAILDIGEST_FROM} --to=${SLACKEMAILDIGEST_TO} --token ${SLACKEMAILDIGEST_TOKEN} --delivery=stdout
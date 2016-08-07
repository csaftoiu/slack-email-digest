# slack-email-digest

Summarize Slack chat history into an email digest.

## Local setup

Install Python 3 and then run:

```
venv ./myenv
./myenv/bin/python setup.py develop
```

### Troubleshooting

- If you receive [SSL errors](https://github.com/kennethreitz/requests/issues/3011#issuecomment-183626795) on OSX, try installing Python 3 from Homebrew. 

## Deploying to Heroku

Create and deploy the app:

```
heroku create my-app-name
git push heroku master
```

Add the following add-ons:

1. Postmark
1. Heroku Scheduler
1. Papertrail (optional)

Set the following config vars

1. SLACKEMAILDIGEST_DELIVERY=delivery
1. SLACKEMAILDIGEST_FROM=<sender@yourdomain.com>
1. SLACKEMAILDIGEST_TO=<receiver@theirdomain.com>
1. SLACKEMAILDIGEST_TOKEN=<slack-test-api-token> ([Test token](https://api.slack.com/docs/oauth-test-tokens))

Open the Heroku Scheduler add-on from your app dashboard and add a new job running `scripts/slack-email-digest.sh` daily.


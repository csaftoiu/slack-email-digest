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

### Create the App

Create and deploy the app:

```
heroku create my-app-name
git push heroku master
```

### Add-ons

Add the following add-ons:

1. Postmark (note: doesn't support message threading)
1. Heroku Scheduler
1. Papertrail (optional)

### Config Vars 

Set the following config vars:

1. `SLACKEMAILDIGEST_FROM=sender@yourdomain.com`
1. `SLACKEMAILDIGEST_TO=receiver@theirdomain.com`
1. `SLACKEMAILDIGEST_TOKEN=slack-test-api-token` ([Test token](https://api.slack.com/docs/oauth-test-tokens))

#### Postmark Delivery

Set the following variable:

1. `SLACKEMAILDIGEST_DELIVERY=postmark`

Note that messages sent via postmark won't be threaded properly.

#### SMTP Delivery

Set the following variables:

1. `SLACKEMAILDIGEST_SMTP_HOST=smtp.example.com`
1. `SLACKEMAILDIGEST_SMTP_PORT=587`
1. `SLACKEMAILDIGEST_SMTP_USER=example`
1. `SLACKEMAILDIGEST_SMTP_PASSWORD=secret`

### Add-ons

Configure the necessary add-ons:

1. Open the *Heroku Scheduler* add-on from your app dashboard and add a new job running `scripts/slack-email-digest.sh` daily.
1. *(postmark only)* Open the *Postmark* add-on and create a "sender signature" matching the value of `SLACKEMAILDIGEST_FROM`


# slack-email-digest
Scripts to summarize Slack chat history into an email digest.

## Local setup

Install Python 3 and then run:

```
venv ./myenv
./myenv/bin/python setup.py develop
```

### Troubleshooting

- If you receive [SSL errors](https://github.com/kennethreitz/requests/issues/3011#issuecomment-183626795) on OSX, try installing Python 3 from Homebrew. 

## Deploying to Heroku

```
heroku create my-app-name
git push heroku master
```

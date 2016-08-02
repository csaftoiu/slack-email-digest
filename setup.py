from setuptools import setup


setup(
    name='slack-email-digest',
    version='0.1',
    author='Claudiu Saftoiu',
    author_email='csaftoiu@gmail.com',
    description='Export Slack history as a rich HTML email message',
    url='https://github.com/csaftoiu/slack-email-digest',

    install_requires=[
        'slacker(==0.9.24)',
        'docopt(==0.6.2)',
        'schema(==0.6.2)',
        'jinja2(==2.8)',
    ],

    packages=[],
    scripts=['scripts/slack-email-digest.py'],
)

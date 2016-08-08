import time
import sys

import slacker

from functools import lru_cache


def eprint(*args, **kwargs):
    return print(*args, **kwargs, file=sys.stderr)


class SlackScraper(object):
    def __init__(self, token, verbose=False, request_pause_period=0.5):
        self.slack = slacker.Slacker(token)
        self.verbose = verbose

        self.request_pause_period = 0.5

    def get_team_id(self):
        """:return The team ID for the Slack being accessed by this scraper."""
        return self.slack.team.info().body['team']['id']

    def get_username(self, user_id):
        for name, info in self.users.items():
            if info['id'] == user_id:
                return name

        raise ValueError("No such user: %s" % (user_id,))

    def get_channel_id(self, channel_name):
        res = self.channels.get(channel_name)

        if not res:
            raise ValueError("Channel '%s' does not exist" % (channel_name,))

        return res['id']

    def get_channel_name(self, channel_id):
        for name, info in self.channels.items():
            if info['id'] == channel_id:
                return name

        raise ValueError("No such channel: %s" % (channel_id,))

    @lru_cache(None)
    def get_bot_name(self, bot_id):
        return self.slack.bots.info(bot=bot_id).body['bot']['name']

    def get_channel_history(self, channel, oldest=None, latest=None):
        """Get the channel history.
        :param channel Channel id or name
        :param oldest Timestamp of first message to retrieve, in milliseconds, inclusive. Defaults to the beginning.
        :param latest Timestamp of last message to retrieve, in milliseconds, exclusive. Defaults to now.
        """
        if channel in self.channels:
            channel = self.get_channel_id(channel)

        has_more = True
        messages = []
        while has_more:
            m = self.slack.channels.history(
                channel,
                count=1000,
                oldest=oldest,
                latest=latest - 0.1 if latest else None,  # sub a bit to exclude message right on the dot
                inclusive=1
            )
            messages.extend(m.body['messages'])
            if self.verbose:
                eprint("Retrieved {} messages".format(
                    len(messages)
                ))

            latest = m.body['messages'][-1]['ts'] if m.body['messages'] else latest
            has_more = m.body["has_more"]
            time.sleep(self.request_pause_period)

        return messages

    @property
    @lru_cache(1)
    def channels(self):
        return {c["name"]: c for c in self.slack.channels.list().body["channels"]}

    @property
    @lru_cache(1)
    def users(self):
        return {c["name"]: c for c in self.slack.users.list().body["members"]}

    @property
    @lru_cache(1)
    def emojis(self):
        return self.slack.emoji.list().body['emoji']

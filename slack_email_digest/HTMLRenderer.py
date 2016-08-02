import jinja2


message_template = """\
<div>
  <b>{{ msg.user | username }}</b>: {{ msg.text }}</b>
</div>\
"""

class HTMLRenderer:
    def __init__(self, scraper):
        self.scraper = scraper

        self.env = jinja2.Environment()
        self.env.filters['username'] = self.filter_username

        self.templates = {
            'message': self.env.from_string(message_template)
        }

    def filter_username(self, user_id):
        return self.scraper.get_username(user_id)

    def render_message(self, msg):
        return self.templates['message'].render(msg=msg)

# Notifications in Clrbrain
# Author: David Young, 2018
"""Post Clrbrain notifications.

Attributes:
"""

import json
from urllib import request

from clrbrain import cli
from clrbrain import config

def post(url, msg, attachment):
    post_fields = {"text": msg}
    if attachment:
        post_fields["attachments"] = [{"text": attachment}]
    header = {"Content-type": "application/json"}
    req = request.Request(url, json.dumps(post_fields).encode("utf8"), header)
    response = request.urlopen(req)
    print(response.read().decode("utf8"))
    return response

if __name__ == "__main__":
    print("Starting Clrbrain notifier...")
    cli.main(True)
    post(config.notify_url, config.notify_msg, config.notify_attach)

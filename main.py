from webapp2 import WSGIApplication
from os import environ
import yaml
import tweet_blog

config = {}
try:
    config.update(yaml.load(open('config.yaml', 'r')))
except IOError:
    pass

routes = tweet_blog.routes
app = WSGIApplication(routes, config=config,
                      debug=environ.get('SERVER_SOFTWARE').startswith('Dev'))


# coding=utf-8

from webapp2 import RequestHandler
import urllib
from google.appengine.api.urlfetch import fetch
from google.appengine.api import taskqueue
import hmac
from hashlib import sha1
from base64 import b64encode
from time import time
from random import getrandbits
import json
import logging

api_urls = {
    'request_token_url': 'http://twitter.com/oauth/request_token',
    'access_token_url' : 'http://twitter.com/oauth/access_token',
    'authorize_url'    : 'http://twitter.com/oauth/authorize',
    'tweet_url'        : 'https://api.twitter.com/1.1/statuses/update.json',
    'github_commits'   : 'https://api.github.com/repos/defeo/defeo.github.io/commits/',
    'blog_base'        : 'http://defeo.lu',
    'blog_posts'       : '/api/posts.json'
    }

# Configuration variables
entry_url   = '/tweet-ghblog'
worker_url  = '/tweet-ghblog/commit'
def w_config(m):
    def wrap(self):
        self._post_prefix = self.app.config['tweet_blog'].get('post_prefix') or '[POST]'
        self._post_dir    = self.app.config['tweet_blog'].get('post_dir')    or '_posts/'
        m(self)
    return wrap
        
class CheckCommits(RequestHandler):
    '''
    This hook repsonds to post requests from the github Webhook
    service. It looks for new post commits inside the commits posted
    by github.
    '''
    @w_config
    def post(self):
        commits = json.loads(self.request.get('payload'))
        # Examine each commit in the payload of the request
        count = 0
        for c in commits["commits"]:
            if c['message'].startswith(self._post_prefix):
                # If commit starts with the right prefix, launch a task to examine it
                taskqueue.add(url=worker_url, params={'commit-id': c['id']})
                count += 1
                
        logging.info('Considering %d commits.' % count)
        self.response.content_type = 'application/json'
        self.response.write('{"commits": %d}' % count)


class Tweet(RequestHandler):
    '''
    This hook examines a single commit, looks for newly added files,
    and tweets any new post found.
    '''
    @w_config
    def post(self):
        # Fetch and parse json summary of posts from the blog
        posts = fetch(api_urls['blog_base'] + api_urls['blog_posts'])
        if posts.status_code != 200:
            logging.error('Cannot fetch post list. %s' % post.content)
            self.abort(500, detail='Cannot fetch post list.')
        posts = json.loads(posts.content)

        # Fetch and parse commit data from github
        commit = fetch(api_urls['github_commits'] + self.request.get('commit-id'),
                       validate_certificate=True)
        if commit.status_code != 200:
            logging.error('Cannot fetch commit data. %s' % commit.content)
            self.abort(500, 'Cannot fetch commit data.')
        commit = json.loads(commit.content)

        if commit['commit']['message'].startswith(self._post_prefix):
            # If commit starts with right prefix, look for new files in the post directory
            count = 0
            for f in commit['files']:
                if f['status'] == 'added' and f['filename'].startswith(self._post_dir):
                    count += 1
                    # Tweet post announcement
                    post = posts.get(f['filename'])
                    if post is None:
                        logging.error('Post %s missing in list.' % f['filename'])
                        self.abort(500, 'Post seems to be missing in list.')

                    tweet = u'#Blog post %s.%s %s%s' % (post['title'],
                                                        ''.join(' #' + t for t in post['tags'][:2]),
                                                         api_urls['blog_base'], post['url'])

                    res = self._sign(api_urls['tweet_url'], 'POST', {'status': tweet})
        
                    if res.status_code != 200:
                        res = json.loads(res.content)
                        logging.error('Error while tweeting. %s ' % repr(res['errors']))
                        self.abort(500, 'Error while tweeting.')
                    else:
                        logging.info('Tweeted %s' % tweet)
            self.response.content_type = 'application/json'
            self.response.write('{"posts": %d}' % count)
        else:
            logging.info('Ignoring commit %s: badly formatted message.' % self.request.get('commit-id'))
            self.response.content_type = 'application/json'
            self.response.write('{"error":"Ignoring badly formatted commit message."}')

    def _sign(self, url, method='GET', data=None):
        def quote(s):
            'Percent encoding following RFC 3986'
            return urllib.quote(s.encode('utf-8'), '-._~')

        data = data.items() if data is not None else []

        # OAuth header
        oauth = [
            ('oauth_consumer_key'     , self.app.config['tweet_blog']['consumer_key']), 
            ('oauth_nonce'            , b64encode('%0x' % getrandbits(256))[:32]),
            ('oauth_signature_method' , 'HMAC-SHA1'),
            ('oauth_timestamp'        , str(int(time()))),
            ('oauth_token'            , self.app.config['tweet_blog']['access_token']),
            ('oauth_version'          , '1.0')
            ]
        # OAuth signature
        sig = '%s&%s&%s' % (
            method.upper(),
            quote(url),
            quote("&".join('%s=%s' % tuple(map(quote, p))
                           for p in sorted(oauth + data,
                                           key=lambda(k,_):k))))
        key = '%s&%s' % (quote(self.app.config['tweet_blog']['consumer_secret']),
                         quote(self.app.config['tweet_blog']['access_token_secret']))
        oauth.append(('oauth_signature',
                      b64encode(hmac.new(key,sig,sha1).digest())))

        # form the OAuth header
        oauth_h = 'OAuth ' + ', '.join('%s="%s"' % tuple(map(quote, o))
                                       for o in oauth)

        # Build the request
        return fetch(url,
                     '&'.join('%s=%s' % tuple(map(quote, d)) for d in data),
                     method, {'Authorization': oauth_h},
                     validate_certificate=True)

routes = [(entry_url, CheckCommits),
          (worker_url, Tweet)]

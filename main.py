# coding=utf-8

import webapp2
from webapp2 import WSGIApplication, RequestHandler
from os import environ
import yaml
import urllib
from google.appengine.api.urlfetch import fetch
import hmac
from hashlib import sha1
from base64 import b64encode
from time import time
from random import getrandbits
import json
import logging

config = {
    'request_token_url': 'http://twitter.com/oauth/request_token',
    'access_token_url' : 'http://twitter.com/oauth/access_token',
    'authorize_url'    : 'http://twitter.com/oauth/authorize',
    'tweet_url'        : 'https://api.twitter.com/1.1/statuses/update.json'
    }
try:
    config.update(yaml.load(open('config.yaml', 'r')))
except IOError:
    pass

def quote(s):
    'Percent encoding following RFC 3986'
    return urllib.quote(s.encode('utf-8'), '-._~')

class Tweet(RequestHandler):
    def get(self):
        method = 'POST'

        # OAuth header
        oauth = map(lambda (k,v) : (quote(k), quote(v)),
                    [
                ('oauth_consumer_key'     , config['consumer_key']), 
                ('oauth_nonce'            , "2624ca580241655d217374a70779090a"),#b64encode('%0x' % getrandbits(256))[:32]),
                ('oauth_signature_method' , 'HMAC-SHA1'),
                ('oauth_timestamp'        , '1377736024'),#str(int(time()))),
                ('oauth_token'            , config['access_token']),
                ('oauth_version'          , '1.0')
                ])
        # The tweet
        data = map(lambda (k,v) : (quote(k), quote(v)),
                   [('status', u'Héllo ωorld!')])

        # OAuth signature
        sig = '%s&%s&%s' % (
            method.upper(),
            quote(config['tweet_url']),
            quote("&".join('%s=%s' % p 
                           for p in sorted(oauth + data,
                                           key=lambda(k,_):k))))
        key = '%s&%s' % (quote(config['consumer_secret']),
                         quote(config['access_token_secret']))
        oauth.append(('oauth_signature', 
                      quote(b64encode(hmac.new(key,sig,sha1).digest()))))

        # form the OAuth header
        oauth_h = 'OAuth ' + ', '.join('%s="%s"' % o for o in oauth)

        # Build the request
        res = fetch(config['tweet_url'], '&'.join('%s=%s' % d for d in data),
                    method, {'Authorization': oauth_h},
                    validate_certificate=True)

        if res.status_code != 200:
            res = json.loads(res.content)
            logging.error(repr(res['errors']))
            print oauth_h
            print sig
            print key
        else:
            logging.info('Tweeted: ' + data[0][1])


routes = [('/', Tweet)]
app = WSGIApplication(routes,
                      debug=environ.get('SERVER_SOFTWARE').startswith('Dev'))


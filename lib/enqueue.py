#!/usr/bin/env python
# encoding: utf-8
'''
agents.launch -- Feeds URIs into queues

@author:     Andrew Jackson

@copyright:  2016 The British Library.

@license:    Apache 2.0

@contact:    Andrew.Jackson@bl.uk
@deffield    updated: 2016-01-16
'''

import json
import logging
from datetime import datetime
import mmh3
import binascii
import struct
from urlparse import urlparse
from kafka import KafkaProducer


# Set logging for this module and keep the reference handy:
logger = logging.getLogger(__name__)


class KafkaLauncher(object):
    '''
    classdocs
    '''

    def __init__(self, args):
        '''
        Constructor
        '''
        self.args = args
        self.producer = KafkaProducer(
            bootstrap_servers=self.args.kafka_server,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'))

    def send_message(self, key, message, queue=None):
        """
        Sends a message to the given queue.
        """
        #
        if not queue:
            queue = self.args.queue

        logger.info("Sending key %s, message: %s" % (key, json.dumps(message)))
        self.producer.send(queue, key=key, value=message)

    def launch(self, destination, uri, source, isSeed=False, forceFetch=False, sheets=[], hop="", recrawl_interval=None):
        curim = {}
        if destination == "h3":
            curim['headers'] = {}
            # curim['headers']['User-Agent'] = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/37.0.2062.120 Chrome/37.0.2062.120 Safari/537.36"
            curim['method'] = "GET"
            curim['parentUrl'] = uri
            curim['parentUrlMetadata'] = {}
            curim['parentUrlMetadata']['pathFromSeed'] = ""
            curim['parentUrlMetadata']['heritableData'] = {}
            curim['parentUrlMetadata']['heritableData']['source'] = source
            curim['parentUrlMetadata']['heritableData']['heritable'] = ['source', 'heritable']
            curim['isSeed'] = isSeed
            if not isSeed:
                curim['forceFetch'] = forceFetch
            curim['url'] = uri
            curim['hop'] = hop
            if len(sheets) > 0:
                curim['sheets'] = sheets
            if recrawl_interval:
                curim['recrawlInterval'] = recrawl_interval
            curim['timestamp'] = datetime.now().isoformat()
        elif destination == "har":
            curim['clientId'] = "unused"
            curim['metadata'] = {}
            curim['metadata']['heritableData'] = {}
            curim['metadata']['heritableData']['heritable'] = ['source', 'heritable']
            curim['metadata']['heritableData']['source'] = source
            curim['metadata']['pathFromSeed'] = ""
            curim['isSeed'] = isSeed
            if not isSeed:
                curim['forceFetch'] = forceFetch
            curim['url'] = uri
        else:
            logger.error("Can't handle destination type '%s'" % destination)

        # Determine the key, hashing the 'authority' (should match Java version):
        key = binascii.hexlify(struct.pack("<I", mmh3.hash(urlparse(uri).netloc, signed=False)))

        # Push a 'seed' message onto the rendering queue:
        self.send_message(key, curim)

    def flush(self):
        self.producer.flush()
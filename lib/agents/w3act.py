#!/usr/bin/env python
# -*- coding: utf-8 -*- 

import sys
import json
import logging
import requests
import traceback
import datetime, time
import dateutil.parser

logger = logging.getLogger( __name__)


class w3act():
	def __init__(self, url, email, password):
		self.url = url.rstrip("/")
		loginUrl = "%s/login" % self.url
		logger.info("Logging into %s as %s "% ( loginUrl, email ))
		response = requests.post(loginUrl, data={"email": email, "password": password})
		if not response.history:
			logger.error("Login failed!")
			sys.exit()
		self.cookie = response.history[0].headers["set-cookie"]
		self.get_headers = {
			"Cookie": self.cookie,
		}
		self.up_headers = {
			"Cookie": self.cookie,
			"Content-Type": "application/json"
		}


	def _get_json(self, url):
		js = None
		try:
			logger.info("Getting URL: %s" % url)
			r = requests.get(url, headers=self.get_headers)
			if r.status_code == 200:
				js = json.loads(r.content)
			else:
				logger.info(r.status_code)
				logger.info(r.text)
		except:
			logger.warning(str(sys.exc_info()[0]))
			logger.warning(str(traceback.format_exc()))
		return js
	
	def get_json(self,path):
		path = path.lstrip("/")
		qurl = "%s/%s" % (self.url,path)
		logger.info("Getting %s" % qurl )
		return self._get_json(qurl)

	def get_ld_export(self, frequency):
		qurl = "%s/api/crawl/feed/ld/%s" % (self.url, frequency)
		logger.info("Getting %s" % qurl )
		return self._get_json( qurl )

	def get_by_export(self, frequency):
		return self._get_json( "%s/api/crawl/feed/by/%s" % (self.url, frequency))

	def post_document(self, doc):
		''' See https://github.com/ukwa/w3act/wiki/Document-REST-Endpoint '''
		r = requests.post("%s/documents" % self.url, headers=self.up_headers, data=json.dumps([doc]))
		return r
	
	def post_target(self, url, title):
		target = {}
		target['field_urls'] = [ url ]
		target['title'] = title
		target['selector'] = 1
		target['field_scope'] = "root"
		target['field_depth'] = "CAPPED"
		target['field_ignore_robots_txt']=  False
		logger.info("POST %s" % (json.dumps(target)))
		r = requests.post("%s/api/targets" % self.url, headers=self.up_headers, data=json.dumps(target))
		return r
	
	def get_target(self,tid):
		return self.get_json("/api/targets/%d" % tid)
	
	def update_target_schedule(self,tid,frequency, start_date, end_date=None):
		target = {}
		target['field_crawl_frequency'] = frequency.upper()
		sd = dateutil.parser.parse(start_date)
		target['field_crawl_start_date'] = int(time.mktime(sd.timetuple()))
		if end_date:
			ed = dateutil.parser.parse(start_date)
			target['field_crawl_end_date'] = int(time.mktime(ed.timetuple()))
		else:
			target['field_crawl_end_date'] = 0
		logger.info("PUT %d %s" % (tid,json.dumps(target)))
		r = requests.put("%s/api/targets/%d" % (self.url, tid), headers=self.up_headers, data=json.dumps(target))
		return r

	def update_target_selector(self,tid,uid):
		target = {}
		target['selector'] = uid
		logger.info("PUT %d %s" % (tid,json.dumps(target)))
		r = requests.put("%s/api/targets/%d" % (self.url, tid), headers=self.up_headers, data=json.dumps(target))
		return r

	def watch_target(self,tid):
		target = {}
		target['watchedTarget'] = {}
		target['watchedTarget']['documentUrlScheme'] = ""
		logger.info("PUT %d %s" % (tid,json.dumps(target)))
		r = requests.put("%s/api/targets/%d" % (self.url, tid), headers=self.up_headers, data=json.dumps(target))
		return r

	def unwatch_target(self,tid):
		target = {}
		target['watchedTarget'] = None
		logger.info("PUT %d %s" % (tid,json.dumps(target)))
		r = requests.put("%s/api/targets/%d" % (self.url, tid), headers=self.up_headers, data=json.dumps(target))
		return r
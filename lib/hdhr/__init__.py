# -*- coding: utf-8 -*-
import time
import requests
import binascii
import urllib

import discovery

try:
    from collections import OrderedDict
except:
    from ordereddict_compat import OrderedDict

from lib import util

GUIDE_URL = 'http://mytest.hdhomerun.com/api/guide.php?DeviceID={0}'
SEARCH_URL = 'http://mytest.hdhomerun.com/api/search?DeviceID={0}&Search={1}'

class NoCompatibleDevicesException(Exception): pass

class NoDevicesException(Exception): pass

def chanTuple(guide_number,chanCount):
    major, minor = (guide_number + '.0').split('.',2)[:2]
    return (int(major),int(minor),chanCount*-1)

class ChannelSource(dict):
    @property
    def url(self):
        return self['url']

    @property
    def ID(self):
        return self['ID']

class Channel(object):
    def __init__(self,data,device_response):
        self.number = data['GuideNumber']
        self.name = data['GuideName']
        self.sources = [ChannelSource({'url':data['URL'],'ID':device_response.ID})]
        self.favorite = bool(data.get('Favorite',False))
        self.guide = None

    def add(self,data,device_response):
        self.sources.append(ChannelSource({'url':data['URL'],'ID':device_response.ID}))

    def setGuide(self,guide):
        self.guide = guide

class LineUp(object):
    def __init__(self):
        self.channels = OrderedDict()
        self.devices = {}
        self.hasGuideData = False
        self.collectLineUp()

    def __getitem__(self,key):
        return self.channels[key]

    def __contains__(self, key):
        return key in self.channels

    def __len__(self):
        return len(self.channels.keys())

    def index(self,key):
        if not key in self.channels: return -1
        return self.channels.keys().index(key)

    def indexed(self,index):
        return self.channels[ [k for k in self.channels.keys()][index] ]

    def getDeviceByIP(self,ip):
        for d in self.devices.values():
            if d.ip == ip:
                return d
        return None

    def defaultDevice(self):
        #Return device with the most number of channels as default
        highest = None
        for d in self.devices.values():
            if not highest or highest.channelCount < d.channelCount:
                highest = d
        return highest

    def collectLineUp(self):
        responses = discovery.discover(discovery.TUNER_DEVICE)

        if not responses: raise NoDevicesException()

        lineUps = []

        for r in responses:
            self.devices[r.ID] = r
            try:
                lineup = requests.get(r.url).json()
            except:
                util.ERROR()
                continue

            r.channelCount = len(lineup)
            lineUps.append((r,lineup))

        if not lineUps: raise NoCompatibleDevicesException()

        while lineUps:
            lowest = min(lineUps,key=lambda l: l[1] and chanTuple(l[1][0]['GuideNumber'],l[0].channelCount) or (0,0,0)) #Prefer devices with the most channels assuming (possibly wrongly) that they are getting a better signal
            if not lowest[1]:
                lineUps.pop(lineUps.index(lowest))
                continue

            chanData = lowest[1].pop(0)
            if chanData['GuideNumber'] in self.channels:
                self.channels[chanData['GuideNumber']].add(chanData,lowest[0])
            else:
                self.channels[chanData['GuideNumber']] = Channel(chanData,lowest[0])

        if not self.channels: util.DEBUG_LOG(lineUps)

    def search(self,terms):
        url = SEARCH_URL.format(self.apiAuthID(),urllib.quote(terms.encode('utf-8')))
        util.DEBUG_LOG('Search URL: {0}'.format(url))
        try:
            results = requests.get(url).json()
            return results
        except:
            util.ERROR()

        return None

    def apiAuthID(self):
        combined = ''
        ids = []
        for d in self.devices.values():
            ids.append(d.ID)
            authID = d.authID
            if not authID: continue
            combined += authID

        if combined and not GUIDE_URL.startswith('http://mytest.'):
            return binascii.b2a_base64(combined)
        else:
            return ','.join(ids)

class Show(dict):
    @property
    def title(self):
        return self.get('Title','')

    @property
    def epTitle(self):
        return self.get('EpisodeTitle','')

    @property
    def icon(self):
        return self.get('ImageURL','')

    @property
    def synopsis(self):
        return self.get('Synopsis','')

    @property
    def start(self):
        return self.get('StartTime')

    @property
    def end(self):
        return self.get('EndTime')

    def progress(self):
        start = self.get('StartTime')
        if not start: return None
        end = self.get('EndTime')
        duration = end - start
        sofar = time.time() - start
        return int((sofar/duration)*100)

class GuideChannel(dict):
    @property
    def number(self):
        return self.get('GuideNumber','')

    @property
    def name(self):
        return self.get('GuideName','')

    @property
    def icon(self):
        return self.get('ImageURL','')

    @property
    def affiliate(self):
        return self.get('Affiliate','')

    def currentShow(self):
        shows = self.get('Guide')
        if not shows: return Show()
        now = time.time()
        for s in shows:
            if now >= s.get('StartTime') and now < s.get('EndTime'):
                return Show(s)
        return Show()

    def nextShow(self):
        shows = self.get('Guide')
        if not shows: return Show()
        if len(shows) < 2: return Show()
        now = time.time()
        for i,s in enumerate(shows):
            if now >= s.get('StartTime') and now < s.get('EndTime'):
                i+=1
                if i >= len(shows): break
                return Show(shows[i])

        return Show()

class Guide(object):
    def __init__(self,lineup=None):
        self.init(lineup)

    def init(self,lineup):
        self.guide = OrderedDict()
        if not lineup:
            return
        url = GUIDE_URL.format(lineup.apiAuthID())
        util.DEBUG_LOG('Fetching guide from: {0}'.format(url))
        data = requests.get(url).json()
        for chan in data:
            self.guide[chan['GuideNumber']] = chan

    def getChannel(self,guide_number):
        return GuideChannel(self.guide.get(guide_number) or {})
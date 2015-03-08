# -*- coding: utf-8 -*-
import requests
import discovery
import ordereddict

GUIDE_URL = 'http://mytest.hdhomerun.com/api/guide.php?DeviceID=10504038'

def chanTuple(guide_number):
    major, minor = guide_number.split('.')
    return (int(major),int(minor))

class ChannelSource(dict):
    @property
    def url(self):
        return self['url']

    def ID(self):
        return self['ID']

class Channel(object):
    def __init__(self,data,device_response):
        self.number = data['GuideNumber']
        self.name = data['GuideName']
        self.sources = [ChannelSource({'url':data['URL'],'ID':device_response.ID})]
        self.favorite = bool(data.get('Favorite',False))


    def add(self,data,device_response):
        self.urls.append(ChannelSource({'url':data['URL'],'ID':device_response.ID}))

class LineUp(object):
    def __init__(self):
        self.channels = ordereddict.OrderedDict()
        self.collectLineUp()

    def __getitem__(self,key):
        return self.channels[key]

    def indexed(self,index):
        return self.channels[[k for k in self.channels.keys()][index]]

    def collectLineUp(self):
        responses = discovery.discover(discovery.TUNER_DEVICE)
        lineUps = []

        for r in responses:
            lineUps.append((r,requests.get(r.url).json()))

        while True:
            lowest = min(lineUps,key=lambda l: l[1] and chanTuple(l[1][0]['GuideNumber']) or (0,0))
            if not lowest[1]: return
            chanData = lowest[1].pop(0)
            if chanData['GuideNumber'] in self.channels:
                self.channels[chanData['GuideNumber']].add(chanData,lowest[0])
            else:
                self.channels[chanData['GuideNumber']] = Channel(chanData,lowest[0])

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

    def currentShow(self):
        shows = self.get('Guide')
        if not shows: return Show()
        return Show(shows[0])

    def nextShow(self):
        shows = self.get('Guide')
        if not shows: return Show()
        if len(shows) < 2: return Show()
        return Show(shows[1])

class Guide(object):
    def __init__(self):
        self.init()

    def init(self):
        self.guide = ordereddict.OrderedDict()
        data = requests.get(GUIDE_URL).json()
        for chan in data:
            self.guide[chan['GuideNumber']] = chan

    def getChannel(self,guide_number):
        return GuideChannel(self.guide.get(guide_number) or {})
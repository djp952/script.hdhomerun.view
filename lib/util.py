# -*- coding: utf-8 -*-
import sys, binascii, json, threading, time, datetime
import xbmc, xbmcaddon

DEBUG = True

ADDON = xbmcaddon.Addon()

T = ADDON.getLocalizedString

def LOG(msg):
    xbmc.log('script.hdhomerun.view: {0}'.format(msg))

def DEBUG_LOG(msg):
    if not getSetting('debug',False) and not xbmc.getCondVisibility('System.GetBool(debug.showloginfo)'): return
    LOG(msg)

def ERROR(txt='',hide_tb=False,notify=False):
    if isinstance (txt,str): txt = txt.decode("utf-8")
    short = str(sys.exc_info()[1])
    if hide_tb:
        LOG('ERROR: {0} - {1}'.format(txt,short))
        return short
    print "_________________________________________________________________________________"
    LOG('ERROR: ' + txt)
    import traceback
    tb = traceback.format_exc()
    for l in tb.splitlines(): print '    ' + l
    print "_________________________________________________________________________________"
    print "`"
    if notify: showNotification('ERROR: {0}'.format(short))
    return short

def getSetting(key,default=None):
    setting = ADDON.getSetting(key)
    return _processSetting(setting,default)

def _processSetting(setting,default):
    if not setting: return default
    if isinstance(default,bool):
        return setting.lower() == 'true'
    elif isinstance(default,float):
        return float(setting)
    elif isinstance(default,int):
        return int(float(setting or 0))
    elif isinstance(default,list):
        if setting: return json.loads(binascii.unhexlify(setting))
        else: return default

    return setting

def setSetting(key,value):
    value = _processSettingForWrite(value)
    ADDON.setSetting(key,value)

def _processSettingForWrite(value):
    if isinstance(value,list):
        value = binascii.hexlify(json.dumps(value))
    elif isinstance(value,bool):
        value = value and 'true' or 'false'
    return str(value)

def showNotification(message,time_ms=3000,icon_path=None,header=ADDON.getAddonInfo('name')):
    try:
        icon_path = icon_path or xbmc.translatePath(ADDON.getAddonInfo('icon')).decode('utf-8')
        xbmc.executebuiltin('Notification({0},{1},{2},{3})'.format(header,message,time_ms,icon_path))
    except RuntimeError: #Happens when disabling the addon
        LOG(message)

def videoIsPlaying():
    return xbmc.getCondVisibility('Player.HasVideo')

def timeInDayLocalSeconds():
    now = datetime.datetime.now()
    sod = datetime.datetime(year=now.year,month=now.month,day=now.day)
    sod = int(time.mktime(sod.timetuple()))
    return int(time.time() - sod)

class CronReceiver(object):
    def tick(self): pass
    def halfHour(self): pass
    def day(self): pass

class Cron(threading.Thread):
    def __init__(self,interval):
        threading.Thread.__init__(self)
        self.stopped = threading.Event()
        self.force = threading.Event()
        self.interval = interval
        self._lastHalfHour = self._getHalfHour()
        self._receivers = []

    def __enter__(self):
        self.start()
        DEBUG_LOG('Cron started')
        return self

    def __exit__(self,exc_type,exc_value,traceback):
        self.stop()
        self.join()

    def _wait(self):
        ct=0
        while ct < self.interval:
            xbmc.sleep(100)
            ct+=0.1
            if self.force.isSet():
                self.force.clear()
                return True
            if xbmc.abortRequested or self.stopped.isSet(): return False
        return True

    def forceTick(self):
        self.force.set()

    def stop(self):
        self.stopped.set()

    def run(self):
        while self._wait():
            self._tick()
        DEBUG_LOG('Cron stopped')

    def _getHalfHour(self):
        tid = timeInDayLocalSeconds()/60
        return tid - (tid % 30)

    def _tick(self):
        receivers = list(self._receivers)
        receivers = self._halfHour(receivers)
        for r in receivers:
            try:
                r.tick()
            except:
                ERROR()

    def _halfHour(self,receivers):
        hh = self._getHalfHour()
        if hh == self._lastHalfHour: return receivers
        try:
            receivers = self._day(receivers,hh)
            ret = []
            for r in receivers:
                try:
                    if not r.halfHour(): ret.append(r)
                except:
                    ret.append(r)
                    ERROR()
            return ret
        finally:
            self._lastHalfHour = hh

    def _day(self,receivers,hh):
        if hh >= self._lastHalfHour: return receivers
        ret = []
        for r in receivers:
            try:
                if not r.day(): ret.append(r)
            except:
                ret.append(r)
                ERROR()
        return ret

    def registerReceiver(self,receiver):
        self._receivers.append(receiver)

    def cancelReceiver(self,receiver):
        if receiver in self._receivers:
            self._receivers.pop(self._receivers.index(receiver))

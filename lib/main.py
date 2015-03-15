# -*- coding: utf-8 -*-
import time
import xbmc, xbmcgui

import hdhr
import kodigui
import util
import player

MAX_TIME_INT = 31536000000 #1000 years from Epoch

CHANNEL_DISPLAY = u'[COLOR FF99CCFF]{0}[/COLOR] {1}'

class BaseWindow(xbmcgui.WindowXML):
    def __init__(self,*args,**kwargs):
        self._closing = False
        self._winID = ''

    def onInit(self):
        self._winID = xbmcgui.getCurrentWindowId()

    def setProperty(self,key,value):
        if self._closing: return
        xbmcgui.Window(self._winID).setProperty(key,value)
        xbmcgui.WindowXMLDialog.setProperty(self,key,value)

    def doClose(self):
        self._closing = True
        self.close()

    def onClosed(self): pass

class BaseDialog(xbmcgui.WindowXMLDialog):
    def __init__(self,*args,**kwargs):
        self._closing = False
        self._winID = ''

    def onInit(self):
        self._winID = xbmcgui.getCurrentWindowDialogId()

    def setProperty(self,key,value):
        if self._closing: return
        xbmcgui.Window(self._winID).setProperty(key,value)
        xbmcgui.WindowXMLDialog.setProperty(self,key,value)

    def doClose(self):
        self._closing = True
        self.close()

    def onClosed(self): pass

class KodiChannelEntry(BaseDialog):
    def __init__(self,*args,**kwargs):
        self.digits = str(kwargs['digit'])
        self.channel = ''
        self.set = False
        BaseDialog.__init__(self,*args,**kwargs)

    def onInit(self):
        BaseDialog.onInit(self)
        self.showChannel()

    def onAction(self,action):
        try:
            if  action.getId() >= xbmcgui.REMOTE_0 and action.getId() <= xbmcgui.REMOTE_9:
                digit = str(action.getId() - 58)
                self.digits += digit
                self.showChannel()
                if '.' in self.channel:
                    self.close()
            elif action == xbmcgui.ACTION_SELECT_ITEM:
                if not self.addDecimal():
                    self.close()
        finally:
            BaseDialog.onAction(self,action)

    def addDecimal(self):
        if '.' in self.digits:
            self.channel = self.channel[:-1]
            self.showChannel()
            return False
        self.digits += '.'
        self.showChannel()
        return True

    def showChannel(self):
        self.channel = self.digits
        self.setProperty('channel',self.channel)

    def getChannel(self):
        if not self.channel: return None
        if self.channel.endswith('.'):
            return self.channel[:-1]
        return self.channel


class GuideOverlay(util.CronReceiver):
    _BASE = None
    def __init__(self,*args,**kwargs):
        self._BASE.__init__(self,*args,**kwargs)
        self.started = False
        self.touchMode = False
        self.lineUp = None
        self.guide = None
        self.current = None
        self.fallbackChannel = None
        self.cron = None
        self.guideFetchPreviouslyFailed = False
        self.nextGuideUpdate = MAX_TIME_INT

    #==========================================================================
    # EVENT HANDLERS
    #==========================================================================
    def onInit(self):
        self._BASE.onInit(self)
        if self.started: return
        if self.touchMode:
            util.DEBUG_LOG('Touch mode: ENABLED')
            self.setProperty('touch.mode','True')
        else:
            util.DEBUG_LOG('Touch mode: DISABLED')
        self.started = True
        self.channelList = kodigui.ManagedControlList(self,201,3)
        self.currentProgress = self.getControl(250)

        #Add item to dummy list - this list allows right click on video to bring up the context menu
        self.getControl(210).addItem(xbmcgui.ListItem(''))

        self.start()

    def onFocus(self,controlID):
        if controlID == 201:
            self.cron.forceTick()

    def onAction(self,action):
        try:
            if action == xbmcgui.ACTION_MOVE_RIGHT or action == xbmcgui.ACTION_MOVE_UP or action == xbmcgui.ACTION_MOVE_DOWN:
                return self.showOverlay()
            elif action == xbmcgui.ACTION_CONTEXT_MENU:
                return self.search()
            elif action == xbmcgui.ACTION_SELECT_ITEM:
                if self.clickShowOverlay(): return
            elif action == xbmcgui.ACTION_MOVE_LEFT:
                return self.showOverlay(False)
            elif action == xbmcgui.ACTION_PREVIOUS_MENU or action == xbmcgui.ACTION_NAV_BACK:
                if self.closeHandler(): return
            elif action == xbmcgui.ACTION_BUILT_IN_FUNCTION:
                if self.clickShowOverlay(): return
            elif self.checkChannelEntry(action):
                return
        except:
            util.ERROR()
            self._BASE.onAction(self,action)
            return
        self._BASE.onAction(self,action)

    def onClick(self,controlID):
        if self.clickShowOverlay(): return

        if controlID == 201:
            mli = self.channelList.getSelectedItem()
            channel = mli.dataSource
            self.playChannel(channel)

    def onPlayBackStarted(self):
        util.DEBUG_LOG('ON PLAYBACK STARTED')
        self.fallbackChannel = self.current and self.current.dataSource or None
        self.showProgress()

    def onPlayBackStopped(self):
        self.setCurrent()
        util.DEBUG_LOG('ON PLAYBACK STOPPED')
        self.showProgress() #In case we failed to play video on startup
        self.showOverlay()

    def onPlayBackFailed(self):
        self.setCurrent()
        util.DEBUG_LOG('ON PLAYBACK FAILED')
        self.showProgress() #In case we failed to play video on startup
        if self.fallbackChannel:
            channel = self.fallbackChannel
            self.fallbackChannel = None
            self.playChannel(channel)
        util.showNotification(util.T(32023),time_ms=5000,header=util.T(32022))
    # END - EVENT HANDLERS ####################################################

    def onPlayBackEnded(self):
        self.setCurrent()
        util.DEBUG_LOG('ON PLAYBACK ENDED')

    def tick(self):
        if time.time() > self.nextGuideUpdate:
            self.updateChannels()
        else:
            self.updateProgressBars()

    def doClose(self):
        self._BASE.doClose(self)
        if util.getSetting('exit.stops.player',True):
            self.player.stop()
        else:
            if xbmc.getCondVisibility('Window.IsActive(fullscreenvideo)'): xbmc.executebuiltin('Action(back)')

    def updateProgressBars(self,force=False):
        if not force and not self.overlayVisible(): return

        if self.current:
            self.currentProgress.setPercent(self.current.dataSource.guide.currentShow().progress() or 0)

        for mli in self.channelList:
            prog = mli.dataSource.guide.currentShow().progress()
            if prog == None:
                mli.setProperty('show.progress','')
            else:
                prog = int(prog - (prog % 5))
                mli.setProperty('show.progress','progress/script-hdhomerun-view-progress_{0}.png'.format(prog))

    def updateChannels(self):
        util.DEBUG_LOG('Updating channels')
        self.updateGuide()
        for mli in self.channelList:
            guideChan = mli.dataSource.guide
            currentShow = guideChan.currentShow()
            nextShow = guideChan.nextShow()
            title = mli.dataSource.name
            thumb = currentShow.icon
            icon = guideChan.icon
            if icon: title = CHANNEL_DISPLAY.format(mli.dataSource.number,title)
            mli.setLabel(title)
            mli.setThumbnailImage(thumb)
            mli.setProperty('show.title',currentShow.title)
            mli.setProperty('show.synopsis',currentShow.synopsis)
            mli.setProperty('next.title',u'{0}: {1}'.format(util.T(32004),nextShow.title or util.T(32005)))
            mli.setProperty('next.icon',nextShow.icon)
            start = nextShow.start
            if start:
                mli.setProperty('next.start',time.strftime('%I:%M %p',time.localtime(start)))
            prog = currentShow.progress()
            if prog != None:
                prog = int(prog - (prog % 5))
                mli.setProperty('show.progress','progress/script-hdhomerun-view-progress_{0}.png'.format(prog))

    def setCurrent(self,mli=None):
        if self.current:
            self.current.setProperty('is.current','')
            self.current = None
        if not mli: return self.setWinProperties()
        self.current = mli
        self.current.setProperty('is.current','true')
        self.setWinProperties()

    def closeHandler(self):
        if self.overlayVisible():
            if not self.player.isPlaying():
                return self.handleExit()
            self.showOverlay(False)
            return True
        else:
            return self.handleExit()

    def handleExit(self):
        if util.getSetting('confirm.exit',True):
            if not xbmcgui.Dialog().yesno(util.T(32006),'',util.T(32007),''): return True
        self.doClose()
        return True


    def fullscreenVideo(self):
        if not self.touchMode and util.videoIsPlaying():
            xbmc.executebuiltin('ActivateWindow(fullscreenvideo)')

    def getLineUpAndGuide(self):
        try:
            self.lineUp = hdhr.LineUp()
        except hdhr.NoCompatibleDevicesException:
            xbmcgui.Dialog().ok(util.T(32016),util.T(32011),'',util.T(32012))
            return False
        except hdhr.NoDevicesException:
            xbmcgui.Dialog().ok(util.T(32016),util.T(32014),'',util.T(32012))
            return False
        except:
            e = util.ERROR()
            xbmcgui.Dialog().ok(util.T(32016),util.T(32015),e,util.T(32012))
            return False

        self.showProgress(50,util.T(32008))
        self.updateGuide()
        self.showProgress(75,util.T(32009))
        return True

    def updateGuide(self):
        try:
            guide = hdhr.Guide(self.lineUp)
        except:
            e = util.ERROR()
            if not self.guideFetchPreviouslyFailed: #Only show notification the first time. Don't need this every 5 mins if internet is down
                util.showNotification(e,header=util.T(32013))
            self.guideFetchPreviouslyFailed = True
            self.nextGuideUpdate = time.time() + 300 #Could not get guide data. Check again in 5 minutes
            self.setWinProperties()
            if self.lineUp.hasGuideData: return
            guide = hdhr.Guide()

        self.guideFetchPreviouslyFailed = False

        self.nextGuideUpdate = MAX_TIME_INT
        for channel in self.lineUp.channels.values():
            guideChan = guide.getChannel(channel.number)
            channel.setGuide(guideChan)
            if channel.guide:
                end = channel.guide.currentShow().end
                if end and end < self.nextGuideUpdate:
                    self.nextGuideUpdate = end

        self.lineUp.hasGuideData = True

        self.setWinProperties()
        util.DEBUG_LOG('Next guide update: {0} minutes'.format(int((self.nextGuideUpdate - time.time())/60)))

    def setWinProperties(self):
        title = ''
        icon = ''
        nextTitle = ''
        progress = None
        channel = ''
        if self.current:
            channel = CHANNEL_DISPLAY.format(self.current.dataSource.number,self.current.dataSource.name)
            if self.current.dataSource.guide:
                currentShow = self.current.dataSource.guide.currentShow()
                title = currentShow.title
                icon = currentShow.icon
                progress = currentShow.progress()
                nextTitle = u'{0}: {1}'.format(util.T(32004),self.current.dataSource.guide.nextShow().title or util.T(32005))

        self.setProperty('show.title',title)
        self.setProperty('show.icon',icon)
        self.setProperty('next.title',nextTitle)
        self.setProperty('channel.name',channel)

        if progress != None:
            self.currentProgress.setPercent(progress)
            self.currentProgress.setVisible(True)
        else:
            self.currentProgress.setPercent(0)
            self.currentProgress.setVisible(False)

    def fillChannelList(self):
        last = util.getSetting('last.channel')
        items = []
        for channel in self.lineUp.channels.values():
            guideChan = channel.guide
            currentShow = guideChan.currentShow()
            nextShow = guideChan.nextShow()
            title = channel.name
            thumb = currentShow.icon
            icon = guideChan.icon
            if icon: title = CHANNEL_DISPLAY.format(channel.number,title)
            item = kodigui.ManagedListItem(title,thumbnailImage=thumb,data_source=channel)
            item.setProperty('channel.icon',icon)
            item.setProperty('channel.number',channel.number)
            item.setProperty('show.title',currentShow.title)
            item.setProperty('show.synopsis',currentShow.synopsis)
            item.setProperty('next.title',u'{0}: {1}'.format(util.T(32004),nextShow.title or util.T(32005)))
            item.setProperty('next.icon',nextShow.icon)
            start = nextShow.start
            if start:
                item.setProperty('next.start',time.strftime('%I:%M %p',time.localtime(start)))
            if last == channel.number:
                self.setCurrent(item)
            prog = currentShow.progress()
            if prog != None:
                prog = int(prog - (prog % 5))
                item.setProperty('show.progress','progress/script-hdhomerun-view-progress_{0}.png'.format(prog))
            items.append(item)
        self.channelList.addItems(items)

    def getStartChannel(self):
        util.DEBUG_LOG('Found {0} total channels'.format(len(self.lineUp)))
        last = util.getSetting('last.channel')
        if last and last in self.lineUp:
            return self.lineUp[last]
        elif len(self.lineUp):
            return self.lineUp.indexed(0)
        return None

    def start(self):
        if not self.getLineUpAndGuide(): #If we fail to get lineUp, just exit
            self.doClose()
            return

        for d in self.lineUp.devices.values():
            util.DEBUG_LOG('Device: {0} at {1} with {2} channels'.format(d.ID,d.ip,d.channelCount))

        self.fillChannelList()

        self.player = player.ChannelPlayer().init(self,self.lineUp,self.touchMode)

        channel = self.getStartChannel()
        if not channel:
            xbmcgui.Dialog().ok(util.T(32018),util.T(32017),'',util.T(32012))
            self.doClose()
            return

        if self.player.isPlayingHDHR():
            util.DEBUG_LOG('HDHR video already playing')
            self.fullscreenVideo()
            self.showProgress()
            mli = self.channelList.getListItemByDataSource(channel)
            self.setCurrent(mli)
        else:
            util.DEBUG_LOG('HDHR video not currently playing. Starting channel...')
            self.playChannel(channel)

        self.selectChannel(channel)

        self.cron.registerReceiver(self)

    def selectChannel(self,channel):
        pos = self.lineUp.index(channel.number)
        if pos > -1:
            self.channelList.selectItem(pos)

    def showProgress(self,progress='',message=''):
        self.setProperty('loading.progress',str(progress))
        self.setProperty('loading.status',message)

    def clickShowOverlay(self):
        if not self.overlayVisible():
            self.showOverlay()
            self.setFocusId(201)
            return True
        elif not self.getFocusId() == 201:
            self.showOverlay(False)
            return True
        return False

    def showOverlay(self,show=True):
        self.setProperty('show.overlay',show and 'SHOW' or '')
        if show and self.getFocusId() != 201: self.setFocusId(201)

    def overlayVisible(self):
        return bool(self.getProperty('show.overlay'))

    def playChannel(self,channel):
        self.setCurrent(self.channelList.getListItemByDataSource(channel))
        self.player.playChannel(channel)
        self.fullscreenVideo()

    def playChannelByNumber(self,number):
        if number in self.lineUp:
            channel = self.lineUp[number]
            self.playChannel(channel)
            return channel
        return None

    def checkChannelEntry(self,action):
        if action.getId() >= xbmcgui.REMOTE_0 and action.getId() <= xbmcgui.REMOTE_9:
            self.doChannelEntry(str(action.getId() - 58))
            return True
        return False

    def doChannelEntry(self,digit):
        window = KodiChannelEntry('script-hdhomerun-view-channel_entry.xml',util.ADDON.getAddonInfo('path'),'Main','1080p',digit=digit)
        window.doModal()
        channelNumber = window.getChannel()
        del window
        if not channelNumber: return
        util.DEBUG_LOG('Channel entered: {0}'.format(channelNumber))
        if not channelNumber in self.lineUp: return
        channel = self.lineUp[channelNumber]
        self.playChannel(channel)
        self.selectChannel(channel)

    def search(self):
        terms = xbmcgui.Dialog().input(util.T(32024))
        if not terms: return
        result = self.lineUp.search(terms)
        if not result:
            return xbmcgui.Dialog().ok(util.T(32025),'',util.T(32026))
        items = []
        channels = []
        for r in result:
            now = time.time()
            start = float(r.get('StartTime'))
            end = float(r.get('EndTime'))
            if now >= start and now < end:
                items.append(u'{0} - {1}: {2} - {3}'.format(r.get('ChannelNumber'),r.get('ChannelName'),r.get('Title')[:30],time.strftime('%I:%M %p',time.localtime(start))))
                channels.append(r.get('ChannelNumber'))
        if not items:
            return xbmcgui.Dialog().ok(util.T(32025),'',util.T(32026))
        idx = xbmcgui.Dialog().select('Results',items)
        if idx < 0: return
        channel = self.playChannelByNumber(channels[idx])
        self.selectChannel(channel)

class GuideOverlayWindow(GuideOverlay,BaseWindow):
    _BASE = BaseWindow

class GuideOverlayDialog(GuideOverlay,BaseDialog):
    _BASE = BaseDialog

def start():
    if util.getSetting('touch.mode',False):
        window = GuideOverlayWindow('script-hdhomerun-view-overlay.xml',util.ADDON.getAddonInfo('path'),'Main','1080i')
        window.touchMode = True
    else:
        window = GuideOverlayDialog('script-hdhomerun-view-overlay.xml',util.ADDON.getAddonInfo('path'),'Main','1080i')
    with util.Cron(5) as window.cron:
        window.doModal()
        del window

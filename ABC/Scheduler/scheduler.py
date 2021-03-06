import sys
import wx

from operator import attrgetter
from threading import Event
from threading import Timer
#from traceback import print_exc
#from cStringIO import StringIO

from ABC.Scheduler.action import ActionHandler
from ABC.Scheduler.addtorrents import AddTorrents
from ABC.Scheduler.ratemanager import RateManager

from Utility.constants import * #IGNORE:W0611


wxEVT_INVOKE = wx.NewEventType()

def EVT_INVOKE(win, func):
    win.Connect(-1, -1, wxEVT_INVOKE, func)
    
def DELEVT_INVOKE(win):
    win.Disconnect(-1, -1, wxEVT_INVOKE)

class InvokeEvent(wx.PyEvent):
    def __init__(self, func, args, kwargs):
        wx.PyEvent.__init__(self)
        self.SetEventType(wxEVT_INVOKE)
        self.func = func
        self.args = args
        self.kwargs = kwargs


################################################################
#
# Class: ABCScheduler
#
# Determine which torrents need to run, update global stats,
# and deal with loading, moving, and removing torrents.
#
################################################################
class ABCScheduler(wx.EvtHandler):
    def __init__(self, utility):
        wx.EvtHandler.__init__(self)
        
        self.utility = utility
        self.utility.queue = self
        
        self.utility.actionhandler = ActionHandler(self.utility)
        self.ratemanager = RateManager(self)
        self.addtorrents = AddTorrents(self)

        self.timers = {}
        
        self.flag = Event()

        self.totals = { 'up' : 0.0, 
                        'down' : 0.0, 
                        'connections': 0 }
        self.totals_kb = { 'up': 0.0,
                           'down': 0.0 }

        self.UpdateRunningTorrentCounters()

        EVT_INVOKE(self, self.onInvoke)
        
    def postInitTasks(self):
        # Read old list from torrent.lst
        ####################################
        self.addtorrents.readTorrentList()

        # Wait until after creating the list and adding torrents
        # to start CyclicalTasks in the scheduler
        self.CyclicalTasks()
        self.InfrequentCyclicalTasks(False)
      
    # Update the counters for torrents in a single unified place
    def CalculateTorrentCounters(self):
        torrents_active = self.utility.torrents["active"].keys()

        paused = {}
        seeding = {}
        downloading = {}
                                                   
        for ABCTorrentTemp in torrents_active:
            # Torrent is active
            if (ABCTorrentTemp.status.value == STATUS_HASHCHECK):
                activevalues = [ STATUS_ACTIVE, STATUS_PAUSE, STATUS_SUPERSEED ]
                # Torrent is doing a hash check
                # (Count towards counters if it was active before the the check,
                #  otherwise don't)
                if not ABCTorrentTemp.actions.oldstatus in activevalues:
                    continue
            
            if ABCTorrentTemp.status.value == STATUS_PAUSE:
                paused[ABCTorrentTemp] = 1
            elif ABCTorrentTemp.status.completed:
                seeding[ABCTorrentTemp] = 1
            else:
                downloading[ABCTorrentTemp] = 1

        self.utility.torrents["pause"] = paused
        self.utility.torrents["seeding"] = seeding
        self.utility.torrents["downloading"] = downloading
    
    def getProcCount(self):
        if self.utility.config.Read('trigwhenfinishseed', "boolean"):
            return len(self.utility.torrents["active"])
        else:
            return len(self.utility.torrents["active"]) - len(self.utility.torrents["seeding"])
        
    def UpdateRunningTorrentCounters(self):
        self.CalculateTorrentCounters()
            
        statusfunc = self.utility.frame.abc_sb.SetStatusText      
        statusfunc((" " + self.utility.lang.get('abbrev_loaded') + " %u " % len(self.utility.torrents["all"])), 1)
        statusfunc((" " + self.utility.lang.get('abbrev_running') + " %u " % len(self.utility.torrents["active"])), 2)
        statusfunc((" " + self.utility.lang.get('abbrev_downloading') + " %u " % len(self.utility.torrents["downloading"])), 3)
        statusfunc((" " + self.utility.lang.get('abbrev_seeding') + " %u " % len(self.utility.torrents["seeding"])), 4)
        statusfunc((" " + self.utility.lang.get('abbrev_pause') + " %u " % len(self.utility.torrents["pause"])), 5)
        
        try:
            if hasattr(self.utility, "bottomline2"):
                self.utility.bottomline2.updateCounters()
        except wx.PyDeadObjectError:
            pass

    def getDownUpConnections(self):
        # Ask UD/DL speed of all threads
        ########################################
        totalupload     = 0.0
        totaldownload   = 0.0
        totalconnections = 0

        for ABCTorrentTemp in self.utility.torrents["active"].keys():
            if ABCTorrentTemp.status.value != STATUS_PAUSE:
                downrate = ABCTorrentTemp.getColumnValue(COL_DLSPEED)
                uprate = ABCTorrentTemp.getColumnValue(COL_ULSPEED)
                
                ABCTorrentTemp.connection.rate["up"] = (uprate / 1024.0)
                ABCTorrentTemp.connection.rate["down"] = (downrate / 1024.0)
                
                totaldownload += downrate
                totalupload += uprate
                totalconnections += ABCTorrentTemp.getColumnValue(COL_CONNECTIONS)
                
        self.totals['up'] = totalupload
        self.totals_kb['up'] = (totalupload / 1024.0)
        
        self.totals['down'] = totaldownload
        self.totals_kb['down'] = (totaldownload / 1024.0)
        
        self.totals['connections'] = totalconnections
        
    def updateTrayAndStatusBar(self):
        maxuprate = self.ratemanager.MaxRate("up")
        if maxuprate == 0:
            upspeed = self.utility.speed_format(self.totals['up'], truncate = 1)
            upratecap = "oo"
        else:
            upspeed = self.utility.size_format(self.totals['up'], truncate = 1, stopearly = "KB", applylabel = False)
            upratecap = self.utility.speed_format((maxuprate * 1024), truncate = 0, stopearly = "KB")
        uploadspeed = upspeed + " / " + upratecap

        maxdownrate = self.ratemanager.MaxRate("down")
        if maxdownrate == 0:
            downspeed = self.utility.speed_format(self.totals['down'], truncate = 1)
            downratecap = "oo"
        else:
            downspeed = self.utility.size_format(self.totals['down'], truncate = 1, stopearly = "KB", applylabel = False)
            downratecap = self.utility.speed_format((maxdownrate * 1024), truncate = 0, stopearly = "KB")
        downloadspeed = downspeed + " / " + downratecap
        
        try:
            # update value in minimize icon
            ###########################################
            if self.utility.frame.tbicon is not None and self.utility.frame.tbicon.IsIconInstalled():
                icontext = "ABC" + "\n\n" + \
                           self.utility.lang.get('totaldlspeed') + " " + downloadspeed + "\n" + \
                           self.utility.lang.get('totalulspeed') + " " + uploadspeed + " "
                self.utility.frame.tbicon.SetIcon(self.utility.icon, icontext)

            # update in status bar
            ##########################################
            if self.utility.frame.abc_sb is not None:
                self.utility.frame.abc_sb.SetStatusText(" " + self.utility.lang.get('abbrev_connections') + " " + str(int(self.totals['connections'])), 6)
                self.utility.frame.abc_sb.SetStatusText(" " + self.utility.lang.get('abbrev_down') + " " + downloadspeed, 7)
                self.utility.frame.abc_sb.SetStatusText(" " + self.utility.lang.get('abbrev_up') + " " + uploadspeed, 8)
        except wx.PyDeadObjectError:
            pass
                                
    def CyclicalTasks(self):       
        self.getDownUpConnections()
            
        self.updateTrayAndStatusBar()

        self.ratemanager.RunTasks()
   
        try:
            # Run postponed deleting events
            while self.utility.window.postponedevents:
                ev = self.utility.window.postponedevents.pop(0)
                #print "POSTPONED EVENT : ", ev[0]
                ev[0](ev[1])
            self.utility.list.Enable()
        except wx.PyDeadObjectError:
            pass

        # Try invoking the scheduler
        # (just in case we need to start more stuff:
        #  should return almost immediately otherwise)
        self.Scheduler()

        # Start Timer
        ##########################################
        self.timers['frequent'] = Timer(2, self.CyclicalTasks)
        self.timers['frequent'].start()
            
    def InfrequentCyclicalTasks(self, update = True):
        if update:           
            try:
                if self.timers['infrequent'] is not None:
                    self.timers['infrequent'].cancel()
            except:
                pass
        
            self.updateTorrentList()

        self.timers['infrequent'] = Timer(300, self.InfrequentCyclicalTasks)
        self.timers['infrequent'].start()

               
    def onInvoke(self, event):
        if not self.flag.isSet():
            event.func(*event.args, **event.kwargs)

    def invokeLater(self, func, args = None, kwargs = None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
            
        if not self.flag.isSet():
            wx.PostEvent(self, InvokeEvent(func, args, kwargs))
              
    def updateAndInvoke(self, updateCounters = True, invokeLater = True):
        if updateCounters:
            # Update counter for running torrents
            self.UpdateRunningTorrentCounters()
        # Only invoke the scheduler if we're not shutting down
        if invokeLater:
            self.invokeLater(self.Scheduler)
      
    def updateTorrentList(self):
        torrentconfig = self.utility.torrentconfig
       
        torrentconfig.DeleteGroup()
       
        for ABCTorrentTemp in self.utility.torrents["all"]:
            ABCTorrentTemp.torrentconfig.writeSrc(False)
                        
#        try:
#            torrentconfig.DeleteGroup("dummygroup")
#        except:
#            pass

        torrentconfig.Flush()
        
    def getInactiveTorrents(self, numtorrents):
        if numtorrents < 0:
            numtorrents = 0

        torrents_inactive = self.utility.torrents["inactive"].keys()

        # Find which torrents are queued:
        inactivetorrents = [ABCTorrentTemp for ABCTorrentTemp in torrents_inactive if (ABCTorrentTemp.status.value == STATUS_QUEUE)]

        inactivelength = len(inactivetorrents)

        if inactivelength > numtorrents:
            # Sort first by listindex
            inactivetorrents.sort(key = attrgetter('listindex'))
                
            # Sort second by priority
            inactivetorrents.sort(key = attrgetter('prio'))
                
            # Slice off the number of torrents we need to start
            inactivetorrents = inactivetorrents[0:numtorrents]
                
        return inactivetorrents
        
    # Find new processes to start
    def Scheduler(self):
        if self.flag.isSet():
            return
        self.flag.set()
        
        numsimdownload = self.utility.config.Read('numsimdownload', "int")
            
        # Max number of torrents to start
        torrentstostart = numsimdownload - self.getProcCount()
        if torrentstostart < 0:
            torrentstostart = 0
           
        inactivestarted = 0
            
        # Start torrents
        inactivetorrents = self.getInactiveTorrents(torrentstostart)
                           
        for ABCTorrentTemp in inactivetorrents:
            change = ABCTorrentTemp.actions.resume()
            if change:
                inactivestarted += 1
                    
        torrentstostart = torrentstostart - inactivestarted
        
        if inactivestarted > 0:
            self.UpdateRunningTorrentCounters()
        
        self.flag.clear()
      
    def changeABCParams(self):
        self.utility.bottomline2.changeSpinners()
        
        for ABCTorrentTemp in self.utility.torrents["all"]:
            #Local doesn't need to affect with change ABC Params
            ABCTorrentTemp.connection.resetUploadParams()

        self.updateAndInvoke()

    # Move a line of the list from index1 to index2
    def MoveItems(self, listtomove, direction = 1):
        listtomove.sort()
        
        if direction == 1:
            # Moving items down, need to reverse the list
            listtomove.reverse()
            # Start offset will be one greater than the
            # first item in the resulting set
            startoffset = -1
            endoffset = 0
        # We're only going to allow moving up or down
        else:
            direction = -1
            # End offset will be one greater than the
            # last item in the set
            startoffset = 0
            endoffset = 1
        newloc = []

        for index in listtomove:
            if (direction == 1) and (index == len(self.utility.torrents["all"]) - 1):
                #Last Item can't move down anymore
                newloc.append(index)
            elif (direction == -1) and (index == 0):
                # First Item can't move up anymore
                newloc.append(index)
            elif newloc.count(index + direction) != 0 :
                #Don't move if we've already moved the next item
                newloc.append(index)
            else:
                ABCTorrentTemp = self.utility.torrents["all"].pop(index)
                self.utility.torrents["all"].insert(index + direction, ABCTorrentTemp)
                newloc.append(index + direction)

        # Only need update if something has changed
        if newloc:
            newloc.sort()
            start = newloc[0] + startoffset
            end = newloc[-1] + endoffset
            self.updateListIndex(startindex = start, endindex = end)
            
        return newloc

    def MoveItemsTop(self, selected):
        for index in selected:
            if index != 0:       # First Item can't move up anymore
                ABCTorrentTemp = self.utility.torrents["all"].pop(index)
                self.utility.torrents["all"].insert(0, ABCTorrentTemp)               

        if selected:
            self.updateListIndex(startindex = 0, endindex = selected[0])
        
        return True
        
    def MoveItemsBottom(self, selected):
        for index in selected:
            if index < len(self.utility.torrents["all"]) - 1:
                ABCTorrentTemp = self.utility.torrents["all"].pop(index)
                self.utility.torrents["all"].append(ABCTorrentTemp)
                
        if selected:
            self.updateListIndex(startindex = selected[0])
        
        return True

    # Clear all completed torrents from the list
    # 
    # Passing in a list of torrents to remove + move
    # allows for a torrent to auto-clear itself when
    # completed
    def clearAllCompleted(self, removelist = None):
        if removelist is None:
            removelist = [ABCTorrentTemp for ABCTorrentTemp in self.utility.torrents["inactive"].keys() if ABCTorrentTemp.status.isDoneUploading()]

        # See if we need to move the completed torrents
        # before we remove them from the list
        if self.utility.config.Read('movecompleted', "boolean"):
            self.utility.actionhandler.procMOVE(removelist)
        
        # Remove the torrents
        self.utility.actionhandler.procREMOVE(removelist)
            
    def clearScheduler(self):       
        # Stop frequent timer
        try:
            if self.timers['frequent'] is not None:
                self.timers['frequent'].cancel()
        except:
            pass

        torrents_inactive = self.utility.torrents["inactive"].keys()

        # Call shutdown on inactive torrents
        # (controller.stop will take care of the rest)
        for ABCTorrentTemp in torrents_inactive:
            ABCTorrentTemp.shutdown()

        # Stop all active torrents
        self.utility.controller.stop()
              
        # Update the torrent list
        self.updateTorrentList()
            
#        sys.stderr.write("\nDone clearing scheduler")

        # Stop the timer for updating the torrent list
        try:
            if self.timers['infrequent'] is not None:
                self.timers['infrequent'].cancel()
                del self.timers['infrequent']
        except:
            pass
            
    def getABCTorrent(self, index = -1, info_hash = None):
        # Find it by the index
        if index >= 0 and index < len(self.utility.torrents["all"]):
            return self.utility.torrents["all"][index]
        # Can't find it by index and the hash is none
        # We're out of luck
        elif info_hash is None:
            return None

        # Look for the hash value
        for ABCTorrentTemp in self.utility.torrents["all"]:
            if ABCTorrentTemp.infohash == info_hash:
                return ABCTorrentTemp

    def sortList(self, colid = 4, reverse = False):
        # Sort by uprate first
        self.utility.torrents["all"].sort(key = lambda x: x.getColumnValue(colid, -1.0), reverse = reverse)
        self.updateListIndex()

    def updateListIndex(self, startindex = 0, endindex = None):
        # Can't update indexes for things that aren't in the list anymore
        if startindex >= len(self.utility.torrents["all"]):
            return

        if startindex < 0:
            startindex = 0
        if endindex is None or endindex >= len(self.utility.torrents["all"]):
            endindex = len(self.utility.torrents["all"]) - 1

        for i in range(startindex, endindex + 1):
            ABCTorrentTemp = self.utility.torrents["all"][i]
            ABCTorrentTemp.listindex = i
            ABCTorrentTemp.updateColumns()
            ABCTorrentTemp.updateColor(force = True)
            ABCTorrentTemp.torrentconfig.writeSrc(False)
        
        self.utility.torrentconfig.Flush()
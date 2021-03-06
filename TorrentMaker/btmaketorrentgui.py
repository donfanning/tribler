#!/usr/bin/env python

# Written by Bram Cohen
# modified for multitracker by John Hoffman
# see LICENSE.txt for license information


import sys
import wx
import os

from os.path import join, isdir, exists, normpath, split
from threading import Event, Thread
from shutil import copy2

from traceback import print_exc

from TorrentMaker.btmakemetafile import make_meta_file, completedir

from Utility.helpers import union
from Utility.constants import * #IGNORE:W0611


wxEVT_INVOKE = wx.NewEventType()

def EVT_INVOKE(win, func):
    win.Connect(-1, -1, wxEVT_INVOKE, func)

class InvokeEvent(wx.PyEvent):
    def __init__(self, func, args, kwargs):
        wx.PyEvent.__init__(self)
        self.SetEventType(wxEVT_INVOKE)
        self.func = func
        self.args = args
        self.kwargs = kwargs


################################################################
#
# Class: MiscInfoPanel
#
# Panel for defining miscellaneous settings for a torrent
#
################################################################
class MiscInfoPanel(wx.Panel):
    def __init__(self, parent, dialog):
        wx.Panel.__init__(self, parent, -1)
        
        self.dialog = dialog
        self.utility = dialog.utility

        outerbox = wx.BoxSizer(wx.VERTICAL)

        # Created by:
        outerbox.Add(wx.StaticText(self, -1, self.utility.lang.get('createdby')), 0, wx.EXPAND|wx.ALL, 5)
        self.createdBy = wx.TextCtrl(self, -1)
        outerbox.Add(self.createdBy, 0, wx.EXPAND|wx.ALL, 5)

        # Comment:        
        outerbox.Add(wx.StaticText(self, -1, self.utility.lang.get('comment')), 0, wx.EXPAND|wx.ALL, 5)
        self.commentCtl = wx.TextCtrl(self, -1, size = (-1, 75), style = wx.TE_MULTILINE|wx.HSCROLL|wx.TE_DONTWRAP)        
        outerbox.Add(self.commentCtl, 0, wx.EXPAND|wx.ALL, 5)
      
        self.SetSizerAndFit(outerbox)
        
        self.loadValues()

    def loadValues(self, Read = None):
        if Read is None:
            Read = self.utility.makerconfig.Read
        
        self.createdBy.SetValue(Read('created_by'))
        self.commentCtl.SetValue(Read('comment'))

    def saveConfig(self, event = None):
        self.utility.makerconfig.Write('created_by', self.createdBy.GetValue())
        self.utility.makerconfig.Write('comment', self.commentCtl.GetValue())
        
    def getParams(self):
        params = {}
        
        comment = self.commentCtl.GetValue()
        if comment != '':
            params['comment'] = comment

        createdby = self.createdBy.GetValue()
        if comment != '':
            params['created by'] = createdby
            
        return params


################################################################
#
# Class: TrackerInfoPanel
#
# Panel for defining tracker settings for a torrent
#
################################################################
class TrackerInfoPanel(wx.Panel):
    def __init__(self, parent, dialog):
        wx.Panel.__init__(self, parent, -1)
        
        self.dialog = dialog
        self.utility = dialog.utility

        outerbox = wx.BoxSizer(wx.VERTICAL)

        announcesection_title = wx.StaticBox(self, -1, self.utility.lang.get('announce'))
        announcesection = wx.StaticBoxSizer(announcesection_title, wx.VERTICAL)

        self.announcehistory = []

        # Copy announce from torrent
        abutton = wx.Button(self, -1, self.utility.lang.get('copyannouncefromtorrent'))
        wx.EVT_BUTTON(self, abutton.GetId(), self.announceCopy)
        announcesection.Add(abutton, 0, wx.ALL, 5)

        # Announce url:
        announcesection.Add(wx.StaticText(self, -1, self.utility.lang.get('announceurl')), 0, wx.ALL, 5)

        announceurl_box = wx.BoxSizer(wx.HORIZONTAL)
       
        self.annCtl = wx.ComboBox(self, -1, "", choices = self.announcehistory, style=wx.CB_DROPDOWN)
        announceurl_box.Add(self.annCtl, 1, wx.ALIGN_CENTER_VERTICAL|wx.RIGHT, 5)
        
        button = wx.Button(self, -1, "+", size = (30, -1))
        button.SetToolTipString(self.utility.lang.get('add'))
        wx.EVT_BUTTON(self, button.GetId(), self.addAnnounce)
        announceurl_box.Add(button, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 3)

        button2 = wx.Button(self, -1, "-", size = (30, -1))
        button2.SetToolTipString(self.utility.lang.get('remove'))
        wx.EVT_BUTTON(self, button2.GetId(), self.removeAnnounce)
        announceurl_box.Add(button2, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 3)

        announcesection.Add(announceurl_box, 0, wx.EXPAND)

        # Announce List:        
        announcesection.Add(wx.StaticText(self, -1, self.utility.lang.get('announcelist')), 0, wx.EXPAND|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
       
        self.annListCtl = wx.TextCtrl(self, -1, size = (-1, 75), style = wx.TE_MULTILINE|wx.HSCROLL|wx.TE_DONTWRAP)
        self.annListCtl.SetToolTipString(self.utility.lang.get('multiannouncehelp'))
        announcesection.Add(self.annListCtl, 1, wx.EXPAND|wx.TOP, 5)
        
        outerbox.Add(announcesection, 0, wx.EXPAND|wx.ALL, 3)
      
        # HTTP Seeds:
        outerbox.Add(wx.StaticText(self, -1, self.utility.lang.get('httpseeds')), 0, wx.EXPAND|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
       
        self.httpSeeds = wx.TextCtrl(self, -1, size = (-1, 75), style = wx.TE_MULTILINE|wx.HSCROLL|wx.TE_DONTWRAP)
        self.httpSeeds.SetToolTipString(self.utility.lang.get('httpseedshelp'))
        outerbox.Add(self.httpSeeds, 1, wx.EXPAND|wx.ALL, 5)
      
        self.SetSizerAndFit(outerbox)
        
        self.loadValues()

    def loadValues(self, Read = None):
        if Read is None:
            Read = self.utility.makerconfig.Read
        
        self.annCtl.Clear()
        self.annCtl.SetValue(Read('announcedefault'))

        self.announcehistory = Read('announcehistory', "bencode-list")
        for announceurl in self.announcehistory:
            self.annCtl.Append(announceurl)

        self.annListCtl.SetValue(Read('announce-list'))
        self.httpSeeds.SetValue(Read('httpseeds'))

    def saveConfig(self, event = None):
        index = self.annCtl.GetSelection()
        if index != -1:
            self.utility.makerconfig.Write('announcedefault', self.annCtl.GetValue())
        self.utility.makerconfig.Write('announcehistory', self.announcehistory, "bencode-list")
        self.utility.makerconfig.Write('announce-list', self.annListCtl.GetValue())
        self.utility.makerconfig.Write('httpseeds', self.httpSeeds.GetValue())

    def addAnnounce(self, event = None):
        announceurl = self.annCtl.GetValue()

        # Don't add to the list if it's already present or the string is empty
        announceurl = announceurl.strip()
        if not announceurl or announceurl in self.announcehistory:
            return
       
        self.announcehistory.append(announceurl)
        self.annCtl.Append(announceurl)
        
    def removeAnnounce(self, event = None):
        index = self.annCtl.GetSelection()
        if index != -1:
            announceurl = self.annCtl.GetValue()
            self.annCtl.Delete(index)
            try:
                self.announcehistory.remove(announceurl)
            except:
                pass

    def announceCopy(self, event = None):
        dl = wx.FileDialog(self.dialog, 
                           self.utility.lang.get('choosedottorrentfiletouse'), 
                           '', 
                           '', 
                           self.utility.lang.get('torrentfileswildcard') + ' (*.torrent)|*.torrent', 
                           wx.OPEN)
        if dl.ShowModal() == wx.ID_OK:
            try:
                metainfo = self.utility.getMetainfo(dl.GetPath())
                if (metainfo is None):
                    return
                self.annCtl.SetValue(metainfo['announce'])
                if 'announce-list' in metainfo:
                    list = []
                    for tier in metainfo['announce-list']:
                        for tracker in tier:
                            list += [tracker, ', ']
                        del list[-1]
                        list += ['\n']
                    liststring = ''
                    for i in list:
                        liststring += i
                    self.annListCtl.SetValue(liststring+'\n\n')
                else:
                    self.annListCtl.SetValue('')
            except:
                return                

    def getAnnounceList(self):
        text = self.annListCtl.GetValue()
        list = []
        for tier in text.split('\n'):
            sublist = []
            tier.replace(',', ' ')
            for tracker in tier.split(' '):
                if tracker != '':
                    sublist += [tracker]
            if sublist:
                list.append(sublist)
        return list
        
    def getHTTPSeedList(self):
        text = self.httpSeeds.GetValue()
        list = []
        for tier in text.split('\n'):
            tier.replace(',', ' ')
            for tracker in tier.split(' '):
                if tracker != '':
                    list.append(tracker)
        return list

    def getParams(self):
        params = {}
        
        # Announce list
        annlist = self.getAnnounceList()
        if annlist:
            params['real_announce_list'] = annlist
        
        # Announce URL
        announceurl = None
        index = self.annCtl.GetSelection()
        if annlist and index == -1:
            # If we don't have an announce url specified,
            # try using the first value in announce-list
            tier1 = annlist[0]
            if tier1:
                announceurl = tier1[0]
        else:
            announceurl = self.annCtl.GetValue()
                
        if announceurl is None:
            # What should we do here?
            announceurl = ""
            
        params['announce'] = announceurl
                   
        # HTTP Seeds
        httpseedlist = self.getHTTPSeedList()
        if httpseedlist:
            params['real_httpseeds'] = httpseedlist
        
        return params


################################################################
#
# Class: FileInfoPanel
#
# Class for choosing a file when creating a torrent
#
################################################################        
class FileInfoPanel(wx.Panel):
    def __init__(self, parent, dialog):
        wx.Panel.__init__(self, parent, -1)
        
        self.dialog = dialog
        self.utility = dialog.utility

        outerbox = wx.BoxSizer(wx.VERTICAL)

        # Make torrent of:
        maketorrent_box = wx.BoxSizer(wx.HORIZONTAL)
        maketorrent_box.Add(wx.StaticText(self, -1, self.utility.lang.get('maketorrentof')), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        self.dirCtl = wx.TextCtrl(self, -1, '')
        maketorrent_box.Add(self.dirCtl, 1, wx.ALIGN_CENTER_VERTICAL|wx.EXPAND|wx.ALL, 5)

        button = wx.Button(self, -1, self.utility.lang.get('dir'), style = wx.BU_EXACTFIT)
        wx.EVT_BUTTON(self, button.GetId(), self.selectDir)
        maketorrent_box.Add(button, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        button2 = wx.Button(self, -1, self.utility.lang.get('file'), style = wx.BU_EXACTFIT)
        wx.EVT_BUTTON(self, button2.GetId(), self.selectFile)
        maketorrent_box.Add(button2, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        outerbox.Add(maketorrent_box, 0, wx.EXPAND)        

        # Piece size:
        piecesize_box = wx.BoxSizer(wx.HORIZONTAL)
        
        piecesize_box.Add(wx.StaticText(self, -1, self.utility.lang.get('piecesize')), 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        
        abbrev_mb = " " + self.utility.lang.get('MB')
        abbrev_kb = " " + self.utility.lang.get('KB')
        
        piece_choices = [self.utility.lang.get('automatic'), 
                         '2' + abbrev_mb, 
                         '1' + abbrev_mb, 
                         '512' + abbrev_kb, 
                         '256' + abbrev_kb, 
                         '128' + abbrev_kb, 
                         '64' + abbrev_kb, 
                         '32' + abbrev_kb]
        self.piece_length = wx.Choice(self, -1, choices = piece_choices)
        self.piece_length_list = [0, 21, 20, 19, 18, 17, 16, 15]
        piecesize_box.Add(self.piece_length, 0, wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)
        
        outerbox.Add(piecesize_box, 0, wx.EXPAND)
        

#        panel.DragAcceptFiles(True)
#        wx.EVT_DROP_FILES(panel, self.selectdrop)

        # Save torrent :
        savetorrentbox = wx.StaticBoxSizer(wx.StaticBox(self, -1, self.utility.lang.get('savetor')), wx.VERTICAL)

        self.savetorrb1 = wx.RadioButton(self, -1, self.utility.lang.get('savetordefault'), (-1, -1), (-1, -1), wx.RB_GROUP)
        savetorrb2 = wx.RadioButton(self, -1, self.utility.lang.get('savetorsource'), (-1, -1), (-1, -1))
        savetorrb3 = wx.RadioButton(self, -1, self.utility.lang.get('savetorask'), (-1, -1), (-1, -1))
        self.savetor = [self.savetorrb1, savetorrb2, savetorrb3]

        savetordefbox = wx.BoxSizer(wx.HORIZONTAL)
        savetordefbox.Add(self.savetorrb1, 0, wx.ALIGN_CENTER_VERTICAL)
        self.savetordeftext = wx.TextCtrl(self, -1, "")
        browsebtn = wx.Button(self, -1, "...", style = wx.BU_EXACTFIT)
        browsebtn.Bind(wx.EVT_BUTTON, self.onBrowseDir)
        savetordefbox.Add(self.savetordeftext, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, 5)
        savetordefbox.Add(browsebtn, 0, wx.ALIGN_CENTER_VERTICAL|wx.LEFT|wx.RIGHT, 3)
        savetorrentbox.Add(savetordefbox, 0, wx.EXPAND)
        
        savetorrentbox.Add(savetorrb2, 0)

        savetorrentbox.Add(savetorrb3, 0, wx.TOP, 4)

        outerbox.Add(savetorrentbox, 0, wx.EXPAND|wx.TOP|wx.BOTTOM, 5)

        optionalhash_title = wx.StaticBox(self, -1, self.utility.lang.get('makehash_optional'))
        optionalhash = wx.StaticBoxSizer(optionalhash_title, wx.VERTICAL)

        self.makehash_md5 = wx.CheckBox(self, -1, self.utility.lang.get('makehash_md5'))
        optionalhash.Add(self.makehash_md5, 0)

        self.makehash_crc32 = wx.CheckBox(self, -1, self.utility.lang.get('makehash_crc32'))
        optionalhash.Add(self.makehash_crc32, 0, wx.TOP, 4)

        self.makehash_sha1 = wx.CheckBox(self, -1, self.utility.lang.get('makehash_sha1'))
        optionalhash.Add(self.makehash_sha1, 0, wx.TOP, 4)
        
        outerbox.Add(optionalhash, 0, wx.EXPAND|wx.TOP|wx.BOTTOM, 5)

        self.startnow = wx.CheckBox(self, -1, self.utility.lang.get('startnow'))
        outerbox.Add(self.startnow, 0, wx.ALIGN_LEFT|wx.ALL, 5)

        self.SetSizerAndFit(outerbox)
        
        self.loadValues()

#        panel.DragAcceptFiles(True)
#        wx.EVT_DROP_FILES(panel, self.selectdrop)

    def loadValues(self, Read = None):
        if Read is None:
            Read = self.utility.makerconfig.Read
        self.startnow.SetValue(Read('startnow', "boolean"))
        self.makehash_md5.SetValue(Read('makehash_md5', "boolean"))
        self.makehash_crc32.SetValue(Read('makehash_crc32', "boolean"))
        self.makehash_sha1.SetValue(Read('makehash_sha1', "boolean"))
        
        self.savetor[Read('savetorrent', "int")].SetValue(True)        
        self.piece_length.SetSelection(Read('piece_size', "int"))
        self.savetordeftext.SetValue(Read('savetordeffolder'))
        

    def saveConfig(self, event = None):        
        self.utility.makerconfig.Write('startnow', self.startnow.GetValue(), "boolean")
        
        self.utility.makerconfig.Write('makehash_md5', self.makehash_md5.GetValue(), "boolean")
        self.utility.makerconfig.Write('makehash_crc32', self.makehash_crc32.GetValue(), "boolean")
        self.utility.makerconfig.Write('makehash_sha1', self.makehash_sha1.GetValue(), "boolean")
            
        self.utility.makerconfig.Write('savetordeffolder', self.savetordeftext.GetValue())

        for i in range(3):
            if self.savetor[i].GetValue():
                self.utility.makerconfig.Write('savetorrent', i)
                break
        self.utility.makerconfig.Write('piece_size', self.piece_length.GetSelection())

    def selectDir(self, event = None):
        dlg = wx.DirDialog(self.dialog, 
                           self.utility.lang.get('selectdir'), 
                           style = wx.DD_DEFAULT_STYLE | wx.DD_NEW_DIR_BUTTON)
        if dlg.ShowModal() == wx.ID_OK:
            self.dirCtl.SetValue(dlg.GetPath())
        dlg.Destroy()

    def onBrowseDir(self, event = None):
        dlg = wx.DirDialog(self.dialog, 
                           self.utility.lang.get('choosetordeffolder'), 
                           style = wx.DD_DEFAULT_STYLE | wx.DD_NEW_DIR_BUTTON)
        if dlg.ShowModal() == wx.ID_OK:
            self.savetordeftext.SetValue(dlg.GetPath())
        dlg.Destroy()

    def selectFile(self, event = None):
        dlg = wx.FileDialog(self.dialog, 
                            self.utility.lang.get('choosefiletouse'), 
                            '', 
                            '', 
                            self.utility.lang.get('allfileswildcard') + ' (*.*)|*.*', 
                            wx.OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.dirCtl.SetValue(dlg.GetPath())
        dlg.Destroy()

    def selectdrop(self, x):
        list = x.m_files
        self.dirCtl.SetValue(x[0])
    
    def getParams(self):
        params = {}
        self.targeted = []
        
        params['piece_size_pow2'] = self.piece_length_list[self.piece_length.GetSelection()]
        
        gethash = {}
        if self.makehash_md5.GetValue():
            gethash['md5'] = True
        if self.makehash_crc32.GetValue():
            gethash['crc32'] = True
        if self.makehash_sha1.GetValue():
            gethash['sha1'] = True   
        params['gethash'] = gethash
##
        for i in range(3):
            if self.savetor[i].GetValue():
                break
        
        if i == 0:
            defdestfolder = self.savetordeftext.GetValue()                    
#

            # Check if default download folder is not a file and create it if necessary
            if exists(defdestfolder):
                if not isdir(defdestfolder):
                    dlg = wx.MessageDialog(self, 
                                           message = self.utility.lang.get('notadir') + '\n' + \
                                                     self.utility.lang.get('savedtofolderwithsource'), 
                                           caption = self.utility.lang.get('error'), 
                                           style = wx.OK | wx.ICON_ERROR)
                    dlg.ShowModal()
                    dlg.Destroy()
                    defdestfolder = ""
            else:
                try:
                    os.makedirs(defdestfolder)
                except:
                    dlg = wx.MessageDialog(self, 
                                           message = self.utility.lang.get('invalidwinname') + '\n'+ \
                                                     self.utility.lang.get('savedtofolderwithsource'), 
                                           caption = self.utility.lang.get('error'), 
                                           style = wx.OK | wx.ICON_ERROR)
                    dlg.ShowModal()
                    dlg.Destroy()
                    defdestfolder = ""
                     

#                
            params['target'] = defdestfolder
                
            self.targeted = defdestfolder                 

        elif i == 2:
            dl = wx.DirDialog(self, style = wx.DD_DEFAULT_STYLE | wx.DD_NEW_DIR_BUTTON)
            result = dl.ShowModal()
            dl.Destroy()
            if result != wx.ID_OK:
                return
            params['target'] = dl.GetPath()
            self.targeted = dl.GetPath()
        else:
            self.targeted = ""

        return params
    
    def getTargeted(self):
        targeted = self.targeted
        return targeted


################################################################
#
# Class: TorrentMaker
#
# Creates the dialog for making a torrent
#
################################################################
class TorrentMaker(wx.Frame):
    def __init__(self, parent):
        self.parent = parent
        self.utility = self.parent.utility

        title = self.utility.lang.get('btfilemakertitle')
        wx.Frame.__init__(self, None, -1, title)

        if sys.platform == 'win32':
            self.SetIcon(self.utility.icon)

        panel = wx.Panel(self, -1)
        
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.notebook = wx.Notebook(panel, -1)
                
        self.fileInfoPanel = FileInfoPanel(self.notebook, self)
        self.notebook.AddPage(self.fileInfoPanel, self.utility.lang.get('fileinfo'))
        
        self.trackerInfoPanel = TrackerInfoPanel(self.notebook, self)
        self.notebook.AddPage(self.trackerInfoPanel, self.utility.lang.get('trackerinfo'))

        self.miscInfoPanel = MiscInfoPanel(self.notebook, self)
        self.notebook.AddPage(self.miscInfoPanel, self.utility.lang.get('miscinfo'))
        
        sizer.Add(self.notebook, 1, wx.EXPAND|wx.ALL, 5)        
        
        btnbox = wx.BoxSizer(wx.HORIZONTAL)
        b3 = wx.Button(panel, -1, self.utility.lang.get('saveasdefaultconfig'))
        btnbox.Add(b3, 0, wx.EXPAND)

        b2 = wx.Button(panel, -1, self.utility.lang.get('maketorrent'))
        btnbox.Add(b2, 0, wx.EXPAND|wx.LEFT|wx.RIGHT, 10)

        b4 = wx.Button(panel, -1, self.utility.lang.get('close'))
        btnbox.Add(b4, 0, wx.EXPAND)
        
        sizer.Add(btnbox, 0, wx.ALIGN_CENTER|wx.ALL, 10)

        wx.EVT_BUTTON(panel, b2.GetId(), self.complete)
        wx.EVT_BUTTON(panel, b3.GetId(), self.saveConfig)
        wx.EVT_BUTTON(panel, b4.GetId(), self.closeWin)

        panel.SetSizerAndFit(sizer)
        
        self.Fit()
        
        self.Show()

    def closeWin(self, event = None):
        self.utility.actions[ACTION_MAKETORRENT].torrentmaker = None
        
        savetordeffolder = self.fileInfoPanel.savetordeftext.GetValue()
        self.utility.makerconfig.Write('savetordeffolder', savetordeffolder)
        self.utility.makerconfig.Write('announcehistory', self.trackerInfoPanel.announcehistory, "bencode-list")

        self.Destroy()
        
    def saveConfig(self, event = None):
        self.fileInfoPanel.saveConfig()
        self.trackerInfoPanel.saveConfig()
        self.miscInfoPanel.saveConfig()
        
        self.utility.makerconfig.Flush()
    
    def complete(self, event = None):
        filename = self.fileInfoPanel.dirCtl.GetValue()
        if filename == '':
            dlg = wx.MessageDialog(self, message = self.utility.lang.get('youmustselectfileordir'), 
                caption = self.utility.lang.get('error'), style = wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()
            return
        
        params = self.fileInfoPanel.getParams()
        params = union(params, self.trackerInfoPanel.getParams())
        params = union(params, self.miscInfoPanel.getParams())

        try:
            CompleteDir(self, filename, params['announce'], params)
        except:
            oldstdout = sys.stdout
            sys.stdout = sys.stderr
            print_exc()
            sys.stdout = oldstdout


################################################################
#
# Class: CompleteDir
#
# Creating torrents for one or more files
#
################################################################
class CompleteDir:
    def __init__(self, parent, d, a, params):
        self.d = d
        self.a = a
        self.params = params
        self.parent = parent
        self.utility = self.parent.utility
        self.flag = Event()
        self.separatetorrents = False
        
        # See if we need to get md5sums for each file
        if 'gethash' in params:
            self.gethash = params['gethash']
        else:
            self.gethash = None
            
        # Can remove it from params before we pass things on
        if 'gethash' in params:
            del params['gethash']

        if isdir(d):
            self.choicemade = Event()
            frame = wx.Frame(None, -1, self.utility.lang.get('btmaketorrenttitle'), size = (1, 1))
            self.frame = frame
            panel = wx.Panel(frame, -1)
            gridSizer = wx.FlexGridSizer(cols = 1, vgap = 8, hgap = 8)
            gridSizer.AddGrowableRow(1)
            gridSizer.Add(wx.StaticText(panel, -1, 
                    self.utility.lang.get('dirnotice')), 0, wx.ALIGN_CENTER)
            gridSizer.Add(wx.StaticText(panel, -1, ''))

            b = wx.FlexGridSizer(cols = 3, hgap = 10)
            yesbut = wx.Button(panel, -1, self.utility.lang.get('yes'))
            def saidyes(e, self = self):
                self.frame.Destroy()
                self.separatetorrents = True
                self.begin()
            wx.EVT_BUTTON(frame, yesbut.GetId(), saidyes)
            b.Add(yesbut, 0)

            nobut = wx.Button(panel, -1, self.utility.lang.get('no'))
            def saidno(e, self = self):
                self.frame.Destroy()
                self.begin()
            wx.EVT_BUTTON(frame, nobut.GetId(), saidno)
            b.Add(nobut, 0)

            cancelbut = wx.Button(panel, -1, self.utility.lang.get('cancel'))
            def canceled(e, self = self):
                self.frame.Destroy()                
            wx.EVT_BUTTON(frame, cancelbut.GetId(), canceled)
            b.Add(cancelbut, 0)
            gridSizer.Add(b, 0, wx.ALIGN_CENTER)
            border = wx.BoxSizer(wx.HORIZONTAL)
            border.Add(gridSizer, 1, wx.EXPAND | wx.ALL, 4)
            
            panel.SetSizer(border)
            panel.SetAutoLayout(True)
            frame.Show()
            border.Fit(panel)
            frame.Fit()
        else:
            self.begin()

    def begin(self):
        if self.separatetorrents:
            frame = wx.Frame(None, -1, self.utility.lang.get('btmakedirtitle'), size = wx.Size(550, 250))
        else:
            frame = wx.Frame(None, -1, self.utility.lang.get('btmaketorrenttitle'), size = wx.Size(550, 250))
        self.frame = frame

        panel = wx.Panel(frame, -1)
        gridSizer = wx.FlexGridSizer(cols = 1, vgap = 15, hgap = 8)

        if self.separatetorrents:
            self.currentLabel = wx.StaticText(panel, -1, self.utility.lang.get('checkfilesize'))
        else:
            self.currentLabel = wx.StaticText(panel, -1, self.utility.lang.get('building') + self.d + '.torrent')
        gridSizer.Add(self.currentLabel, 0, wx.EXPAND)
        self.gauge = wx.Gauge(panel, -1, range = 1000, style = wx.GA_SMOOTH)
        gridSizer.Add(self.gauge, 0, wx.EXPAND)
        gridSizer.Add((10, 10), 1, wx.EXPAND)
        self.button = wx.Button(panel, -1, self.utility.lang.get('cancel'))
        gridSizer.Add(self.button, 0, wx.ALIGN_CENTER)
        gridSizer.AddGrowableRow(2)
        gridSizer.AddGrowableCol(0)

        g2 = wx.FlexGridSizer(cols = 1, vgap = 15, hgap = 8)
        g2.Add(gridSizer, 1, wx.EXPAND | wx.ALL, 25)
        g2.AddGrowableRow(0)
        g2.AddGrowableCol(0)
        panel.SetSizer(g2)
        panel.SetAutoLayout(True)
        wx.EVT_BUTTON(frame, self.button.GetId(), self.done)
        wx.EVT_CLOSE(frame, self.done)
        EVT_INVOKE(frame, self.onInvoke)
        frame.Show(True)
        Thread(target = self.complete).start()

    def complete(self):        
        try:
            if self.separatetorrents:
                completedir(self.d, self.a, self.params, self.flag, self.valCallback, self.fileCallback, gethash = self.gethash)
            else:
                make_meta_file(self.d, self.a, self.params, self.flag, self.valCallback, progress_percent = 1, gethash = self.gethash)
            if not self.flag.isSet():
                self.currentLabel.SetLabel(self.utility.lang.get('Done'))
                self.gauge.SetValue(1000)
                self.button.SetLabel(self.utility.lang.get('close'))
                self.frame.Refresh()
        except (OSError, IOError), e:
            self.currentLabel.SetLabel(self.utility.lang.get('error'))
            self.button.SetLabel(self.utility.lang.get('close'))
            dlg = wx.MessageDialog(None, 
                                   message = self.utility.lang.get('error') + ' - ' + str(e), 
                                   caption = self.utility.lang.get('error'), 
                                   style = wx.OK | wx.ICON_ERROR)
            dlg.ShowModal()
            dlg.Destroy()

        if self.parent.fileInfoPanel.startnow.GetValue():
            targeted = self.parent.fileInfoPanel.getTargeted()
            if not targeted:
                copy2(normpath(self.d) + '.torrent', os.path.join(self.utility.getConfigPath(), "torrent"))
            else:
                try:
                    copy2(join(targeted, split(normpath(self.d))[1]) + '.torrent', os.path.join(self.utility.getConfigPath(), "torrent"))
                except:
                    pass

    def valCallback(self, amount):
        self.invokeLater(self.onVal, [amount])

    def onVal(self, amount):
        self.gauge.SetValue(int(amount * 1000))

    def fileCallback(self, f):
        self.invokeLater(self.onFile, [f])

    def onFile(self, f):
        self.currentLabel.SetLabel(self.utility.lang.get('building') + join(self.d, f) + '.torrent')

    def onInvoke(self, event):
        if not self.flag.isSet():
            event.func(*event.args, **event.kwargs)

    def invokeLater(self, func, args = None, kwargs = None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        if not self.flag.isSet():
            wx.PostEvent(self.frame, InvokeEvent(func, args, kwargs))

    def done(self, event):
        self.flag.set()
        self.frame.Destroy()
        if self.parent.fileInfoPanel.startnow.GetValue():
            self.tmtordest = split(normpath(self.d))[1] + '.torrent'
            torrentsrc = os.path.join(self.utility.getConfigPath(), "torrent", self.tmtordest)
            self.utility.queue.addtorrents.AddTorrentFromFile(torrentsrc, dest = self.d)

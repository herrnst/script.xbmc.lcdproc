'''
    XBMC LCDproc addon

    Kodi broker / Update notification handler and information,
    data and state inquiry

    Copyright (C) 2012-2018 Team Kodi
    Copyright (C) 2012-2018 Daniel 'herrnst' Scheller

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

import json
import time

from .common import *
from .thread import *

class KodiBroker(Thread, xbmc.Monitor):

    ########
    # ctor
    def __init__(self):
        # init base class instances
        Thread.__init__(self)
        xbmc.Monitor.__init__(self)

        # prepare infobool strings to save some cpu ticks later
        self._cKaiToastActive = "Window.IsActive(" + str(WINDOW_IDS.WINDOW_DIALOG_KAI_TOAST) + ")"
        self._cVolumeBarActive = "Window.IsActive(" + str(WINDOW_IDS.WINDOW_DIALOG_VOLUME_BAR) + ")"

        # interval to use for async polling
        self._asyncinterval = 0.2

        self._useExecJRPC = True
        self._jrpcdebug = False
        self._counter = 0

    def jsonrpc_get(self, method, params):
        jsondata = {
            "jsonrpc": "2.0",
            "method": method,
            "id": method}

        if params:
            jsondata["params"] = params

        try:
            if self._jrpcdebug: log(LOGDEBUG, "==== JSONRPC debug begin ====")

            rpccmd = json.dumps(jsondata)
            if self._jrpcdebug: log(LOGDEBUG, "JSONRPC out: " + rpccmd)

            rpcreply = xbmc.executeJSONRPC(rpccmd)

            if self._jrpcdebug:
                log(LOGDEBUG, "JSONRPC in: " + rpcreply)
                log(LOGNOTICE, "==== JSONRPC debug end ====")

            rpcdata = json.loads(rpcreply)

            if rpcdata["id"] == method and rpcdata.has_key("result"):
                return rpcdata["result"]
        except Exception as e:
            log(LOGERROR, "Caught JSONRPC exception: %s" % (str(e)))

        return False

    def getlabels(self, labels):
        if self._useExecJRPC:
            return self.jsonrpc_get("XBMC.GetInfoLabels",
                {"labels": labels})

        ret = {}
        for label in labels:
            ret[label] = xbmc.getInfoLabel(label)

        return ret

    def getbools(self, bools):
        if self._useExecJRPC:
            return self.jsonrpc_get("XBMC.GetInfoBooleans",
                {"booleans": bools})

        ret = {}
        for bool in bools:
            ret[bool] = xbmc.getCondVisibility(bool)

        return ret

    ########
    # run(): background thread used for async state inquiry for all things
    # Kodi doesn't tell us on it's own (like player progress)
    def run(self):
        # take note of threadid and debug to Kodi log
        self.storethreadid()
        log(LOGDEBUG, "Started thread '%s'" % (self.getthreadid()))

        # keep on working until being told otherwise
        while not self.cancelled() and not self.waitForAbort(self._asyncinterval):
            self.syncStatePeriodic()

        log(LOGDEBUG, "Finished thread '%s'" % (self.getthreadid()))

    def syncStatePeriodic(self):
        # init local vars
        oldwindow = ""
        oldcontrol = ""

        # list of InfoLabels to load
        labels = self.getlabels([
            "MusicPlayer.Channels",
            "Player.Duration",
            "Player.Time",
            "System.CurrentWindow",
            "System.CurrentControl",
            "System.ScreenHeight",
            "System.Time(hh:mm:ss)",
            "VideoPlayer.AudioChannels",
        ])

        # list of InfoBools (aka. CondVisibility)
        bools = self.getbools([
            "PVR.IsRecording",
            "Player.Passthrough",
            self._cKaiToastActive,
            self._cVolumeBarActive
        ])

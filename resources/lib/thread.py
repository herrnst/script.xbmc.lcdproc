'''
    XBMC LCDproc addon

    Thread wrapper

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

import threading

from .common import *

class Thread(threading.Thread):

    ######
    # ctor
    def __init__(self):
        # init base class
        threading.Thread.__init__(self)

        # instance vars
        self._threadlock = threading.Lock()
        self._cancel = False
        self._type = self.__class__.__name__
        self._threadid = None

    def storethreadid(self):
        self._threadid = str(threading.current_thread())

    def getthreadid(self):
        return self._threadid

    def cancelled(self):
        return self._cancel

    def cancel(self):
        log(LOGDEBUG, "Cancelling worker thread %s" % (self._threadid))
        self._threadlock.acquire()
        self._cancel = True
        self._threadlock.release()

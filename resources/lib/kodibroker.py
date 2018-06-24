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

from .common import *
from .thread import *

class KodiBroker(Thread, xbmc.Monitor):

    ########
    # ctor
    def __init__(self):
        # init base class instances
        Thread.__init__(self)
        xbmc.Monitor.__init__(self)

        # interval to use for async polling
        self._asyncinterval = 0.2

    ########
    # run(): background thread used for async state inquiry for all things
    # Kodi doesn't tell us on it's own (like player progress)
    def run(self):
        # take note of threadid and debug to Kodi log
        self.storethreadid()
        log(LOGDEBUG, "Started thread '%s'" % (self.getthreadid()))

        # keep on working until being told otherwise
        while not self.cancelled():
            self.waitForAbort(self._asyncinterval)

        log(LOGDEBUG, "Finished thread '%s'" % (self.getthreadid()))

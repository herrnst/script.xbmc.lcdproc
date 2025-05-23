# SPDX-License-Identifier: GPL-2.0-or-later
#
# XBMC LCDproc addon
# Copyright (C) 2012-2024 Team Kodi
# Copyright (C) 2012-2024 Daniel 'herrnst' Scheller
#

import re
import time

import xbmc

from socket import *

from .settings import *
from .lcdbase import *

from .lcdproc_extra_imon import *
from .lcdproc_extra_mdm166a import *

from .infolabels import *

MAX_ROWS = 20
MAX_BIGDIGITS = 20
INIT_RETRY_INTERVAL = 2
INIT_RETRY_INTERVAL_MAX = 60

class LCDProc(LcdBase):
  def __init__(self, settings):
    self.m_bStop        = True
    self.m_lastInitAttempt = 0
    self.m_initRetryInterval = INIT_RETRY_INTERVAL
    self.m_used = True
    self.m_socket = None
    self.m_sockreadbuf = b''
    self.m_timeLastSockAction = time.time()
    self.m_timeSocketIdleTimeout = 2
    self.m_strLineText = [None]*MAX_ROWS
    self.m_strLineType = [None]*MAX_ROWS
    self.m_bstrLineIcon = [None]*MAX_ROWS
    self.m_strDigits = [None]*MAX_BIGDIGITS
    self.m_iProgressBarWidth = 0
    self.m_iProgressBarLine = -1
    self.m_bstrIconName = b"BLOCK_FILLED"
    self.m_iBigDigits = int(8) # 12:45:78 / colons count as digit
    self.m_iOffset = 1
    self.m_bstrSetLineCmds = b""
    self.m_cExtraIcons = None

    LcdBase.__init__(self, settings)

  def ReadUntil(self, separator):
    if not self.m_socket:
      return b""

    while separator not in self.m_sockreadbuf:
      data = self.m_socket.recv(1024)
      if not data:
        raise EOFError
      self.m_sockreadbuf += data

    line, tmp, self.m_sockreadbuf = self.m_sockreadbuf.partition(separator)

    return line

  def SendCommand(self, strCmd, bCheckRet):
    countcmds = strCmd.count(b'\n')
    sendcmd = strCmd
    ret = True

    # Single command without lf
    if countcmds < 1:
      countcmds = 1
      sendcmd += b"\n"

    try:
      # Send commands to LCDproc server
      self.m_socket.sendall(sendcmd)
    except Exception as ex:
      # Something bad happened, abort
      log(LOGERROR, "SendCommand(): Caught %s on m_socket.sendall()" % type(ex))
      return False

    # Update last socketaction timestamp
    self.m_timeLastSockAction = time.time()

    # Repeat for number of found commands
    for i in range(1, (countcmds + 1)):
      # Read in (multiple) responses
      while True:
        try:
          # Read server reply
          reply = self.ReadUntil(b"\n")
        except Exception as ex:
          # (Re)read failed, abort
          log(LOGERROR, "SendCommand(): Caught %s when reading back response(s)" % type(ex))
          return False

        # Skip these messages
        if reply[:6] == b'listen':
          continue
        elif reply[:6] == b'ignore':
          continue
        elif reply[:3] == b'key':
          continue
        elif reply[:9] == b'menuevent':
          continue

        # Response seems interesting, so stop here
        break

      if not bCheckRet:
        continue # no return checking desired, so be fine

      if strCmd == b'noop' and reply == b'noop complete':
        continue # noop has special reply

      if reply == b'success':
        continue

      ret = False

    # Leave information something undesired happened
    if ret is False:
      log(LOGWARNING, "Reply to '%s' was '%s'" % (strCmd.decode(self.m_strLCDEncoding), reply.decode(self.m_strLCDEncoding)))

    return ret

  def SetupScreen(self):
    # Add screen first
    if not self.SendCommand(b"screen_add xbmc", True):
      return False

    # Set screen priority
    if not self.SendCommand(b"screen_set xbmc -priority info", True):
      return False

    # Turn off heartbeat if desired
    if not self.m_Settings.getHeartBeat():
      if not self.SendCommand(b"screen_set xbmc -heartbeat off", True):
        return False

    # Initialize command list var
    strInitCommandList = b""

    # Setup widgets (scrollers and hbars first)
    for i in range(1,int(self.m_iRows)+1):
      # Text widgets
      strInitCommandList += b"widget_add xbmc lineScroller%i scroller\n" % (i)

      # Progress bars
      strInitCommandList += b"widget_add xbmc lineProgress%i hbar\n" % (i)

      # Reset bars to zero
      strInitCommandList += b"widget_set xbmc lineProgress%i 0 0 0\n" % (i)

      self.m_strLineText[i-1] = ""
      self.m_strLineType[i-1] = ""

    # Setup icons last
    for i in range(1,int(self.m_iRows)+1):
      # Icons
      strInitCommandList += b"widget_add xbmc lineIcon%i icon\n" % (i)

      # Default icon
      strInitCommandList += b"widget_set xbmc lineIcon%i 0 0 BLOCK_FILLED\n" % (i)

      self.m_bstrLineIcon[i-1] = b""

    for i in range(1,int(self.m_iBigDigits + 1)):
      # Big Digit
      strInitCommandList += b"widget_add xbmc lineBigDigit%i num\n" % (i)

      # Set Digit
      strInitCommandList += b"widget_set xbmc lineBigDigit%i 0 0\n" % (i)

      self.m_strDigits[i] = b""

    if not self.SendCommand(strInitCommandList, True):
      return False

    return True

  def Initialize(self):
    connected = False
    if not self.m_used:
      return False#nothing to do

    #don't try to initialize too often
    now = time.time()
    if (now - self.m_lastInitAttempt) < self.m_initRetryInterval:
      return False
    self.m_lastInitAttempt = now

    if self.Connect():
      if LcdBase.Initialize(self):
        # reset the retry interval after a successful connect
        self.m_initRetryInterval = INIT_RETRY_INTERVAL
        self.m_bStop = False
        connected = True

      else:
        log(LOGERROR, "Connection successful but LCD.xml has errors, aborting connect")

    if not connected:
      # preventively close socket
      self.CloseSocket()

      # give up after INIT_RETRY_INTERVAL_MAX (60) seconds
      if self.m_initRetryInterval > INIT_RETRY_INTERVAL_MAX:
        self.m_used = False
        log(LOGERROR,"Connect failed. Giving up. Please fix any connection problems and restart the addon.")
      else:
        self.m_initRetryInterval = self.m_initRetryInterval * 2
        log(LOGERROR,"Connect failed. Retry in %d seconds." % self.m_initRetryInterval)

    return connected

  def DetermineExtraSupport(self):
    rematch_imon = "SoundGraph iMON(.*)LCD"
    rematch_mdm166a = "Targa(.*)mdm166a"
    rematch_imonvfd = "Soundgraph(.*)VFD"

    bUseExtraIcons = self.m_Settings.getUseExtraElements()

    # Never cause script failure/interruption by this! This is totally optional!
    try:
      # Retrieve driver name for additional functionality
      self.m_socket.send(b"info\n")
      reply = self.ReadUntil(b"\n").strip().decode("ascii")

      # When the LCDd driver doesn't supply a valid string, inform and return
      if reply == "":
        log(LOGINFO, "Empty driver information reply")
        return

      log(LOGINFO, "Driver information reply: " + reply)

      if re.match(rematch_imon, reply):
        log(LOGINFO, "SoundGraph iMON LCD detected")
        if bUseExtraIcons:
          self.m_cExtraIcons = LCDproc_extra_imon()

        # override bigdigits counter, the imonlcd driver handles bigdigits
        # different: digits count for two columns instead of three
        self.m_iBigDigits = 7

      elif re.match(rematch_mdm166a, reply):
        log(LOGINFO, "Futaba/Targa USB mdm166a VFD detected")
        if bUseExtraIcons:
          self.m_cExtraIcons = LCDproc_extra_mdm166a()

      elif re.match(rematch_imonvfd, reply):
        log(LOGINFO, "SoundGraph iMON IR/VFD detected")

      if self.m_cExtraIcons is not None:
        self.m_cExtraIcons.Initialize()

    except:
      pass

  def Connect(self):
    self.CloseSocket()

    try:
      ip = self.m_Settings.getHostIp()
      port = self.m_Settings.getHostPort()
      log(LOGDEBUG,"Open " + str(ip) + ":" + str(port))

      self.m_socket = socket(AF_INET, SOCK_STREAM)
      self.m_socket.settimeout(15)
      self.m_socket.connect((ip, port))
      self.m_socket.settimeout(3)

    except Exception as ex:
      log(LOGERROR, "Connect(): Caught %s on initial connect, aborting" % type(ex))
      return False

    try:
      # Start a new session
      self.m_socket.send(b"hello\n")

      # Receive LCDproc data to determine row and column information
      reply = self.ReadUntil(b"\n").decode("ascii")
      log(LOGDEBUG,"Reply: " + reply)

      # parse reply by regex
      lcdinfo = re.match(r"^connect .+ protocol ([0-9\.]+) lcd wid (\d+) hgt (\d+) cellwid (\d+) cellhgt (\d+)$", reply)

      # if regex didn't match, LCDproc is incompatible or something's odd
      if lcdinfo is None:
        return False

      # protocol version must currently either be 0.3 or 0.4
      if float(lcdinfo.group(1)) not in [0.3, 0.4]:
        log(LOGERROR, "Only LCDproc protocols 0.3 and 0.4 supported (got " + lcdinfo.group(1) +")")
        return False

      # set up class vars
      self.m_iColumns = int(lcdinfo.group(2))
      self.m_iRows  = int(lcdinfo.group(3))
      self.m_iCellWidth = int(lcdinfo.group(4))
      self.m_iCellHeight = int(lcdinfo.group(5))

      # tell users what's going on
      log(LOGINFO, "Connected to LCDd at %s:%s, Protocol version %s - Geometry %sx%s characters (%sx%s pixels, %sx%s pixels per character)" % (str(ip), str(port), float(lcdinfo.group(1)), str(self.m_iColumns), str(self.m_iRows), str(self.m_iColumns * self.m_iCellWidth), str(self.m_iRows * self.m_iCellHeight), str(self.m_iCellWidth), str(self.m_iCellHeight)))

      # Set up BigNum values based on display geometry
      if self.m_iColumns < 13:
        self.m_iBigDigits = 0 # No clock
      elif self.m_iColumns < 17:
        self.m_iBigDigits = 5 # HH:MM
      elif self.m_iColumns < 20:
        self.m_iBigDigits = 7 # H:MM:SS on play, HH:MM on clock
      else:
        self.m_iBigDigits = 8 # HH:MM:SS

      # Check LCDproc if we can enable any extras or override values
      # (might override e.g. m_iBigDigits!)
      self.DetermineExtraSupport()

    except Exception as ex:
      log(LOGERROR,"Connect(): Caught %s during hello/info phase, aborting." % type(ex))
      return False

    if not self.SetupScreen():
      log(LOGERROR, "Screen setup failed!")
      return False

    return True

  def CloseSocket(self):
    if self.m_socket:
      # no pyexceptions, please, we're disconnecting anyway
      try:
        # if we served extra elements, (try to) reset them
        if self.m_cExtraIcons is not None:
          if not self.SendCommand(self.m_cExtraIcons.GetClearAllCmd(), True):
            log(LOGERROR, "CloseSocket(): Cannot clear extra icons")

        # do gracefully disconnect (send directly as we won't get any response on this)
        self.m_socket.send(b"bye\n")
        # and close socket afterwards
        self.m_socket.close()
      except:
        # exception caught on this, so what? :)
        pass

    # delete/cleanup extra support instance
    del self.m_cExtraIcons
    self.m_cExtraIcons = None

    self.m_sockreadbuf = b''
    self.m_socket = None

  def IsConnected(self):
    if not self.m_socket:
      return False

    # Ping only every SocketIdleTimeout seconds
    if (self.m_timeLastSockAction + self.m_timeSocketIdleTimeout) > time.time():
      return True

    if not self.SendCommand(b"noop", True):
      log(LOGERROR, "noop failed in IsConnected(), aborting!")
      return False

    return True

  def SetBackLight(self, iLight):
    if not self.m_socket:
      return
    log(LOGDEBUG, "Switch Backlight to: " + str(iLight))

    # Build command
    if iLight == 0:
      cmd = b"screen_set xbmc -backlight off\n"
    elif iLight > 0:
      cmd = b"screen_set xbmc -backlight on\n"

    # Send to server
    if not self.SendCommand(cmd, True):
      log(LOGERROR, "SetBackLight(): Cannot change backlight state")
      self.CloseSocket()

  def SetContrast(self, iContrast):
    #TODO: Not sure if you can control contrast from client
    return

  def Stop(self):
    self.CloseSocket()
    self.m_bStop = True

  def Suspend(self):
    if self.m_bStop or not self.m_socket:
      return

    # Build command to suspend screen
    cmd = b"screen_set xbmc -priority hidden\n"

    # Send to server
    if not self.SendCommand(cmd, True):
      log(LOGERROR, "Suspend(): Cannot suspend")
      self.CloseSocket()

  def Resume(self):
    if self.m_bStop or not self.m_socket:
      return

    # Build command to resume screen
    cmd = b"screen_set xbmc -priority info\n"

    # Send to server
    if not self.SendCommand(cmd, True):
      log(LOGERROR, "Resume(): Cannot resume")
      self.CloseSocket()

  def GetColumns(self):
    return int(self.m_iColumns)

  def GetBigDigitTime(self, mode):
      ret = ""

      if self.m_InfoLabels.IsPlayerPlaying():
        if not (mode == LCD_MODE.LCD_MODE_SCREENSAVER and self.m_InfoLabels.IsPlayerPaused()):
          ret = self.m_InfoLabels.GetPlayerTime()[-self.m_iBigDigits:]

      if ret == "": # no usable timestring, e.g. not playing anything
        strSysTime = self.m_InfoLabels.GetSystemTime()

        if self.m_iBigDigits >= 8: # return h:m:s
          ret = strSysTime
        elif self.m_iBigDigits >= 5: # return h:m when display too small
          ret = strSysTime[:5]

      return ret

  def SetBigDigits(self, strTimeString, bForceUpdate):
    iOffset = 1
    iDigitCount = 1
    iStringOffset = 0
    strRealTimeString = ""

    if strTimeString == "" or strTimeString == None:
      return

    iStringLength = int(len(strTimeString))

    if self.m_bCenterBigDigits:
      iColons = strTimeString.count(":")
      iWidth  = 3 * (iStringLength - iColons) + iColons
      iOffset = 1 + max(self.m_iColumns - iWidth, 0) / 2

    if iStringLength > self.m_iBigDigits:
      iStringOffset = len(strTimeString) - self.m_iBigDigits
      iOffset = 1;

    if self.m_iOffset != iOffset:
      # on offset change force redraw
      bForceUpdate = True
      self.m_iOffset = iOffset

    for i in range(int(iStringOffset), int(iStringLength)):
      if self.m_strDigits[iDigitCount] != strTimeString[i] or bForceUpdate:
        self.m_strDigits[iDigitCount] = strTimeString[i]

        if strTimeString[i] == ":":
          self.m_bstrSetLineCmds += b"widget_set xbmc lineBigDigit%i %i 10\n" % (iDigitCount, iOffset)
        elif strTimeString[i].isdigit():
          self.m_bstrSetLineCmds += b"widget_set xbmc lineBigDigit%i %i %s\n" % (iDigitCount, iOffset, strTimeString[i].encode(self.m_strLCDEncoding))
        else:
          self.m_bstrSetLineCmds += b"widget_set xbmc lineBigDigit%i 0 0\n" % (iDigitCount)

      if strTimeString[i] == ":":
        iOffset += 1
      else:
        iOffset += 3

      iDigitCount += 1

    while iDigitCount <= self.m_iBigDigits:
      if self.m_strDigits[iDigitCount] != "" or bForceUpdate:
        self.m_strDigits[iDigitCount] = ""
        self.m_bstrSetLineCmds += b"widget_set xbmc lineBigDigit%i 0 0\n" % (iDigitCount)

      iDigitCount += 1

  def SetProgressBar(self, percent, pxWidth):
    self.m_iProgressBarWidth = int(float(percent) * pxWidth)
    return self.m_iProgressBarWidth

  def SetPlayingStateIcon(self):
    bPlaying = self.m_InfoLabels.IsPlayerPlaying()
    bPaused = self.m_InfoLabels.IsPlayerPaused()
    bForwarding = self.m_InfoLabels.IsPlayerForwarding()
    bRewinding = self.m_InfoLabels.IsPlayerRewinding()

    self.m_bstrIconName = b"STOP"

    if bForwarding:
      self.m_bstrIconName = b"FF"
    elif bRewinding:
      self.m_bstrIconName = b"FR"
    elif bPaused:
      self.m_bstrIconName = b"PAUSE"
    elif bPlaying:
      self.m_bstrIconName = b"PLAY"

  def GetRows(self):
    return int(self.m_iRows)

  def ClearBigDigits(self, fullredraw = True):
    for i in range(1,int(self.m_iBigDigits + 1)):
      # Clear Digit
      if fullredraw:
        self.m_bstrSetLineCmds += b"widget_set xbmc lineBigDigit%i 0 0\n" % (i)
      self.m_strDigits[i] = ""

    # on full redraw, make sure all widget get redrawn by resetting their type
    if fullredraw:
      for i in range(0, int(self.GetRows())):
        self.m_strLineType[i] = ""
        self.m_strLineText[i] = ""
        self.m_bstrLineIcon[i] = b""

  def ClearLine(self, iLine):
    self.m_bstrSetLineCmds += b"widget_set xbmc lineIcon%i 0 0 BLOCK_FILLED\n" % (iLine)
    self.m_bstrSetLineCmds += b"widget_set xbmc lineProgress%i 0 0 0\n" % (iLine)
    self.m_bstrSetLineCmds += b"widget_set xbmc lineScroller%i 1 %i %i %i m 1 \"\"\n" % (iLine, iLine, self.m_iColumns, iLine)

  def SetLine(self, mode, iLine, strLine, dictDescriptor, bForce):
    if self.m_bStop or not self.m_socket:
      return

    if iLine < 0 or iLine >= int(self.m_iRows):
      return

    plTime = self.m_InfoLabels.GetPlayerTime()
    plDuration = self.m_InfoLabels.GetPlayerDuration()
    ln = iLine + 1
    bExtraForce = False
    drawLineText = False

    if self.m_strLineType[iLine] != dictDescriptor['type']:
      if dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_BIGSCREEN:
        self.ClearDisplay()
      else:
        if self.m_strLineType[iLine] == LCD_LINETYPE.LCD_LINETYPE_BIGSCREEN:
          self.ClearBigDigits()
        else:
          self.ClearLine(int(iLine + 1))

      self.m_strLineType[iLine] = dictDescriptor['type']
      bExtraForce = True

      if dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_PROGRESS and dictDescriptor['text'] != "":
        self.m_bstrSetLineCmds += b"widget_set xbmc lineScroller%i 1 %i %i %i m 1 \"%s\"\n" % (ln, ln, self.m_iColumns, ln, dictDescriptor['text'].encode(self.m_strLCDEncoding))

      if dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_PROGRESSTIME and dictDescriptor['text'] != "":
        self.m_bstrSetLineCmds += b"widget_set xbmc lineScroller%i 1 %i %i %i m 1 \"%s\"\n" % (ln, ln, self.m_iColumns, ln, dictDescriptor['text'].encode(self.m_strLCDEncoding))

    if dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_BIGSCREEN:
      strLineLong = self.GetBigDigitTime(mode)
    elif dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_PROGRESSTIME:
      strLineLong = plTime + self.m_bProgressbarBlank * (self.m_iColumns - len(plTime) - len(plDuration)) + plDuration
    else:
      strLineLong = strLine

    strLineLong.strip()

    iMaxLineLen = dictDescriptor['endx'] - (int(dictDescriptor['startx']) - 1)
    iScrollSpeed = self.m_Settings.getScrollDelay()
    bstrScrollMode = self.m_Settings.getLCDprocScrollMode().encode(self.m_strLCDEncoding)

    if len(strLineLong) > iMaxLineLen: # if the string doesn't fit the display...
      if iScrollSpeed != 0:            # add separator when scrolling enabled
        if bstrScrollMode == b"m":     # and scrollmode is marquee
          strLineLong += self.m_strScrollSeparator
      else:                                       # or cut off
        strLineLong = strLineLong[:iMaxLineLen]
        iScrollSpeed = 1

    iStartX = dictDescriptor['startx']

    # check if update is required
    if strLineLong != self.m_strLineText[iLine] or bForce:
      # bigscreen
      if dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_BIGSCREEN:
        self.SetBigDigits(strLineLong, bExtraForce)
      # progressbar line
      elif dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_PROGRESS:
        self.m_bstrSetLineCmds += b"widget_set xbmc lineProgress%i %i %i %i\n" % (ln, iStartX, ln, self.m_iProgressBarWidth)
      # progressbar line with time
      elif dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_PROGRESSTIME:
        drawLineText = True
        pLenFract = float(self.m_iColumns - int(len(plDuration) + len(plTime))) / self.m_iColumns
        pTimeLen = int(self.m_iProgressBarWidth * pLenFract)
        self.m_bstrSetLineCmds += b"widget_set xbmc lineProgress%i %i %i %i\n" % (ln, iStartX + len(plTime), ln, pTimeLen)
      # everything else (text, icontext)
      else:
        drawLineText = True
        if len(strLineLong) < iMaxLineLen and dictDescriptor['align'] != LCD_LINEALIGN.LCD_LINEALIGN_LEFT:
          iSpaces = iMaxLineLen - len(strLineLong)
          if dictDescriptor['align'] == LCD_LINEALIGN.LCD_LINEALIGN_RIGHT:
            iStartX += iSpaces
          elif dictDescriptor['align'] == LCD_LINEALIGN.LCD_LINEALIGN_CENTER:
            iStartX += int(iSpaces / 2)

      if drawLineText:
        self.m_bstrSetLineCmds += b"widget_set xbmc lineScroller%i %i %i %i %i %s %i \"%s\"\n" % (ln, iStartX, ln, self.m_iColumns, ln, bstrScrollMode, iScrollSpeed, re.escape(strLineLong.encode(self.m_strLCDEncoding, errors="replace")))

      # cache contents
      self.m_strLineText[iLine] = strLineLong

    if dictDescriptor['type'] == LCD_LINETYPE.LCD_LINETYPE_ICONTEXT:
      if self.m_bstrLineIcon[iLine] != self.m_bstrIconName or bExtraForce:
        self.m_bstrLineIcon[iLine] = self.m_bstrIconName

        self.m_bstrSetLineCmds += b"widget_set xbmc lineIcon%i 1 %i %s\n" % (ln, ln, self.m_bstrIconName)

  def ClearDisplay(self):
    log(LOGDEBUG, "Clearing display contents")

    # clear line buffer first
    self.FlushLines()

    # set all widgets to empty stuff and/or offscreen
    for i in range(1,int(self.m_iRows)+1):
      self.ClearLine(i)

    # add commands to clear big digits
    self.ClearBigDigits()

    # send to display
    self.FlushLines()

  def FlushLines(self):
      if len(self.m_bstrSetLineCmds) > 0:
        # Send complete command package
        self.SendCommand(self.m_bstrSetLineCmds, False)

        self.m_bstrSetLineCmds = b""

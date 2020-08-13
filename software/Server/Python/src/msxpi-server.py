# External module imports
import RPi.GPIO as GPIO
import time
import subprocess
import urllib2
import mmap
import fcntl,os
import sys
from subprocess import Popen,PIPE,STDOUT
from HTMLParser import HTMLParser
import datetime
import time
import glob
import array
import socket
import errno
import select
import base64
from random import randint

version = "0.9.0"
build   = "20200810.00001"
BLKSIZE = 8192

# Pin Definitons
csPin   = 21
sclkPin = 20
mosiPin = 16
misoPin = 12
rdyPin  = 25

SPI_SCLK_LOW_TIME = 0.001
SPI_SCLK_HIGH_TIME = 0.001

GLOBALRETRIES       =    5
SPI_INT_TIME        =    3000
PIWAITTIMEOUTOTHER  =    120     # seconds
PIWAITTIMEOUTBIOS   =    60      # seconds
SYNCTIMEOUT         =    5
BYTETRANSFTIMEOUT   =    5
SYNCTRANSFTIMEOUT   =    3
STARTTRANSFER       = 0xA0
SENDNEXT            = 0xA1
ENDTRANSFER         = 0xA2
READY               = 0xAA
ABORT               = 0xAD
WAIT                = 0xAE

RC_SUCCESS          =    0xE0
RC_INVALIDCOMMAND   =    0xE1
RC_CRCERROR         =    0xE2
RC_TIMEOUT          =    0xE3
RC_INVALIDDATASIZE  =    0xE4
RC_OUTOFSYNC        =    0xE5
RC_FILENOTFOUND     =    0xE6
RC_FAILED           =    0xE7
RC_CONNERR          =    0xE8
RC_WAIT             =    0xE9
RC_READY            =    0xEA
RC_SUCCNOSTD        =    0XEB
RC_FAILNOSTD        =    0XEC
RC_ESCAPE           =    0xED
RC_UNDEFINED        =    0xEF

st_init             =    0       # waiting loop, waiting for a command
st_cmd              =    1       # transfering data for a command
st_recvdata         =    2
st_senddata         =    4
st_synch            =    5       # running a command received from MSX
st_runcmd           =    6
st_shutdown         =    99

NoTimeOutCheck      = False
TimeOutCheck        = True

MSXPIHOME = "/home/msxpi"
RAMDISK = "/media/ramdisk"
TMPFILE = RAMDISK + "/msxpi.tmp"

def init_spi_bitbang():
# Pin Setup:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(csPin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(sclkPin, GPIO.OUT)
    GPIO.setup(mosiPin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(misoPin, GPIO.OUT)
    GPIO.setup(rdyPin, GPIO.OUT)

def tick_sclk():
    GPIO.output(sclkPin, GPIO.HIGH)
    #time.sleep(SPI_SCLK_HIGH_TIME)
    GPIO.output(sclkPin, GPIO.LOW)
    #time.sleep(SPI_SCLK_LOW_TIME)

def SPI_MASTER_transfer_byte(byte_out):
    #print "transfer_byte:sending",hex(byte_out)
    byte_in = 0
    tick_sclk()
    for bit in [0x80,0x40,0x20,0x10,0x8,0x4,0x2,0x1]:
        if (byte_out & bit):
            GPIO.output(misoPin, GPIO.HIGH)
        else:
            GPIO.output(misoPin, GPIO.LOW)

        GPIO.output(sclkPin, GPIO.HIGH)
        #time.sleep(SPI_SCLK_HIGH_TIME)
        
        if GPIO.input(mosiPin):
            byte_in |= bit
    
        GPIO.output(sclkPin, GPIO.LOW)
        #time.sleep(SPI_SCLK_LOW_TIME)

    tick_sclk()
    #print "transfer_byte:received",hex(byte_in),":",chr(byte_in)
    return byte_in

def piexchangebyte(byte_out):
    rc = RC_SUCCESS
    
    GPIO.output(rdyPin, GPIO.HIGH)
    while(GPIO.input(csPin)):
        ()

    byte_in = SPI_MASTER_transfer_byte(byte_out)
    GPIO.output(rdyPin, GPIO.LOW)

    #print "piexchangebyte: received:",hex(mymsxbyte)
    return byte_in

def recvdatablock():
    buffer = bytearray()
    bytecounter = 0
    crc = 0
    rc = RC_SUCCESS
    
    msxbyte = piexchangebyte(SENDNEXT)
    if (msxbyte != SENDNEXT):
        print("recvdatablock:Out of sync with MSX")
        rc = RC_OUTOFSYNC
    else:
        dsL = piexchangebyte(SENDNEXT)
        dsM = piexchangebyte(SENDNEXT)
        datasize = dsL + 256 * dsM
        
        #print "recvdatablock:Received blocksize =",datasize
        while(datasize>bytecounter):
            msxbyte = piexchangebyte(SENDNEXT)
            buffer.append(msxbyte)
            crc ^= msxbyte
            bytecounter += 1

        msxcrc = piexchangebyte(crc)
        if (msxcrc != crc):
            rc = RC_CRCERROR

    #print "recvdatablock:exiting with rc = ",hex(rc)
    return [rc,buffer]

def sendstdmsg(rc, message):
    piexchangebyte(rc)
    senddatablock(message,len(message),0,1)

def senddatablock(buf,blocksize,blocknumber,attempts=1):

    crc = 0
    rc = RC_FAILED
    
    bufsize = len(buf)
    bufpos = blocksize*blocknumber

    if (blocksize <= bufsize - bufpos):
        thisblocksize = blocksize
    else:
        thisblocksize = bufsize - bufpos
        if thisblocksize < 0:
            thisblocksize = 0

    msxbyte = piexchangebyte(SENDNEXT)

    if (msxbyte != SENDNEXT):
        print "senddatablock:Out of sync with MSX, waiting SENDNEXT, received",hex(msxbyte),hex(msxbyte)
        return RC_OUTOFSYNC
    else:
        piexchangebyte(thisblocksize % 256)
        piexchangebyte(thisblocksize / 256)
        if thisblocksize == 0:
            return ENDTRANSFER

    piexchangebyte(attempts)

    while (attempts > 0 and rc != RC_SUCCESS):
        bytecounter = 0
        while(bytecounter < thisblocksize):
            pibyte = ord(buf[bufpos+bytecounter])
            piexchangebyte(pibyte)
            #print(bytecounter,bufpos+bytecounter,chr(pibyte))
            if bufpos != 2:
                crc ^= pibyte
            bytecounter += 1

        attempts -= 1

        msxcrc = piexchangebyte(crc)
        #print("senddatablock:CRC RPi:MSX = ",crc,msxcrc)
        if (msxcrc != crc):
            rc = RC_CRCERROR
            print("RC_CRCERROR")
        else:
            rc = RC_SUCCESS
    
    #print("senddatablock exit:",hex(rc))
    return rc 


#   senddatablockC(TimeOutCheck,buffer,index+initpos,blocksize,True)
def senddatablockC(flag1,buf,initpos,size,flag2):
    print("senddatablock:starting")
    fh = open(RAMDISK+'/msxpi.tmp', 'wb')
    fh.write(buf[initpos:initpos+size])
    fh.flush()
    fh.close()
    print "senddatablockC:Calling senddatablock.msx:",initpos,size
    cmd = "sudo " + RAMDISK + "/senddatablock.msx " + RAMDISK + "/msxpi.tmp"
    rc = subprocess.call(cmd, shell=True)
    init_spi_bitbang()
    GPIO.output(rdyPin, GPIO.LOW)
    print "Exiting senddatablockC:call returned:",hex(rc)
    return rc

def getpath(basepath, path):

    path=path.strip().rstrip(' \t\r\n\0')
    if  path.startswith('/'):
        urltype = 0 # this is an absolute local path
        newpath = path
    elif (path.startswith('http') or \
          path.startswith('ftp') or \
          path.startswith('nfs') or \
          path.startswith('smb')):
        urltype = 2 # this is an absolute network path
        newpath = path
    elif basepath.startswith('/'):
        urltype = 1 # this is an relative local path
        newpath = basepath + "/" + path
    elif (basepath.startswith('http') or \
          basepath.startswith('ftp') or \
          basepath.startswith('nfs') or \
          basepath.startswith('smb')):
        urltype = 3 # this is an relative network path
        newpath = basepath + "/" + path

    return [urltype, newpath]

# create a subclass and override the handler methods
class MyHTMLParser(HTMLParser):
    def __init__(self):
        self.reset()
        self.NEWTAGS = []
        self.NEWATTRS = []
        self.HTMLDATA = []
    def handle_starttag(self, tag, attrs):
        self.NEWTAGS.append(tag)
        self.NEWATTRS.append(attrs)
    def handle_data(self, data):
        self.HTMLDATA.append(data)
    def clean(self):
        self.NEWTAGS = []
        self.NEWATTRS = []
        self.HTMLDATA = []

def msxdos_inihrd(filename, access=mmap.ACCESS_WRITE):
    #print "msxdos_inihrd:Starting"
    size = os.path.getsize(filename)
    if (size>0):
        fd = os.open(filename, os.O_RDWR)
        rc = mmap.mmap(fd, size, access=access)
    else:
        rc = RC_FAILED

    return rc

def dos83format(fname):
    name = '        '
    ext = '   '

    finfo = fname.split('.')

    name = str(finfo[0]).ljust(8)
    if len(finfo) == 2:
        ext = str(finfo[1]).ljust(3)
    
    return name+ext

def ini_fcb(fname):

    fpath = fname.split(':')
    if len(fpath) == 1:
        msxfile = str(fpath[0])
        msxdrive = 0
    else:
        msxfile = str(fpath[1])
        drvletter = str(fpath[0]).upper()
        msxdrive = ord(drvletter) - 64

    #convert filename to 8.3 format using all 11 positions required for the FCB
    msxfcbfname = dos83format(msxfile)

    #print("Drive, Filename:",msxdrive,msxfcbfname)

    # send FCB structure to MSX
    piexchangebyte(msxdrive)
    for i in range(0,11):
        piexchangebyte(ord(msxfcbfname[i]))

def prun(cmd):
    piexchangebyte(RC_WAIT)
    rc = RC_SUCCESS

    if (cmd.strip() == '' or len(cmd.strip()) == 0):
        print "prun:syntax error"
        sendstdmsg(RC_FAILED,"Syntax: prun <command> <::> command\nTo pipe a command to other, use :: instead of |")
        rc = RC_FAILED
    else:
        cmd = cmd.replace('::','|')
        try:

            p = Popen(cmd.decode(), shell=True, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
            buf = p.stdout.read()
            if len(buf) == 0:
                buf = "Pi:Command did not return any output.\n"

            sendstdmsg(rc,buf)

        except Exception as e:
            rc = RC_FAILED
            sendstdmsg(rc,"Pi:Error running the command.\n"+str(e)+'\n')

    #print "prun:exiting rc:",hex(rc)
    return rc

def pdir(path):
    msxbyte = piexchangebyte(RC_WAIT)
    global psetvar
    basepath = psetvar[0][1]
    rc = RC_SUCCESS
    #print "pdir:starting"

    if (msxbyte == SENDNEXT):
        urlcheck = getpath(basepath, path)
        if (urlcheck[0] == 0 or urlcheck[0] == 1):
            if (path.strip() == '*'):
                prun('ls -l ' + urlcheck[1])
            elif ('*' in path):
                numChilds = path.count('/')
                fileDesc = path.rsplit('/', 1)[numChilds].replace('*','')
                if (fileDesc == '' or len(fileDesc) == 0):
                    fileDesc = '.'
                prun('ls -l ' + urlcheck[1].rsplit('/', 1)[0] + '/|/bin/grep '+ fileDesc)
            else:
                prun('ls -l ' + urlcheck[1])
        else:
            parser = MyHTMLParser()
            try:
                htmldata = urllib2.urlopen(urlcheck[1].decode()).read()
                parser = MyHTMLParser()
                parser.feed(htmldata)
                buf = " ".join(parser.HTMLDATA)
                piexchangebyte(RC_SUCCESS)
                rc = senddatablock(buf,len(buf),0,1)

            except urllib2.HTTPError as e:
                rc = RC_FAILED
                print "pdir:http error "+ str(e)
                sendstdmsg(rc,str(e))
    else:
        rc = RC_FAILNOSTD
        print "pdir:out of sync in RC_WAIT"

    #print "pdir:exiting rc:",hex(rc)
    return rc

def pcd(path):    
    msxbyte = piexchangebyte(RC_WAIT)
    rc = RC_SUCCESS
    global psetvar
    basepath = psetvar[0][1]
    newpath = basepath
    
    #print "pcd:starting basepath:path=",basepath + ":" + path

    if (msxbyte == SENDNEXT):
        if (path == '' or path.strip() == "."):
            sendstdmsg(rc,basepath+'\n')
        elif (path.strip() == ".."):
            newpath = basepath.rsplit('/', 1)[0]
            if (newpath == ''):
                newpath = '/'
            psetvar[0][1] = newpath
            sendstdmsg(rc,str(newpath+'\n'))
        else:
            #print "pcd:calling getpath"
            urlcheck = getpath(basepath, path)
            newpath = urlcheck[1]

            if (newpath[:4] == "http" or \
                newpath[:3] == "ftp" or \
                newpath[:3] == "nfs" or \
                newpath[:3] == "smb"):
                rc = RC_SUCCESS
                psetvar[0][1] = newpath
                sendstdmsg(rc,str(newpath+'\n'))
            else:
                newpath = str(newpath)
                if (os.path.isdir(newpath)):
                    psetvar[0][1] = newpath
                    sendstdmsg(rc,newpath+'\n')
                elif (os.path.isfile(str(newpath))):
                    sendstdmsg(RC_FAILED,"Pi:Error - not a folder")
                else:
                    sendstdmsg(RC_FAILED,"Pi:Error - path not found")
    else:
        rc = RC_FAILNOSTD
        print "pcd:out of sync in RC_WAIT"

    return [rc, newpath]

def pcopy(path='',inifcb=True):
    piexchangebyte(RC_WAIT)

    buf = ''
    rc = RC_SUCCESS

    global psetvar
    basepath = psetvar[0][1]
    
    if (path.startswith('http') or \
        path.startswith('ftp') or \
        path.startswith('nfs') or \
        path.startswith('smb') or \
        path.startswith('/')):
        fileinfo = path
    elif path == '':
        fileinfo = basepath
    else: 
        fileinfo = basepath+'/'+path

    fileinfo = fileinfo.split()

    if len(fileinfo) == 1:
        fname_rpi = str(fileinfo[0])
        fname_msx_0 = fname_rpi.split('/')
        fname_msx = str(fname_msx_0[len(fname_msx_0)-1])
    elif len(fileinfo) == 2:
        fname_rpi = str(fileinfo[0])
        fname_msx = str(fileinfo[1])
    else:
        print("Pi:Command line parametrs invalid.")
        sendstdmsg(RC_FAILED,"Pi:Command line parametrs invalid.")
        return RC_FAILED

    urlcheck = getpath(basepath, path)
    # basepath 0 local filesystem
    if (urlcheck[0] == 0 or urlcheck[0] == 1):
        try:
            with open(fname_rpi, mode='rb') as f:
                buf = f.read()
            filesize = len(buf)
 
        except Exception as e:
            print("pcopy:",str(e))
            sendstdmsg(RC_FAILED,"Pi:"+str(e)+'\n') 
            return RC_FAILED

    else:
        try:
            urlhandler = urllib2.urlopen(fname_rpi)
            #print("pcopy:urlopen rc:",urlhandler.getcode())
            buf = urlhandler.read()
            filesize = len(buf)
            
        except Exception as e:
            rc = RC_FAILED
            print "pcopy:http error "+ str(e)
            sendstdmsg(RC_FAILED,"Pi:"+str(e))
    
    if rc == RC_SUCCESS:
        if filesize == 0:
            sendstdmsg(RC_FILENOTFOUND,"Pi:No valid data found")
        else:
            if inifcb:
                msxbyte = piexchangebyte(RC_SUCCESS)
                ini_fcb(fname_msx)
            else:
                if filesize > 32768:
                    return RC_INVALIDDATASIZE

                msxbyte = piexchangebyte(RC_SUCCESS)

            blocknumber = 0   
            while (rc == RC_SUCCESS):
                rc = senddatablock(buf,BLKSIZE,blocknumber,attempts=1)
                if rc == RC_SUCCESS:
                    blocknumber += 1
    return rc

def ploadr(path=''):
    rc = pcopy(path,False)
    if rc == RC_INVALIDDATASIZE:
        sendstdmsg(rc,"Pi:Error - Not valid 8/16/32KB ROM")

def pdate(parms = ''):
    msxbyte = piexchangebyte(RC_WAIT)

    rc = RC_FAILED
    
    if (msxbyte == SENDNEXT):
        now = datetime.datetime.now()

        msxbyte = piexchangebyte(RC_SUCCESS)
        if (msxbyte == SENDNEXT):
            piexchangebyte(now.year & 0xff)
            piexchangebyte(now.year >>8)
            piexchangebyte(now.month)
            piexchangebyte(now.day)
            piexchangebyte(now.hour)
            piexchangebyte(now.minute)
            piexchangebyte(now.second)
            piexchangebyte(0)
            buf = "Pi:Ok\n"
            senddatablock(buf,len(buf),0,1)
            rc = RC_SUCCESS
        else:
            print "pdate:out of sync in SENDNEXT"
    else:
        print "pdate:out of sync in RC_WAIT"

    return rc

def pplay(cmd):
    rc = RC_SUCCESS
    
    cmd = "bash " + RAMDISK + "/pplay.sh " + " PPLAY "+psetvar[0][1]+ " "+cmd+" >" + RAMDISK + "/msxpi.tmp"
    cmd = str(cmd)
    
    #print "pplay:starting command:len:",cmd,len(cmd)

    piexchangebyte(RC_WAIT)
    try:
        p = subprocess.call(cmd, shell=True)
        buf = msxdos_inihrd(RAMDISK + "/msxpi.tmp")
        if (buf == RC_FAILED):
            sendstdmsg(RC_SUCCESS,"Pi:Ok\n")
        else:
            sendstdmsg(rc,buf)
    except subprocess.CalledProcessError as e:
        print "pplay:Error:",p
        rc = RC_FAILED
        sendstdmsg(rc,"Pi:Error\n"+str(e))
    
    #print "pplay:exiting rc:",hex(rc)
    return rc

def pset(cmd=''):
    piexchangebyte(RC_WAIT)

    global psetvar
    
    rc = RC_SUCCESS
    buf = "Pi:Error\nSyntax: pset set <var> <value>"
    cmd = cmd.strip()

    if (len(cmd)==0 or cmd[:1] == "d" or cmd[:1] == "D"):
        s = str(psetvar)
        buf = s.replace(", ",",").replace("[[","").replace("]]","").replace("],","\n").replace("[","").replace(",","=").replace("'","")
    
    elif (cmd[:1] == "s" or cmd[:1] == "S"):
        cmd=cmd.split(" ")
        found = False
        if (len(cmd) == 3):
            for index in range(0,len(psetvar)):
                if (psetvar[index][0] == str(cmd[1])):
                    psetvar[index][1] = str(cmd[2])
                    found = True
                    buf = "Pi:Ok\n"
                    rc_text = psetvar[index][0];
                    break

            if (not found):
                for index in range(7,len(psetvar)):
                    if (psetvar[index][0] == "free"):
                        psetvar[index][0] = str(cmd[1])
                        psetvar[index][1] = str(cmd[2])
                        found = True
                        buf = "Pi:Ok\n"
                        rc_text = psetvar[index][0];
                        break

            if (not found):
                rc = RC_FAILED
                rc_text = '';
                buf = "Pi:Erro setting parameter"
        else:
            rc = RC_FAILED
            
    sendstdmsg(rc,buf)

    return rc

def pwifi(parms=''):
    piexchangebyte(RC_WAIT)

    global psetvar
    wifissid = psetvar[4][1]
    wifipass = psetvar[5][1]
    rc = RC_SUCCESS
    cmd=parms.decode().strip()

    if (len(cmd)==0):
        sendstdmsg(RC_FAILED,"Pi:Syntax error.\nUsage: pwifi display | set")
        return RC_FAILED

    elif (cmd[:1] == "s" or cmd[:1] == "S"):
        buf = "country=GB\n\nctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev\nupdate_config=1\nnetwork={\n"
        buf = buf + "\tssid=\"" + wifissid
        buf = buf + "\"\n\tpsk=\"" + wifipass
        buf = buf + "\"\n}\n"

        os.system("sudo cp -f /etc/wpa_supplicant/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf.bak")
        f = open(RAMDISK + "/wpa_supplicant.conf","w")
        f.write(buf)
        f.close()
        os.system("sudo cp -f " + RAMDISK + "/wpa_supplicant.conf /etc/wpa_supplicant/wpa_supplicant.conf")
        cmd = cmd.strip().split(" ")
        if (len(cmd) == 2 and cmd[1] == "wlan1"):
            prun("sudo ifdown wlan1 && sleep 1 && sudo ifup wlan1")
        else:
            prun("sudo ifdown wlan0 && sleep 1 && sudo ifup wlan0")
        rc = RC_SUCCESS
    else:
        prun("ip a | grep '^1\\|^2\\|^3\\|^4\\|inet'|grep -v inet6")
    
    return rc

def pver(parms=''):
    piexchangebyte(RC_WAIT)
    global version,build
    ver = "MSXPi Server Version "+version+" Build "+build
    sendstdmsg(RC_SUCCESS,ver)

""" ============================================================================
    msxpi-server.py
    main program starts here
    ============================================================================
"""

psetvar = [['PATH','/home/msxpi'], \
           ['DRIVE0','disks/msxpiboot.dsk'], \
           ['DRIVE1','disks/50dicas.dsk'], \
           ['WIDTH','80'], \
           ['WIFISSID','MYWIFI'], \
           ['WIFIPWD','MYWFIPASSWORD'], \
           ['DSKTMPL','disks/msxpi_720KB_template.dsk'], \
           ['IRCNICK','msxpi'], \
           ['IRCADDR','chat.freenode.net'], \
           ['IRCPORT','6667'], \
           ['WUPPH','351966764458'], \
           ['WUPPW','D4YQDfsnY3KIgW4azGdtYDbMAO4='], \
           ['free','free'], \
           ['free','free'], \
           ['free','free'], \
           ['free','free'], \
           ['free','free'], \
           ['free','free'], \
           ['free','free'], \
           ['free','free'], \
           ]

WUPGRP = {'554191119326-1399041454@g.us' : 'MSXBr', '447840924680-1486475091@g.us' :'MSXPi', '447840924680-1515184325@g.us' : 'MSXPiTest'}

# Initialize disk system parameters
sectorInfo = [0,0,0,0]
numdrives = 0

# Load the disk images into a memory mapped variable
drive0Data = msxdos_inihrd(psetvar[1][1])
drive1Data = msxdos_inihrd(psetvar[2][1])

# irc
channel = "#msxpi"

init_spi_bitbang()
GPIO.output(rdyPin, GPIO.LOW)
print "GPIO Initialized\n"
print "Starting MSXPi Server Version ",version,"Build",build

try:
    while True:
        print("st_recvcmd: waiting command")
        rc = recvdatablock()
        print"Received command",rc[1]

        if (rc[0] == RC_SUCCESS):
            try:
                cmd = str(rc[1].split()[0]).lower()
                parms = str(rc[1][len(cmd)+1:])
                # Executes the command (first word in the string)
                # And passes the whole string (including command name) to the function
                # globals()['use_variable_as_function_name']() 
                globals()[cmd](parms)
            except Exception, e:
                print("Command exception:"+str(e))

except KeyboardInterrupt:
    GPIO.cleanup() # cleanup all GPIO
    print "Terminating msxpi-server"

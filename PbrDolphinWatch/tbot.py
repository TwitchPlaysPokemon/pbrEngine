# encoding=utf8  
'''
Created on 14.05.2015

@author: Felk
'''

import re
import socket

class Twitchbot(object):
    def __init__(self, nick, password, channel, host="irc.twitch.tv", port=6667):
        self.HOST = host
        self.PORT = port
        self.CHAN = channel
        self.NICK = nick
        self.PASS = password
                
        self.con = socket.socket()
        self.con.connect((self.HOST, self.PORT))
        
        self.send_pass(self.PASS)
        self.send_nick(self.NICK)
        self.join_channel(self.CHAN)
        
        self.data = ""


    # --------------------------------------------- Start Functions ----------------------------------------------------
    def send_pong(self, msg):
        self.con.send(bytearray('PONG %s\r\n' % msg, 'UTF-8'))
    
    
    def send_message(self, chan, msg):
        self.con.send(bytearray('PRIVMSG %s :%s\r\n' % (chan, msg), 'UTF-8'))
    
    
    def send_nick(self, nick):
        self.con.send(bytearray('NICK %s\r\n' % nick, 'UTF-8'))
    
    
    def send_pass(self, password):
        self.con.send(bytearray('PASS %s\r\n' % password, 'UTF-8'))
    
    
    def join_channel(self, chan):
        self.con.send(bytearray('JOIN %s\r\n' % chan, 'UTF-8'))
    
    
    def part_channel(self, chan):
        self.con.send(bytearray('PART %s\r\n' % chan, 'UTF-8'))
    # --------------------------------------------- End Functions ------------------------------------------------------
    
    
    # --------------------------------------------- Start Helper Functions ---------------------------------------------
    def get_sender(self, msg):
        result = ""
        for char in msg:
            if char == "!":
                break
            if char != ":":
                result += char
        return result
    
    
    def get_message(self, msg):
        result = ""
        i = 3
        length = len(msg)
        while i < length:
            result += msg[i] + " "
            i += 1
        result = result.lstrip(':')
        return result
    
    
    # --------------------------------------------- End Helper Functions -----------------------------------------------
    
    def recv(self):
        while True:
            try:
                self.data = self.data+self.con.recv(1024)
                data_split = re.split(r"[~\r\n]+", self.data)
                self.data = data_split.pop()
        
                for line in data_split:
                    line = str.rstrip(line)
                    line = str.split(line)
        
        
                    if len(line) >= 1:
                        if line[0] == 'PING':
                            self.send_pong(line[1])
        
                        if line[1] == 'PRIVMSG':
                            sender = self.get_sender(line[0])
                            message = self.get_message(line)
                            match = re.match("^\s*([UDLRFBudlrfb][2']?)\s*$", message)
                            if match:
                                return (sender, match.group(1))
                            return None
    
            except socket.error:
                print "Socket died"
        
            except socket.timeout:
                print "Socket timeout"
        

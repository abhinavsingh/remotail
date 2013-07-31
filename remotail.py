#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
    remotail.py
    ~~~~~~~~~~~

    Tail multiple remote files on a terminal window

    :copyright: (c) 2013 by Abhinav Singh.
    :license: BSD, see LICENSE for more details.
"""
VERSION = (0, 1, 1)
__version__ = '.'.join(map(str, VERSION[0:3])) + ''.join(VERSION[3:])
__description__ = 'Tail multiple remote files on a terminal window'
__author__ = 'Abhinav Singh'
__author_email__ = 'mailsforabhinav@gmail.com'
__homepage__ = 'https://github.com/abhinavsingh/remotail'
__license__ = 'BSD'

import argparse
import urlparse
import getpass
import multiprocessing
import Queue
import paramiko
import select
import socket
import urwid
import logging

logging.basicConfig(level=logging.INFO, filename="/tmp/remotail.log")
logger = logging.getLogger('remotail')

class UI(object):
    
    palette = [
        ('title', 'black,bold', 'dark green',),
        ('header', 'black', 'dark green',),
        ('footer','white', 'dark blue',),
        ('key', 'white,bold', 'dark blue',),
    ]
    
    header_text = [
        ('title', 'Remotail v0.0.1',),
    ]
    
    footer_text = [
        ('key', "UP"), ", ",
        ('key', "DOWN"), ", ",
        ('key', "PAGE UP"), " and ",
        ('key', "PAGE DOWN"), " more view ",
        ('key', "Q"), " exits",
    ]
    
    boxes = dict()
    
    def __init__(self):
        self.columns = urwid.Columns([])
        self.header = urwid.AttrMap(urwid.Text(self.header_text), 'header')
        self.footer = urwid.AttrMap(urwid.Text(self.footer_text), 'footer')
        self.frame = urwid.Frame(self.columns, header=self.header, footer=self.footer)
        self.loop = urwid.MainLoop(self.frame, self.palette, unhandled_input=self.unhandled_input)
    
    def add_box(self, key):
        self.boxes[key] = urwid.ListBox(urwid.SimpleListWalker([]))
        self.columns.contents.append((self.boxes[key], self.columns.options()))
    
    def unhandled_input(self, key):
        if key.lower() == 'q':
            raise urwid.ExitMainLoop()
        elif key in ('right', 'tab'):
            self.columns.focus_position = self.columns.focus_position + 1 if self.columns.focus_position < len(self.columns.contents) - 1 else 0
        elif key == 'left':
            self.columns.focus_position = self.columns.focus_position - 1 if self.columns.focus_position > 0 else len(self.columns.contents) - 1

class Channel(object):
    
    def __init__(self, filepath):
        self.filepath = filepath
    
    def __enter__(self):
        self.client = paramiko.SSHClient()
        self.client.load_system_host_keys()
        self.client.set_missing_host_key_policy(paramiko.WarningPolicy())
        self.client.connect(self.filepath['host'], self.filepath['port'], self.filepath['username'], self.filepath['password'])
        self.transport = self.client.get_transport()
        self.channel = self.transport.open_session()
        return self.channel
    
    def __exit__(self, type, value, traceback):
        self.client.close()
        self.channel.close()

class Remotail(object):
    
    def __init__(self, filepaths):
        self.queue = multiprocessing.Queue()
        self.procs = list()
        self.ui = UI()
        
        self.filepaths = dict()
        for filepath in filepaths:
            filepath = self.filepath_to_dict(filepath)
            self.filepaths[filepath['alias']] = filepath
    
    def filepath_to_dict(self, filepath):
        url = urlparse.urlparse(filepath)
        return dict(
            username = url.username if url.username else getpass.getuser(),
            password = url.password,
            host = url.hostname,
            port = url.port if url.port else 22,
            path = url.path,
            alias = url.scheme
        )
    
    def start(self):
        for alias in self.filepaths:
            proc = multiprocessing.Process(target=Remotail.tail, args=(self.filepaths[alias], self.queue,))
            self.procs.append(proc)
            proc.start()
            self.ui.add_box(self.filepaths[alias]['alias'])
        
        self.ui.loop.watch_file(self.queue._reader, self.display)
        
        try:
            self.ui.loop.run()
        except Exception as e:
            logger.info(e)
        finally:
            for proc in self.procs:
                proc.terminate()
                proc.join()
    
    def display(self):
        line = self.queue.get_nowait()
        self.ui.boxes[line['alias']].body.append(urwid.Text(line['data'].strip()))
    
    @staticmethod
    def tail(filepath, queue):
        with Channel(filepath) as channel:
            channel.exec_command('tail -f %s' % filepath['path'])
            try:
                while True:
                    if channel.exit_status_ready():
                        logger.info('channel exit status ready')
                        break
                    
                    r, w, e = select.select([channel], [], [])
                    if channel in r:
                        try:
                            data = channel.recv(1024)
                            if len(data) == 0:
                                logger.info("EOF for %s" % filepath['alias'])
                                break
                            queue.put(dict(alias=filepath['alias'], data=data))
                        except socket.timeout as e:
                            logger.info(e)
                            pass
            except KeyboardInterrupt as e:
                pass
            except Exception as e:
                logger.info(e)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--file-path', default=list(), action='append', help='alias://user:pass@host:port/file/path/to/tail')
    args = parser.parse_args()
    
    try:
        Remotail(args.file_path).start()
    except KeyboardInterrupt as e:
        pass

if __name__ == '__main__':
    main()

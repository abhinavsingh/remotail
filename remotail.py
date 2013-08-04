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

class Cols(urwid.Columns):
    
    def __init__(self, *args, **kwargs):
        super(Cols, self).__init__(*args, **kwargs)
    
    def keypress(self, size, key):
        super(Cols, self).keypress(size, key)
        
        if key in ('right', 'tab'):
            self.focus_position = self.focus_position + 1 if self.focus_position < len(self.contents) - 1 else 0
        elif key == 'left':
            self.focus_position = self.focus_position - 1 if self.focus_position > 0 else len(self.contents) - 1
        else:
            return key

class UI(object):
    
    """Console UI for showing captured logs.
    
    -------------------frame-------------------------
    | header                                        |
    |         ---------------columns--------------  |
    |         | ----------frame----------        |  |
    |         | | header                |        |  |
    |         | |        ---listbox---  |        |  |
    |         | |        |           |  |        |  |
    | body    | | body   |           |  |  ....  |  |
    |         | |        |           |  |        |  |
    |         | |        -------------  |        |  |
    |         | | footer                |        |  |
    |         | -------------------------        |  |
    |         ------------------------------------  |
    | footer                                        |
    -------------------------------------------------
    """
    
    palette = [
        ('outer-title', 'black,bold', 'dark green',),
        ('outer-header', 'black', 'dark green',),
        ('outer-footer','white', 'dark blue',),
        ('key', 'white,bold', 'dark blue',),
        ('inner-title', 'black,bold', 'dark cyan',),
        ('inner-header', 'black', 'dark cyan',),
    ]
    
    header_text = [('outer-title', 'Remotail v%s' % __version__,),]
    
    footer_text = [
        ('key', "UP"), ", ",
        ('key', "DOWN"), ", ",
        ('key', "PAGE UP"), " and ",
        ('key', "PAGE DOWN"), " more view ",
        ('key', "Q"), " exits",
    ]
    
    boxes = dict()
    
    def __init__(self):
        self.columns = Cols([])
        self.header = urwid.AttrMap(urwid.Text(self.header_text, align='center'), 'outer-header')
        self.footer = urwid.AttrMap(urwid.Text(self.footer_text), 'outer-footer')
        self.frame = urwid.Frame(self.columns, header=self.header, footer=self.footer)
        self.loop = urwid.MainLoop(self.frame, self.palette, unhandled_input=self.unhandled_input)
    
    def add_column(self, alias):
        header = urwid.AttrMap(urwid.Text([('inner-title', alias,),]), 'inner-header')
        listbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.boxes[alias] = urwid.Frame(listbox, header=header)
        self.columns.contents.append((self.boxes[alias], self.columns.options()))
    
    def unhandled_input(self, key):
        if key.lower() == 'q':
            raise urwid.ExitMainLoop()

class Channel(object):
    
    def __init__(self, filepath):
        self.filepath = filepath
        self.connected = False
    
    def __enter__(self):
        try:
            self.client = paramiko.SSHClient()
            self.client.load_system_host_keys()
            self.client.set_missing_host_key_policy(paramiko.WarningPolicy())
            self.client.connect(self.filepath['host'], self.filepath['port'], self.filepath['username'], self.filepath['password'])
            self.transport = self.client.get_transport()
            self.channel = self.transport.open_session()
            self.connected = True
            return self.channel
        except Exception as e:
            return e
    
    def __exit__(self, type, value, traceback):
        if self.connected:
            self.client.close()
            self.channel.close()

class Tail(multiprocessing.Process):
    
    def __init__(self, filepath, queue):
        super(Tail, self).__init__()
        self.filepath = filepath
        self.queue = queue
    
    def run(self):
        with Channel(self.filepath) as channel:
            if isinstance(channel, Exception):
                self.put(str(channel))
            else:
                channel.exec_command('tail -f %s' % self.filepath['path'])
                try:
                    while True:
                        if channel.exit_status_ready():
                            self.put('channel exit status ready')
                            break
                        
                        r, w, e = select.select([channel], [], [])
                        if channel in r:
                            try:
                                data = channel.recv(1024)
                                if len(data) == 0:
                                    self.put("EOF")
                                    break
                                self.put(data)
                            except socket.timeout as e:
                                self.put(str(e))
                except KeyboardInterrupt as e:
                    pass
                except Exception as e:
                    self.put(str(e))
    
    def put(self, data):
        self.queue.put(dict(
            alias = self.filepath['alias'],
            data = data
        ))

class Remotail(object):
    
    def __init__(self, filepaths):
        self.queue = multiprocessing.Queue()
        self.procs = list()
        self.ui = UI()
        self.filepaths = dict()
        
        for filepath in filepaths:
            filepath = self.filepath_to_dict(filepath)
            self.filepaths[filepath['alias']] = filepath
    
    @staticmethod
    def filepath_to_dict(filepath):
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
            proc = Tail(self.filepaths[alias], self.queue)
            self.procs.append(proc)
            proc.start()
            self.ui.add_column(self.filepaths[alias]['alias'])
        
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
        text = urwid.Text(line['data'].strip())
        box = self.ui.boxes[line['alias']].body
        box.body.append(text)
        box.set_focus(len(box.body)-1)

def main():
    parser = argparse.ArgumentParser(
        description='Remotail v%s' % __version__,
        epilog='Having difficulty using Remotail? Report at: %s/issues/new' % __homepage__
    )
    parser.add_argument('--file-path', default=list(), action='append', help='alias://user:pass@host:port/file/path/to/tail')
    parser.add_argument('--config', help='Config file containing one --file-path per line')
    args = parser.parse_args()
    
    filepaths = args.file_path
    
    if args.config:
        try:
            filepaths += open(args.config, 'rb').read().strip().split()
        except IOError as e:
            logger.error(e)
    
    try:
        Remotail(filepaths).start()
    except KeyboardInterrupt as e:
        pass

if __name__ == '__main__':
    main()

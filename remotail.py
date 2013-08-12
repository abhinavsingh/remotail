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

remotail = None

class Container(urwid.Columns):
    
    def keypress(self, size, key):
        key = super(Container, self).keypress(size, key)
        
        if key in ('right', 'tab'):
            self.focus_position = self.focus_position + 1 if self.focus_position < len(self.contents) - 1 else 0
        elif key == 'left':
            self.focus_position = self.focus_position - 1 if self.focus_position > 0 else len(self.contents) - 1
        else:
            return key

class CommandLine(urwid.Edit):
    
    _allowed_cmds = ['enable', 'disable']
    
    def keypress(self, size, key):
        key = super(CommandLine, self).keypress(size, key)
        
        if key == 'enter':
            self._execute(self.get_edit_text())
            self.set_edit_text('')
        else:
            return key
    
    def _execute(self, input):
        args = input.split()
        if args[0] in self._allowed_cmds:
            if args[0] == 'enable':
                remotail.enable(args[1])
            elif args[0] == 'disable':
                remotail.disable(args[1])
        else:
            logger.error('%s command not found' % args[0])

PALETTES = {
    'default': [
        ('outer-title', 'white,bold', 'dark blue',),
        ('outer-header', 'white', 'dark blue',),
        ('outer-footer','black,bold', 'dark cyan',),
        ('outer-footer-text', 'black,bold', 'dark cyan',),
        ('inner-title', 'black,bold', 'dark green',),
        ('inner-header', 'black', 'dark green',),
    ],
}

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
    
    palette = PALETTES['default']
    header_text = [('outer-title', 'Remotail v%s' % __version__,),]
    footer_text = [('outer-footer-text', '> '),]
    boxes = dict()
    
    def __init__(self):
        self.columns = Container([])
        self.header = urwid.AttrMap(urwid.Text(self.header_text, align='center'), 'outer-header')
        self.footer = urwid.AttrMap(CommandLine(self.footer_text), 'outer-footer')
        
        self.frame = urwid.Frame(self.columns, header=self.header, footer=self.footer)
        self.frame.set_focus('footer')
        
        self.loop = urwid.MainLoop(self.frame, self.palette)
    
    def add_column(self, alias):
        header = urwid.AttrMap(urwid.Text([('inner-title', alias,),]), 'inner-header')
        listbox = urwid.ListBox(urwid.SimpleListWalker([]))
        self.boxes[alias] = (urwid.Frame(listbox, header=header), self.columns.options())
        self.columns.contents.append(self.boxes[alias])
    
    def del_column(self, alias):
        self.columns.contents.remove(self.boxes[alias])
        del self.boxes[alias]

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

TAIL_MSG_TYPE_DATA = 1
TAIL_MSG_TYPE_NOTIFY = 2

class Tail(multiprocessing.Process):
    
    def __init__(self, filepath, queue):
        super(Tail, self).__init__()
        self.filepath = Remotail.filepath_to_dict(filepath)
        self.queue = queue
    
    def run(self):
        with Channel(self.filepath) as channel:
            if isinstance(channel, Exception):
                self.put(str(channel), TAIL_MSG_TYPE_NOTIFY)
            else:
                self.put('connected', TAIL_MSG_TYPE_NOTIFY)
                channel.exec_command('tail -f %s' % self.filepath['path'])
                try:
                    while True:
                        if channel.exit_status_ready():
                            self.put('channel exit status ready', TAIL_MSG_TYPE_NOTIFY)
                            break
                        
                        r, w, e = select.select([channel], [], [])
                        if channel in r:
                            try:
                                data = channel.recv(1024)
                                if len(data) == 0:
                                    self.put('EOF', TAIL_MSG_TYPE_NOTIFY)
                                    break
                                self.put(data)
                            except socket.timeout as e:
                                self.put(str(e), TAIL_MSG_TYPE_NOTIFY)
                except KeyboardInterrupt as e:
                    pass
                except Exception as e:
                    self.put(str(e), TAIL_MSG_TYPE_NOTIFY)
    
    def put(self, msg, type=None):
        type = type if type else TAIL_MSG_TYPE_DATA
        self.queue.put(dict(
            alias = self.filepath['alias'],
            data = msg,
            type = type
        ))

class Remotail(object):
    
    def __init__(self, filepaths):
        self.queue = multiprocessing.Queue()
        self.procs = dict()
        self.ui = UI()
        self.filepaths = filepaths
        
        # TODO: ugly hack to get going right now
        # replace with something better
        global remotail
        remotail = self
    
    @staticmethod
    def filepath_to_dict(filepath):
        url = urlparse.urlparse(filepath)
        filepath = dict(
            username = url.username if url.username else getpass.getuser(),
            password = url.password,
            host = url.hostname,
            port = url.port if url.port else 22,
            path = url.path,
            alias = url.scheme
        )
        assert filepath['alias'] is not ''
        return filepath
    
    def enable(self, filepath):
        proc = Tail(filepath, self.queue)
        self.procs[proc.filepath['alias']] = proc
        self.ui.add_column(proc.filepath['alias'])
        proc.start()
    
    def disable(self, alias):
        proc = self.procs[alias]
        del self.procs[alias]
        proc.terminate()
        self.ui.del_column(proc.filepath['alias'])
    
    def start(self):
        for filepath in self.filepaths:
            self.enable(filepath)
        
        self.ui.loop.watch_file(self.queue._reader, self.display)
        
        try:
            self.ui.loop.run()
        except Exception as e:
            logger.info(e)
        finally:
            for alias in self.procs:
                proc = self.procs[alias]
                proc.terminate()
                proc.join()
    
    def display(self):
        line = self.queue.get_nowait()
        text = urwid.Text(line['data'].strip())
        box = self.ui.boxes[line['alias']][0].body
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

#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
Module to centralize the definition of settings and UI resources.
'''

import os

from PyQt4.QtGui import QIcon

# Time between event processing (in seconds)
EVENT_RESPONSE_TIME = 0.1

# Icons
ICONS_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'icons')
RES_ICON_START = QIcon(os.path.join(ICONS_PATH, 'btn_start.png'))
RES_ICON_CONT = QIcon(os.path.join(ICONS_PATH, 'btn_cont.gif'))
RES_ICON_STOP = QIcon(os.path.join(ICONS_PATH, 'btn_stop.gif'))
RES_ICON_INTO = QIcon(os.path.join(ICONS_PATH, 'btn_into.gif'))
RES_ICON_OVER = QIcon(os.path.join(ICONS_PATH, 'btn_over.gif'))
RES_ICON_OUT = QIcon(os.path.join(ICONS_PATH, 'btn_out.gif'))
RES_ICON_ADD = QIcon(os.path.join(ICONS_PATH, 'btn_add_watch.gif'))
RES_ICON_WATCHES = QIcon(os.path.join(ICONS_PATH, 'btn_watches.png'))

RES_STR_DEBUG_FILE_START = 'Debug File'
RES_STR_DEBUG_STOP = 'Finish debug session'
RES_STR_DEBUG_CONTINUE = 'Continue'
RES_STR_DEBUG_STEPINTO = 'Step Into'
RES_STR_DEBUG_STEPOVER = 'Step Over'
RES_STR_DEBUG_STEPOUT = 'Step Out'

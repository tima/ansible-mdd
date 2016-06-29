# Provides per-task timing, ongoing playbook elapsed time

# Make coding more python3-ish
from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import sys
import pwd
import socket
import time

from influxdb import InfluxDBClient

from ansible.plugins.callback import CallbackBase

t0 = time.time()


class CallbackModule(CallbackBase):
    """
    This callback module provides per-task timing, ongoing playbook elapsed time
    """
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'influxdb_timers'
    #CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        self.stats = dict()
        self.current = None
        _host = os.getenv('ANSIBLE_INFLUXDB_HOST', 'localhost')
        _port = os.getenv('ANSIBLE_INFLUXDB_PORT', 8086)
        _user = os.getenv('ANSIBLE_INFLUXDB_USER', None)
        _pass = os.getenv('ANSIBLE_INFLUXDB_PASS', None)
        _dbname = os.getenv('ANSIBLE_INFLXUDB_DBNAME', 'ansible')

        self.influxdb = InfluxDBClient(_host, _port, _user, _pass, _dbname)
        try:
            self.influxdb.create_database(_dbname)
        except:
            pass
        self.influxdb.switch_database(_dbname)
        self.influxdb.switch_user(_user, _pass)

        self.username = pwd.getpwuid(os.getuid()).pw_name
        self.hostname = socket.gethostname()
        # socket.gethostbyname(socket.gethostname())
        # socket.getfqdn()
        super(CallbackModule, self).__init__()

    def _record_task(self, task):
        """
        Logs the start of each task
        """
        self._timestamp()
        self.current = task._uuid
        self.stats[self.current] = {
            'time': time.time(),
            'name': task.get_name(),
            'path': task.get_path()
        }

    def _timestamp(self):
        if self.current is not None:
            duration = time.time() - self.stats[self.current]['time']
            del self.stats[self.current]['time']
            fields = { 'duration': duration }
            tags = self.stats[self.current]
            self._report_timing('task-timing', fields, tags)

    def _report_timing(self, timing_type, fields, tags=dict()):
        tags['type'] = timing_type
        tags['user']= self.username
        tags['hostname'] = tags.get('hostname', self.hostname)
        tags['playbook_file'] = self.playbook_file
        tags['playbook_basedir'] = self.playbook_basedir
        timing_body = [
            {
                'measurement': 'timing',
                'tags': tags,
                'fields': fields
            }
        ]
        self.influxdb.write_points(timing_body)

    def v2_playbook_on_start(self, playbook):
        self.playbook_file = os.path.basename(playbook._file_name)
        self.playbook_basedir = playbook._basedir

    def v2_playbook_on_task_start(self, task, is_conditional):
        self._record_task(task)

    def v2_playbook_on_handler_task_start(self, task):
        self._record_task(task)

    #def playbook_on_setup(self):
    #    self._display.display(tasktime())

    def playbook_on_stats(self, stats):
        self._timestamp()
        time_total_elapsed = time.time() - t0
        fields = { 'duration': time_total_elapsed }
        self._report_timing('playbook-timing', fields)

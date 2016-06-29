# (c) 2016, Timothy Appnel <tim@appnel.com>

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import sys
import pwd
import socket

from influxdb import InfluxDBClient

from ansible.plugins.callback import CallbackBase

class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'notification'
    CALLBACK_NAME = 'influxdb_events'

    def __init__(self, display=None):
        self.results = []
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
        super(CallbackModule, self).__init__(display)

    def report_event(self, event_type, fields, tags=dict()):
        tags['type'] = event_type
        tags['user']= self.username
        tags['hostname'] = tags.get('hostname', self.hostname)
        tags['playbook_file'] = self.playbook_file
        tags['playbook_basedir'] = self.playbook_basedir
        annotation_body = [
            {
                'measurement': 'events',
                'tags': tags,
                'fields': fields
            }
        ]
        self.influxdb.write_points(annotation_body)

    def v2_playbook_on_start(self, playbook):
        self.playbook_file = os.path.basename(playbook._file_name)
        self.playbook_basedir = playbook._basedir
        fields = { 'text': 'Playbook %s started on %s by %s' %
            (self.playbook_file, self.hostname, self.username)
        }
        self.report_event('playbook-start', fields)

    def v2_playbook_on_play_start(self, play):
        fields = {
            'text': '"%s" from playbook %s started on %s by %s' %
                (play.name, self.playbook_file, self.hostname, self.username),
            'id': str(play._uuid)
        }
        self.report_event('play-start', fields)

    def v2_runner_on_ok(self, result, **kwargs):
        if not result._result.get('changed', False):
            return
        r = result._result
        module_name = r['invocation']['module_name']
        if module_name != 'service': # more
            return
        delegated_vars = r.get('_ansible_delegated_vars', None)
        if delegated_vars:
            delegated_from = result._host.get_name()
            hostname = delegated_vars['ansible_host']
        else:
            delegated_from = None
            hostname = result._host.get_name()
        name = r['name'] # doesn't handle list
        state = r['invocation']['module_args']['state']
        tags = {
            'service_name': name,
            'service_state': state,
            'hostname': hostname
        }
        if delegated_from:
            tags['delegated_from'] = delegated_from
        fields = {
            'text': 'The %s service was %s on %s' % (name, state, hostname)
        }
        self.report_event(module_name, fields, tags=tags)

    # +END PLAY

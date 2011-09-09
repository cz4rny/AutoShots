#!/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2011 Cezary Krzyżanowski. All rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
# 
#    1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 
#    2. Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
# 
# THIS SOFTWARE IS PROVIDED BY CEZARY KRZYŻANOWSKI ''AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> OR
# CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
# PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING
# NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# 
# The views and conclusions contained in the software and documentation
# are those of the authors and should not be interpreted as representing
# official policies, either expressed

import datetime
import itertools
import multiprocessing
import os
import re
import sys
import tempfile
dirname = os.path.dirname(__file__)
onedirup = os.path.normpath(os.path.join(dirname, os.pardir))
sys.path.insert(0, onedirup)

import autoshots

class TestAutoshots:
    """ Main autoshots test fixture. """

    #: Generic test url used all arround the test suite.
    test_url = 'Test URL'

    #: The title of the running header.
    running_header = 'Running jobs:'
    #: The title of the history header.
    history_header = 'History jobs:'


    def setup_method(self, method):
        """ Make a temporoary file as a test database. Also setup
            flask for the testing.
        """
        self.db_fd, temppath = tempfile.mkstemp()
        autoshots.app.config['SQLALCHEMY_DATABASE_URI'] = \
            'sqlite:///' + temppath
        autoshots.app.config['TESTING'] = True
        self.app = autoshots.app.test_client()
        autoshots.db.create_all()

    def teardown_method(self, method):
        """ Close the db file. """
        os.close(self.db_fd)
        sqliteurl = autoshots.app.config['SQLALCHEMY_DATABASE_URI']
        os.unlink(sqliteurl.replace('sqlite:///', ''))

    def _get_now_hour(self):
        return datetime.datetime.utcnow().strftime('%H:%M')

    def test_doctype(self):
        """ Check whether we're displaying the doctype tag. """
        rv = self.app.get('/')
        assert ('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN"\n'
            +'   "http://www.w3.org/TR/html4/strict.dtd">') in rv.data

    def test_home(self):
        """ Check the basic home page layout, i.e. text input and
            a button.
        """
        rv = self.app.get('/')
        assert '<input type="text" name="url">' in rv.data
        assert '<input type="submit" value="Send">' in rv.data

    def test_empty_home(self):
        """ Check whether headers dissapear when no data
            available on the home page.

            That means both running and history task headers.
        """

        # No data, no headers.
        rv = self.app.get('/')
        assert self.running_header not in rv.data
        assert self.history_header not in rv.data

        # One entry, not running.
        history_job = autoshots.Job('History job')
        autoshots.db.session.add(history_job)
        autoshots.db.session.commit()
        rv = self.app.get('/')
        assert self.running_header not in rv.data
        assert self.history_header in rv.data

        # Both entry types; history and running
        running_job = autoshots.Job('Running job')
        running_job.running = True
        autoshots.db.session.add(running_job)
        autoshots.db.session.commit()
        rv = self.app.get('/')
        assert self.running_header in rv.data
        assert self.history_header in rv.data

        # Only the running job.
        autoshots.db.session.delete(history_job)
        autoshots.db.session.commit()
        rv = self.app.get('/')
        assert self.running_header in rv.data
        assert self.history_header not in rv.data

    def test_adding(self):
        """ Checks whether adding a job works.

            This means that a new entry shows on the
            homepage, especially under the running header.

            Also looks for the timestamp on the page.
        """
        # First check that nothing is there.
        rv = self.app.get('/')
        assert self.test_url not in rv.data

        now = self._get_now_hour()
        # Now add a url via POST.
        rv = self.app.post('/add', data=dict(
            url=self.test_url,
            ), follow_redirects=True)
        assert rv.data.count(self.test_url) == 3
        assert re.search(self.running_header + '(.+?)'
            + '(?!' + self.history_header + ')'
            + self.test_url, rv.data, re.DOTALL)
        assert now in rv.data

    def test_done(self):
        """ Checks the done URL with POST.

            Uses test_adding for initial addition.
        """
        # First add.
        self.test_adding()

        # Then mark done.
        rv = self.app.post('/done', data=dict(
            url=self.test_url,
            ), follow_redirects=True)
        assert re.search(self.history_header + '(.+?)'
            + '(?!' + self.running_header + ')'
            + self.test_url, rv.data, re.DOTALL)

    def test_process_starting(self):
        """ Check that the browsershots job process starts
            after adding it via the website.
        """
        # Add some job first.
        rv = self.app.post('/add', data=dict(
            url=self.test_url,
            ), follow_redirects=True)

        children = multiprocessing.active_children()
        jobs = filter(lambda p: autoshots.PROCESS_NAME
            in p.name, children)
        assert jobs

        # Termiante all the jobs just in case
        for job in jobs:
            job.terminate()

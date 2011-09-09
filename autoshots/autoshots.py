#!/usr/bin/env python
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
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL CEZARY KRZYŻANOWSKI OR
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

"""
.. module: autoshots
    :platform: Unix, Windows
    :synopsis: Extends browsershots sessions for you.

.. moduleauthor: Cezary Krzyżanowski <cezary.krzyzanowski@gmail.com>
"""

from flask import (Flask, url_for, request,
    render_template, redirect, flash)
from flaskext.sqlalchemy import SQLAlchemy

from datetime import datetime
import multiprocessing
import os.path

import job

class Config(object):
    """ Default configuration.

        Put all values here, and override in other classes.
    """
    #: Run framework in debug mode?
    DEBUG = False
    #: Are we testing?
    TESTING = False
    #: URI for the database.
    DATABASE_URI = ('sqlite:///' + os.path.join(os.path.dirname(
        os.path.abspath( __file__)), 'autoshots.db'))
    #: URL root
    URL_ROOT = None

class ProductionConfig(Config):
    """ How we're working on production. """
    #: This elaborate setting makes the sqlite database file
    #: reside in the same dir as this file. Needs to be an absolute path.
    URL_ROOT = '/autoshots'

class DevelopmentConfig(Config):
    """ Developement settings. """
    DEBUG = True

class TestingConfig(Config):
    """ Test environemtn settings. """
    TESTING = True

#: This maps the correct config class in regard to the environmental mode.
mode_mapping = {
    'DEV': DevelopmentConfig,
    'PROD': ProductionConfig,
    'TEST': TestingConfig,
}

#: The config class with values depending on the
#: environmental variable AUTOSHOTS_MODE
config = mode_mapping[os.getenv('AUTOSHOTS_MODE', 'DEV')]()

app = Flask(__name__)
app.debug = config.DEBUG
app.testing = config.TESTING
app.config['APPLICATION_ROOT'] = config.URL_ROOT
app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URI
app.secret_key = \
    '\x8b\x90\xd39\xfa\t\xa9m9#\xd0!\xac<\x81\xe3\xee\xc7e\x8b 7\xf3\xa1'

#: Database object, an SQLAlchemy instance.
db = SQLAlchemy(app)

#: BS has a simple API, i.e.
#: http://browsershots.org/http://your.site/address?here=value
#: This is the basic url.
BROWSERSHOTS_URL = 'http://browsershots.org/'

#: The name of the prcess being created
PROCESS_NAME = 'BrowsershotsJob: '

class Job(db.Model):
    """ A model of the job send to browsershots.

        This is kept in the SQL database.
    """
    #: Primary key (integer), just the id.
    id = db.Column(db.Integer, primary_key=True)
    #: Full qualified url (string) being checked by BS.
    url = db.Column(db.String(200), unique=True)
    #: Timestamp (datetime) of the system addition.
    timestamp = db.Column(db.DateTime)
    #: Is the job still running (boolean)?
    running = db.Column(db.Boolean)

    def __init__(self, url):
        """ Create a job.

        Only the url and timestamp are needed.

        Attrs:
            url (string): The URL of the webpage being tested by
                 browsershots.
        """
        self.url = url
        self.timestamp = datetime.utcnow()
        self.running = False

    def __repr__(self):
        return '<Job %r>' % self.url

@app.route('/')
def home():
    """ Main landing page.

        Displays a big input box to add a job and lists previous jobs,
        both running and finished.
    """
    running_jobs = (Job.query.filter_by(running=True)
        .order_by(Job.timestamp.desc())).all()
    history_jobs = (Job.query.filter_by(running=False)
        .order_by(Job.timestamp.desc())).all()
    return render_template('home.html', now=datetime.utcnow(),
        base_url=BROWSERSHOTS_URL,
        running_jobs=running_jobs, history_jobs=history_jobs)

@app.route('/add', methods=['POST'])
def add():
    """ The POST handler for adding a new job. """
    if not request.method == 'POST':
        abort(401)

    url = request.form['url']
    new_job = Job.query.filter_by(url=url).first()
    if new_job:
        # Update existing entry.
        new_job.running = True
        db.session.commit()

        flash('Url %s re-run.' % url)
    else:
        # A totally new job.
        new_job = Job(url)
        new_job.running = True
        db.session.add(new_job)
        db.session.commit()

        flash('Url %s added.' % url)

    # Start a new daemon process which will extend the
    # browsershots session from time to time.
    p = multiprocessing.Process(target=job.bs_job_with_callback,
            name=PROCESS_NAME + url, kwargs={
                'url': BROWSERSHOTS_URL + url,
                'callback_url': url_for('done')})
    p.daemon = True
    p.start()

    return redirect(url_for('home'))

@app.route('/done', methods=['POST'])
def done():
    """ The POST handler for job done signal. """
    if not request.method == 'POST':
        abort(401)

    url = request.form['url']
    job = Job.query.filter_by(url=url).first()
    if not job:
        abort(401)
    job.running = False
    db.session.commit()
    return redirect(url_for('home'))


#@app.route('/<path:url>')
#def url_details(url):
#    """ Displays a jobs individual information.
#
#        Attrs:
#            url (string): The webpage URL for which to display info.
#    """
#    return redirect(url)

if __name__ == '__main__':
    app.run()

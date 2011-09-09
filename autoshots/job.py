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
.. module: job
    :platform: Unix, Windows
    :synopsis: The job for extending browsershot sessions.

.. moduleauthor: Cezary Krzyżanowski <cezary.krzyzanowski@gmail.com>
"""

import cookielib
import copy
import re
import time
import urllib
import urllib2

#: The main URL of browsershots.
BROWSERSHOTS_URL = 'http://browsershots.org/'
#: URL for login (POST).
SIGNIN_URL = BROWSERSHOTS_URL + 'accounts/signin'
#: The URL used to extend a session.
EXTEND_URL = BROWSERSHOTS_URL + 'ajax/requests/extend'

#: Regular expression used to extract the extension id.
extend_regex = re.compile(
    r'<a(?:.+?)id="(?P<id>.+?)"(?:.+?)rel="extend"',
    re.IGNORECASE | re.MULTILINE)
#: Regular expresion used to extract the csrf token.
csrf_regex = re.compile(
    r'<input(?:.+?)name=\'csrfmiddlewaretoken\''
    + '(?:.+?)value=\'(?P<csrf>.+?)\'',
    re.IGNORECASE)
#: Loggged in regexp.
logged_regex = re.compile(
    r'a(?:.+?)href="/accounts/logout"')

#: A data mapping used for authentication.
#: This includes username and password.
auth_data = [
#    ('username', 'dhubleizh'),
    ('username', 'cz4rny'),
    ('password', 'pieprzonyptasiu'),
    ('remember', 'on'),
    ('fromurl', '/'),
]

#: Basic headers used in the communication.
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows; U; Windows NT 5.0; '
        + 'en-GB; rv:1.8.1.12) Gecko/20080201 Firefox/2.0.0.12',
    'Accept:': 'text/thml,application/hxtml+xml,'
        + 'application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-gb,en;q=0.5',
    'Accept-Charset': 'utf-8,ISO-8859-1;q=0.7,*;q=0.7',
    'Connection': 'Keep-alive'
}

#: Additional headers used for localhost browshershots to
#: browsershots requests.
localhost_headers = {
    'Host': 'browsershots.org',
    'Origin': 'http://browsershots.org',
    'Referer': 'http://browsershots.org/',
}

#: Json specific requests. Used for the extension.
json_headers = {
    'Accept': 'application/json,text/javascript',
    'X-Requested-With': 'XMLHttpRequest',
}

#: The frequency of running the extension job. 20min.
HAMMER_FREQUENCY = 540

class WrongResponseError(RuntimeError):
    """ Raised when a HTTP request to browsershots returns
        wrong response.

    """

class UnexpectedContentError(RuntimeError):
    """ Raised when the returned html page does not have the
        content that was expected.
    """

def bs_job_with_callback(url, callback_url):
    """ Runs the browsershot job and posts the result afterwards. """
    # The actual job.
    finish_browshershot_job(url)

    # Preapre the data.
    data = urllib.urlencode({
        'url': url,
    })
    # After the job send the 'done' message via POST.
    req = urllib2.Request(callback_url, data)
    response = urllib2.urlopen(req)
    result = response.read()
    response.close()

def finish_browshershot_job(url):
    """ Main browsershot job. """
    # Set up the urllib to accept cookies and
    # redirects.
    cookiejar = cookielib.CookieJar()
    url_opener = urllib2.build_opener(
        urllib2.HTTPCookieProcessor(cookiejar),
        urllib2.HTTPRedirectHandler)
    urllib2.install_opener(url_opener)

    # Loop while we get a csrf token
    request_id = extend_procedure(url)
    while request_id:
        time.sleep(HAMMER_FREQUENCY)
        try:
            request_id = extend_procedure(url)
        except UnexpectedContentError:
            # No request id--- it seems we've finished
            pass

def extend_procedure(url):
    """ Execute the full browsershots extend procedure.

        Attrs:
            url (string): The browsershots URL to extend.
    """
    # Extract the CSRF token from the site to login.
    csrf = get_CSRF()
    # Login to get the session id in the cookie.
    login(csrf)
    # Get the request id for the extension.
    request_id = get_request_id(url)
    # Finally, extend the session with the right id and being
    # logged in.
    extend_session(request_id)

    return request_id

def get_CSRF():
    """ Get the CSRF token.

        Connect to the browsershots website to get the CSRF
        token in order to send it with the login.

        That's basically overriding cross-site scripting security
        of browsershots.

        Returns:
            CSRF token as a string or None.
    """
    # Get the HTML from the website.
    req = urllib2.Request(BROWSERSHOTS_URL, None, headers)
    response = urllib2.urlopen(req)
    html = response.read()
    if response.getcode() != 200:
        response.close()
        raise WrongResponseError('Error retreiving CSRF token from'
            + 'browsershots. Got response: ' + str(response.getcode())
            + ':\n' + html)

    # Find and extract the CSRF token from the HTML.
    match = re.search(csrf_regex, html)
    if match:
        return match.groupdict()['csrf']
    else:
        raise UnexpectedContentError('Could not find the csrf token'
            + ' on the retreived page. Used regexp:\n'
            + str(csrf_regex.pattern) + '\nPage:\n' + html)

def login(csrf):
    """ Login to browsershots.

        Uses the csrf token and credentials to login to browsershots.
        The cookie will hold the session.

        Args:
            csrf (string): The CSRF token.
    """
    # Insert the token to the data dict.
    auth_data.insert(0, ('csrfmiddlewaretoken', csrf))
    data = urllib.urlencode(auth_data)

    # Update headers with json request.
    new_headers = copy.deepcopy(headers)
    new_headers.update(localhost_headers)

    # Make the login request.
    req = urllib2.Request(SIGNIN_URL, data, new_headers)
    response = urllib2.urlopen(req)
    html = response.read()

    # Search for logout link, won't be there unless successfully
    # logged in.
    match = re.search(logged_regex, html)
    if not match:
        response.close()
        raise UnexpectedContentError('There is no logout link on the'
            + ' browsershots webpage. Regexp used: '
            + logged_regex.pattern + '\nPage:\n'
            + html)

def get_request_id(url):
    """ Gets the request ID for the extension.

        This function needs the urllib2 be already logged
        into browsershots. The CookieJar needs to have the
        session inside of it.

        Args:
            url (string) URL to extend the browsershots session for.
        Returns:
            The id string or None
    """
    # Get the HTML content.
    req = urllib2.Request(url, None, headers)
    response = urllib2.urlopen(req)
    html = response.read()
    if response.getcode() != 200:
        raise WrongResponseError('Wrong response code on fetching'
            + ' browsershots page.\nCode: ' + str(response.getcode())
            + '\nPage:\n' + html)

    # Extract the id for later usage.
    match = re.search(extend_regex, html)
    if match:
        return  match.groupdict()['id']
    else:
        raise UnexpectedContentError('Unable to fetch the browsershots id'
            + ' from the page. Regexp used:\n' + str(extend_regex.pattern)
            + '\nPage:\n' + html)

def extend_session(request_id):
    """ Extends the session for a given id.

        Needs the CookieJar to be logged in, i.e. the cookie
        contains the session.

        Args:
            request_id (string): The id of the session to extend.
    """
    # Prepare the form data for the request.
    data = urllib.urlencode({
            'request_group_id' : request_id
        }
    )

    # Make the connection to extend the session.
    new_headers = copy.deepcopy(headers)
    new_headers.update(localhost_headers)
    new_headers.update(json_headers)
    req = urllib2.Request(EXTEND_URL, data, new_headers)
    response = urllib2.urlopen(req)
    html = response.read()
    response.close()
    if not '"success": true' in html:
        raise UnexpectedContentError('No success string in the'
            + ' extend response. Response code: ' + response.getcode()
            + '\nJSON:\n' + html)

if __name__ == '__main__':
    finish_browshershot_job('http://browsershots.org/'
        + 'http://pogorzelisko.blogspot.com/')

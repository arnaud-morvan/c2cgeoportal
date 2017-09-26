# -*- coding: utf-8 -*-

# Copyright (c) 2012-2017, Camptocamp SA
# All rights reserved.

# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:

# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.

# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
# ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

# The views and conclusions contained in the software and documentation are those
# of the authors and should not be interpreted as representing official policies,
# either expressed or implied, of the FreeBSD Project.

import os
import logging
from logging.config import fileConfig
from pyramid.paster import get_app


def create_application(configfile=None):  # pragma: no cover
    """
    Create a standard WSGI application with the capabilities to use environment variables in the
    configuration file (use %(ENV_VAR)s place holders)

    :param config: The configuration file to use
    :return: The application
    """
    logging.captureWarnings(True)
    if configfile is None:
        configfile = os.environ.get("WSGI_CONFIG", "/app/production.ini")
    # Load the logging config without using pyramid to be able to use environment variables in there.
    fileConfig(configfile, defaults=os.environ)
    try:
        return get_app(configfile, "main", options=os.environ)
    except:
        logging.getLogger(__name__).exception("Failed starting the application")
        raise
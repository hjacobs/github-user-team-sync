=========================
GitHub User and Team Sync
=========================

Goal: Sync employees and their team membership to GitHub.com

To run this script, you will need:

* Google Spreadsheet with the email and GitHub username of each user
* Google Apps Script ``get-github-usernames.js`` to read the spreadsheet via API
* OAuth token for the team service (Team service contains mapping from uid to team_id)
* GitHub personal access token, you need at least to grant the following scopes in GitHub: "admin:org", "repo", "user"


Prerequisites
=============

First make sure you have Python 3.4+ installed.

Next install the PyPI dependencies:

.. code-block:: bash

    $ sudo pip3 install -r requirements.txt

Usage
=====

.. code-block:: bash

    $ sudo pip3 install scm-source
    $ scm-source  # generate scm-source.json
    $ docker build -t github-user-team-sync .
    $ docker run -it -e GITHUB_ACCESS_TOKEN=... -e .. github-user-team-sync

The following environment variables need to be set:

``CREDENTIALS_DIR``
    Directory with OAuth credentials (``client.json`` and ``user.json``).
``GITHUB_ACCESS_TOKEN``
    The personal GitHub access token with "admin:org", "repo" and "user" scopes.
``OAUTH2_ACCESS_TOKEN_URL``
    OAuth provider URL to create access tokens.
``SCRIPT_ID``
    Google Apps script ID of ``get-github-usernames.js``
``SCRIPT_CREDENTIALS``
    JSON OAuth credentials of Google API client
``TEAM_SERVICE_URL``
    URL of Team Service providing team membership information, e.g. https://teams.example.org
``UPDATE_INTERVAL_SECONDS``
    Seconds between syncs (default: 300).
``USER_SERVICE_URL``
    URL of User Service to lookup employees by mail, e.g. https://users.example.org

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

    $ export GITHUB_ACCESS_TOKEN=123456789
    $ export SCRIPT_ID=123
    $ export SCRIPT_CREDENTIALS='{...}'
    $ ./sync-github-teams.py https://teams.example.org https://users.example.org


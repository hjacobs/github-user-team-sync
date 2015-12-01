=========================
GitHub User and Team Sync
=========================

Goal: Sync employees and their team membership to GitHub.com

To run this script, you will need:

* CSV file with three columns: email, GitHub username and uid
* OAuth token for the team service (Team service contains mapping from uid to team_id)
* GitHub personal access token, you need at least to grant the following scopes in GitHub: "admin:org", "repo", "user"

The CSV file can be generated with ldap.sh by using LDAP credentials (LDAP contains mapping from email to uid):

.. code-block:: bash

    $ cat usernames.csv | tail -n +2 | ./ldap.sh  > usernames-with-uid.csv

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
    $ ./sync-github-teams.py usernames-with-uid.csv https://teams.example.org https://users.example.org


=========================
GitHub User and Team Sync
=========================

Goal: Sync employees and their team membership to GitHub.com

To run this script, you will need:

* CSV file with two columns: email and GitHub username
* LDAP credentials (LDAP contains mapping from email to uid)
* OAuth token for the team service (Team service contains mapping from uid to team_id)
* GitHub personal access token

Usage
=====

.. code-block:: bash

    $ export GITHUB_ACCESS_TOKEN=123456789
    $ ./sync-github-teams.py mycsvfile.csv https://teams.example.org


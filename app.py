#!/usr/bin/env python3

import collections
import connexion
import httplib2
import itertools
import json
import logging
import os
import requests
import time
import zign.api

from apiclient import discovery
from apiclient import errors
import oauth2client
from oauth2client import client
from oauth2client import tools

from unittest.mock import MagicMock

from clickclick import Action, info

ALL_ORGANIZATION_MEMBERS_TEAM = 'All Organization Members'

github_base_url = "https://api.github.com/"

sess = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
sess.mount('https://', adapter)
requests = sess

SCOPES = 'https://www.googleapis.com/auth/spreadsheets'
CLIENT_SECRET_FILE = 'client_secret.json'
APPLICATION_NAME = 'github-user-team-sync'


def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    json_data = os.getenv('SCRIPT_CREDENTIALS')
    if json_data:
        credentials = client.Credentials.new_from_json(json_data)
        return credentials

    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir,
                                   'script-get-github-usernames.json')

    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
        flow.user_agent = APPLICATION_NAME
        credentials = tools.run(flow, store)
        info('Storing credentials to ' + credential_path)
    return credentials


def get_github_usernames():
    SCRIPT_ID = os.getenv('SCRIPT_ID')

    # Authorize and create a service object.
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('script', 'v1', http=http)

    # Create an execution request object.
    request = {"function": "getGitHubUsernames"}

    try:
        # Make the API request.
        response = service.scripts().run(body=request,
                                         scriptId=SCRIPT_ID).execute()

        if 'error' in response:
            # The API executed, but the script returned an error.

            # Extract the first (and only) set of error details. The values of
            # this object are the script's 'errorMessage' and 'errorType', and
            # an list of stack trace elements.
            error = response['error']['details'][0]
            error("Script error message: {0}".format(error['errorMessage']))

            if 'scriptStackTraceElements' in error:
                # There may not be a stacktrace if the script didn't start
                # executing.
                error("Script error stacktrace:")
                for trace in error['scriptStackTraceElements']:
                    error("\t{0}: {1}".format(trace['function'],
                          trace['lineNumber']))
        else:
            # The structure of the result will depend upon what the Apps Script
            # function returns. Here, the function returns an Apps Script Object
            results = response['response'].get('result', {})
            # drop the first (header) row
            return results[1:]

    except errors.HttpError as e:
        # The API encountered a problem before the script started executing.
        error(e.content)


def get_member_teams(team_service_url, access_token):
    headers = {'Authorization': 'Bearer {}'.format(access_token)}

    with Action('Collecting team memberships from team service..') as act:
        r = requests.get(team_service_url + '/teams', headers=headers)
        r.raise_for_status()

        uid_to_teams = collections.defaultdict(set)

        for team in r.json():
            if team['id']:
                resp = requests.get(team_service_url + '/teams/{}'.format(team['id']), headers=headers)
                act.progress()
                data = resp.json()
                for member in data.get('member', []):
                    uid_to_teams[member].add(data['id'])

    return uid_to_teams


def get_users(user_service_url, access_token):
    with Action('Retrieving GitHub usernames from Google Spreadsheet..'):
        rows = get_github_usernames()

    info('Found {} GitHub usernames'.format(len(rows)))

    headers = {'Authorization': 'Bearer {}'.format(access_token)}
    for email, github_username in rows:
        if email and github_username:
            github_username = github_username.split('/')[-1]
            with Action('Checking {}..'.format(email)):
                r = requests.get(user_service_url + '/employees', params={'mail': email}, headers=headers)
                if r.status_code == 200:
                    found = False
                    for user in r.json():
                        if user['email'] == email and user['login']:
                            found = True
                            yield github_username, user['login']
                    if not found:
                        info('{} not found as employee'.format(email))
                r.raise_for_status()


def sync(team_service_url, user_service_url, github_access_token, dry_run: bool=False, no_remove: bool=False, filter: str=None):
    '''
    Synchronize users and team memberships with GitHub.com.

    Second argument must be the URL to team service providing team membership information.
    '''
    # we just assume we got a valid token
    access_token = zign.api.get_token('github-user-team-sync', ['uid'])

    users = list(get_users(user_service_url, access_token))

    uid_to_teams = get_member_teams(team_service_url, access_token)

    teams_with_members = set(itertools.chain(*uid_to_teams.values()))
    info('Found {} users in {} teams'.format(len(uid_to_teams), len(teams_with_members)))

    headers = {"Authorization": "token {}".format(github_access_token)}

    def request(func, url, **kwargs):
        if dry_run:
            print('**DRY-RUN** {} {}'.format(func, url))
            return MagicMock()
        else:
            return func(url, **kwargs)

    def create_github_team(name: str):
        description = '{} team'.format(name)
        response = request(
            requests.post,
            github_base_url + "orgs/zalando/teams",
            data=json.dumps({
                "name": name,
                "description": description,
                "permission": "admin"
                }),
            headers=headers)
        data = response.json()
        errors = data.get('errors')
        if errors:
            for error in errors:
                if error.get('code') == 'already_exists':
                    return
        response.raise_for_status()
        return response.json()

    def get_github_teams():
        teams_by_name = {}
        page = 1
        while True:
            r = requests.get(github_base_url + 'orgs/zalando/teams', params={'per_page': 100, 'page': page}, headers=headers)
            for team in r.json():
                teams_by_name[team['name']] = team
            page += 1
            if 'next' not in r.headers.get('Link'):
                break
        return teams_by_name

    def get_github_people():
        users = set()
        page = 1
        while True:
            r = requests.get(github_base_url + 'orgs/zalando/members', params={'per_page': 100, 'page': page}, headers=headers)
            for user in r.json():
                users.add(user['login'])
            page += 1
            if 'next' not in r.headers.get('Link'):
                break
        return users

    def add_github_team_member(team: dict, username: str):
        info('Adding {} to {}..'.format(username, team['name']))
        r = request(requests.put, github_base_url + 'teams/{}/memberships/{}'.format(team['id'], username), headers=headers)
        r.raise_for_status()

    def remove_github_team_member(team: dict, username: str):
        info('Removing {} from {}..'.format(username, team['name']))
        r = request(requests.delete, github_base_url + 'teams/{}/memberships/{}'.format(team['id'], username), headers=headers)
        r.raise_for_status()

    def get_github_team_members(team: dict):
        r = requests.get(github_base_url + 'teams/{}/members'.format(team['id']), headers=headers)
        r.raise_for_status()
        usernames = set([row['login'] for row in r.json()])
        return usernames

    users_by_team = collections.defaultdict(set)

    for github_username, uid in users:
        if filter and filter.lower() not in github_username.lower():
            continue
        with Action('Checking GitHub user {}..'.format(github_username)) as act:
            user_response = requests.get(
                github_base_url + "users/{}".format(github_username),
                headers=headers)

            if user_response.status_code == 200:
                team_ids = uid_to_teams.get(uid, [])
                if team_ids:
                    for team_id in team_ids:
                        create_github_team(team_id)
                        github_teams = get_github_teams()
                        github_team = github_teams.get(team_id)
                        if not github_team:
                            act.error('no GitHub team: {}'.format(team_id))
                            continue
                        add_github_team_member(github_team, github_username)
                        users_by_team[github_team['id']].add(github_username)
                else:
                    # add to "All Org Members" team
                    create_github_team(ALL_ORGANIZATION_MEMBERS_TEAM)
                    github_teams = get_github_teams()
                    github_team = github_teams.get(ALL_ORGANIZATION_MEMBERS_TEAM)
                    add_github_team_member(github_team, github_username)
                    users_by_team[github_team['id']].add(github_username)
            else:
                act.error('not found')

    known_github_usernames = set([github_username for github_username, _ in users])
    github_org_members = get_github_people()
    info('Unknown GitHub usernames:')
    for username in sorted(github_org_members - known_github_usernames):
        info('* {}'.format(username))

    with Action('Creating team for all organization members..'):
        create_github_team(ALL_ORGANIZATION_MEMBERS_TEAM)
        github_teams = get_github_teams()
        github_team = github_teams.get(ALL_ORGANIZATION_MEMBERS_TEAM)
        for github_username in github_org_members:
            add_github_team_member(github_team, github_username)

    if no_remove:
        info('Not removing any team members')
    else:
        github_teams = get_github_teams()
        for team_id, github_team in github_teams.items():
            if team_id not in teams_with_members:
                continue
            with Action('Removing members of team {}..'.format(team_id)):
                github_members = get_github_team_members(github_team)
                team_members = users_by_team[github_team['id']]
                members_to_be_removed = github_members - team_members
                for member in members_to_be_removed:
                    if filter and filter.lower() not in member.lower():
                        continue
                    remove_github_team_member(github_team, member)


def run_update(signum):
    if uwsgi.is_locked(signum):
        return
    uwsgi.lock(signum)
    try:
        sync(os.getenv('TEAM_SERVICE_URL'), os.getenv('USER_SERVICE_URL'), os.getenv('GITHUB_ACCESS_TOKEN'), no_remove=True)
        time.sleep(60)
    finally:
        uwsgi.unlock(signum)


def get_health():
    return True


logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
app = connexion.App(__name__)
app.add_api('swagger.yaml')
# set the WSGI application callable to allow using uWSGI:
# uwsgi --http :8080 -w app
application = app.app

try:
    import uwsgi
    signum = 1
    uwsgi.register_signal(signum, "", run_update)
    uwsgi.add_timer(signum, int(os.getenv('UPDATE_INTERVAL_SECONDS', '300')))
except Exception as e:
    print(e)

if __name__ == '__main__':
    app.run(port=8080)

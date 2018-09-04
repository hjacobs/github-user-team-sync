#!/usr/bin/env python3

import collections
import itertools
import json
import logging
import os
import requests
import time
import zign.api

from unittest.mock import MagicMock

ALL_ORGANIZATION_MEMBERS_TEAM = 'All Organization Members'

github_base_url = "https://api.github.com/"

logger = logging.getLogger('app')

sess = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
sess.mount('https://', adapter)
requests = sess

APPLICATION_NAME = 'github-user-team-sync'

CACHE_DIR = '/tmp/github-user-team-sync'


def get_cache(key):
    try:
        with open(os.path.join(CACHE_DIR, key + '.json')) as fd:
            data = json.load(fd)
    except:
        return None
    return data


def set_cache(key, val):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, key + '.json'), 'w') as fd:
        json.dump(val, fd)


def get_member_teams(team_service_url, access_token):
    headers = {'Authorization': 'Bearer {}'.format(access_token)}

    logger.info('Collecting team memberships from team service..')
    r = requests.get(team_service_url + '/api/teams', headers=headers)
    r.raise_for_status()

    uid_to_teams = collections.defaultdict(set)

    for team in r.json():
        if team['id']:
            try:
                resp = requests.get(team_service_url + '/api/teams/{}'.format(team['id']), headers=headers)
                resp.raise_for_status()
            except:
                logger.exception('Failed to load team {}'.format(team['id']))
            else:
                data = resp.json()
                for member in data.get('member', []):
                    uid_to_teams[member].add(data['id'])

    return uid_to_teams


def get_users(user_service_url, access_token):
    headers = {'Authorization': 'Bearer {}'.format(access_token)}
    r = requests.get(user_service_url + '/api/employees', headers=headers)
    r.raise_for_status()

    employees = r.json()
    active_employees = set()

    for employee in employees:
        if not employee.get('inactive'):
            active_employees.add(employee['login'])

    logger.info('Found {} active employees'.format(len(active_employees)))

    logger.info('Retrieving GitHub usernames from Users API..')
    r = requests.get(user_service_url + '/api/employees?account=github', headers=headers)
    r.raise_for_status()

    handles = r.json()
    logger.info('Found {} users with GitHub username'.format(len(handles)))

    for uid, github_usernames in handles.items():
        if uid in active_employees:
            for username in github_usernames:
                yield username, uid


def sync_org(org, github_access_token, users, uid_to_teams, teams_with_members, dry_run, no_remove, filter):
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
            github_base_url + "orgs/{}/teams".format(org),
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
                if error.get('message') == 'Name has already been taken':
                    # "already exists"
                    return
            logger.error('Failed to create {}: {}'.format(description, errors))
        response.raise_for_status()
        return response.json()

    def get_github_teams():
        teams_by_name = {}
        page = 1
        while True:
            r = requests.get(github_base_url + 'orgs/{}/teams'.format(org), params={'per_page': 100, 'page': page}, headers=headers)
            r.raise_for_status()
            for team in r.json():
                teams_by_name[team['name']] = team
            page += 1
            if 'next' not in r.headers.get('Link', ''):
                break
        return teams_by_name

    def get_github_people():
        users = set()
        page = 1
        while True:
            r = requests.get(github_base_url + 'orgs/{}/members'.format(org), params={'per_page': 100, 'page': page}, headers=headers)
            r.raise_for_status()
            for user in r.json():
                users.add(user['login'])
            page += 1
            if 'next' not in r.headers.get('Link', ''):
                break
        return users

    def add_github_team_member(team: dict, username: str):
        logger.info('Adding {} to {}..'.format(username, team['name']))
        r = request(requests.put, github_base_url + 'teams/{}/memberships/{}'.format(team['id'], username), headers=headers)
        r.raise_for_status()

    def remove_github_team_member(team: dict, username: str):
        logger.info('Removing {} from {}..'.format(username, team['name']))
        r = request(requests.delete, github_base_url + 'teams/{}/memberships/{}'.format(team['id'], username), headers=headers)
        r.raise_for_status()

    def get_github_team_members(team: dict):
        r = requests.get(github_base_url + 'teams/{}/members'.format(team['id']), headers=headers)
        r.raise_for_status()
        usernames = set([row['login'] for row in r.json()])
        return usernames

    users_by_team = collections.defaultdict(set)

    def handle_user(github_username):
        if filter and filter.lower() not in github_username.lower():
            return
        logger.debug('Checking GitHub user {}..'.format(github_username))
        user_response = requests.head(
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
                        logger.warn('no GitHub team: {}'.format(team_id))
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
        elif user_response.status_code == 404:
            logger.info('GitHub user {} not found'.format(github_username))
        else:
            user_response.raise_for_status()

    last_full_sync = get_cache('last_full_sync_{}'.format(org))
    if last_full_sync and last_full_sync > time.time() - int(os.getenv('FULL_SYNC_INTERVAL_SECONDS', '3600')):
        github_org_members = get_github_people()
        for github_username, uid in users:
            # only handle "new" GitHub users
            if github_username not in github_org_members:
                handle_user(github_username)
        return

    # full sync
    for github_username, uid in users:
        handle_user(github_username)

    known_github_usernames = set([github_username for github_username, _ in users])
    github_org_members = get_github_people()
    for username in sorted(github_org_members - known_github_usernames):
        logger.warn('Unknown GitHub username "{}"'.format(username))

    logger.info('Creating team for all organization members..')
    create_github_team(ALL_ORGANIZATION_MEMBERS_TEAM)
    github_teams = get_github_teams()
    github_team = github_teams.get(ALL_ORGANIZATION_MEMBERS_TEAM)
    # only add known (active) users to the All Org team
    for github_username in known_github_usernames:
        add_github_team_member(github_team, github_username)

    if no_remove:
        logger.info('Not removing any team members')
    else:
        github_teams = get_github_teams()
        for team_id, github_team in github_teams.items():
            if team_id not in teams_with_members:
                continue
            logger.info('Removing members of team {}..'.format(team_id))
            github_members = get_github_team_members(github_team)
            team_members = users_by_team[github_team['id']]
            members_to_be_removed = github_members - team_members
            for member in members_to_be_removed:
                if filter and filter.lower() not in member.lower():
                    continue
                remove_github_team_member(github_team, member)
    set_cache('last_full_sync_{}'.format(org), time.time())


def sync(orgs, team_service_url, user_service_url, github_access_token, dry_run: bool=False, no_remove: bool=False, filter: str=None):
    '''
    Synchronize users and team memberships with GitHub.com.

    Second argument must be the URL to team service providing team membership information.
    '''
    # we just assume we got a valid token
    access_token = zign.api.get_token('github-user-team-sync', ['uid'])

    users = list(set(get_users(user_service_url, access_token)))
    logger.info('Found {} active GitHub user mappings'.format(len(users)))

    uid_to_teams = get_member_teams(team_service_url, access_token)

    teams_with_members = set(itertools.chain(*uid_to_teams.values()))
    logger.info('Found {} users in {} teams'.format(len(uid_to_teams), len(teams_with_members)))

    for org in orgs:
        logger.info('Syncing {} organization..'.format(org))
        try:
            sync_org(org, github_access_token, users, uid_to_teams, teams_with_members, dry_run, no_remove, filter)
        except Exception as e:
            logger.exception('Failed to sync %s: %s', org, e)


def run_update():
    sync(os.getenv('GITHUB_ORGANIZATIONS').split(','), os.getenv('TEAM_SERVICE_URL'), os.getenv('USER_SERVICE_URL'), os.getenv('GITHUB_ACCESS_TOKEN'), no_remove=True)


logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')

if __name__ == '__main__':
    run_update()

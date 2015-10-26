#!/usr/bin/env python3

import click
import collections
import itertools
import json
import requests
import zign.api

from mock import MagicMock

from clickclick import Action, info

ALL_ORGANIZATION_MEMBERS_TEAM = 'All Organization Members'

github_base_url = "https://api.github.com/"

sess = requests.Session()
adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
sess.mount('https://', adapter)
requests = sess


def read_csv_file(csv_file):
    for line in csv_file:
        cols = line.strip().split(',')
        try:
            email, github_username, uid = cols
        except:
            raise click.UsageError('Invalid CSV file format: expected three columns')
        # just take the last path segment for cases where github.com/... is entered
        github_username = github_username.split('/')[-1]
        yield github_username, uid


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


@click.command()
@click.argument('csv_file', type=click.File('r'))
@click.argument('team_service_url')
@click.option('--github-access-token', envvar='GITHUB_ACCESS_TOKEN', help='GitHub personal access token', metavar='TOKEN')
@click.option('--dry-run', is_flag=True, help='No-op: do not modify anything, just show what would be done')
@click.option('--no-remove', is_flag=True, help='Do not remove any team members')
@click.option('--filter', help='Only process matching GitHub usernames')
@click.option('--team-service-token-name', default='team-service', help='Zign OAuth token name to use', metavar='NAME')
def cli(csv_file, team_service_url, github_access_token, dry_run: bool, no_remove: bool, team_service_token_name, filter: str):
    '''
    Synchronize users and team memberships with GitHub.com.

    First argument must be a CSV file with three columns: first column email, second column GitHub username and last column the user's UID.

    Second argument must be the URL to team service providing team membership information.
    '''
    # we just assume we got a valid token
    access_token = zign.api.get_existing_token(team_service_token_name)
    if not access_token:
        raise click.UsageError('Please use "zign token -n {}" to get an OAuth access token'.format(team_service_token_name))
    access_token = access_token['access_token']

    users = list(read_csv_file(csv_file))

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

if __name__ == '__main__':
    cli()

#!/usr/bin/env python3

import click
import collections
import json
import requests
import zign.api

from mock import MagicMock

from clickclick import Action, info


github_base_url = "https://api.github.com/"

def read_csv_file(csv_file: file):
    for line in csv_file:
        cols = line.strip().split(',')
        try:
            email, github_username, uid = cols
        except:
            raise click.UsageError('Invalid CSV file format: expected three columns')
        # just take the last path segment for cases where github.com/... is entered
        github_username = github_username.split('/')[-1]
        yield github_username, uid


@click.command()
@click.argument('csv_file', type=click.File('r'))
@click.argument('team_service_url')
@click.option('--github-access-token', envvar='GITHUB_ACCESS_TOKEN', help='GitHub personal access token', metavar='TOKEN')
@click.option('--dry-run', is_flag=True, help='No-op: do not modify anything, just show what would be done')
@click.option('--no-remove', is_flag=True, help='Do not remove any team members')
@click.option('--team-service-token-name', default='team-service', help='Zign OAuth token name to use', metavar='NAME')
def cli(csv_file, team_service_url, github_access_token, dry_run: bool, no_remove: bool, team_service_token_name):
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

    headers = {'Authorization': 'Bearer {}'.format(access_token)}

    with Action('Collecting team memberships from team service..') as act:
        r = requests.get(team_service_url + '/teams', headers=headers)

        uid_to_teams = collections.defaultdict(set)
        teams_with_members = set()

        for team in r.json():
            resp = requests.get(team_service_url + '/teams/{}'.format(team['id']), headers=headers)
            act.progress()
            data = resp.json()
            for member in data['members']:
                uid_to_teams[member].add(data['id'])
                teams_with_members.add(data['id'])

    headers = {"Authorization": "token {}".format(github_access_token)}

    def request(func, url, **kwargs):
        if dry_run:
            print('**DRY-RUN** {} {}'.format(func, url))
            return MagicMock()
        else:
            return func(url, **kwargs)

    def create_github_team(name: str):
        description = '{} team'.format(name)
        response = request(requests.post,
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
                    info('team already exists')
                    return
        response.raise_for_status()
        return response.json()

    def get_github_teams():
        r = requests.get(github_base_url + 'orgs/zalando/teams', headers=headers)
        teams_by_name = {}
        for team in r.json():
            teams_by_name[team['name']] = team
        return teams_by_name

    def add_github_team_member(team: dict, username: str):
        r = request(requests.put, github_base_url + 'teams/{}/memberships/{}'.format(team['id'], username), headers=headers)
        r.raise_for_status()

    def remove_github_team_member(team: dict, username: str):
        r = request(requests.delete, github_base_url + 'teams/{}/memberships/{}'.format(team['id'], username), headers=headers)
        r.raise_for_status()

    def get_github_team_members(team: dict):
        r = requests.get(github_base_url + 'teams/{}/members'.format(team['id']), headers=headers)
        r.raise_for_status()
        usernames = set([row['login'] for row in r.json()])
        return usernames

    users_by_team = collections.defaultdict(set)

    for github_username, uid in users:
        with Action('Checking GitHub user {}..'.format(github_username)) as act:
            user_response = requests.get(
                github_base_url + "users/{}".format(github_username),
                headers=headers)

            if user_response.status_code == 200:
                team_ids = uid_to_teams.get(uid, [])
                for team_id in team_ids:
                    print(team_id)
                    create_github_team(team_id)
                    github_teams = get_github_teams()
                    github_team = github_teams.get(team_id)
                    if not github_team:
                        act.error('no GitHub team')
                        continue
                    add_github_team_member(github_team, github_username)
                    users_by_team[github_team['id']].add(github_username)
            else:
                act.error('not found')

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
                if not members_to_be_removed:
                    info('nothing to do')
                for member in members_to_be_removed:
                    remove_github_team_member(github_team, member)

if __name__ == '__main__':
    cli()

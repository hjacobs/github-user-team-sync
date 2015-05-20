#!/usr/bin/env python3

import click
import collections
import json
import requests
import zign.api

from mock import MagicMock

from clickclick import Action, info


github_base_url = "https://api.github.com/"


@click.command()
@click.argument('csv_file')
@click.argument('team_service_url')
@click.option('--github-access-token', envvar='GITHUB_ACCESS_TOKEN')
@click.option('--dry-run', is_flag=True)
def cli(csv_file, team_service_url, github_access_token, dry_run):
    # we just assume we got a valid token
    access_token = zign.api.get_existing_token('team-service')
    access_token = access_token['access_token']

    headers = {'Authorization': 'Bearer {}'.format(access_token)}

    with Action('Collecting team memberships from team service..') as act:
        r = requests.get(team_service_url + '/teams', headers=headers)

        uid_to_team = {}
        teams_with_members = set()

        for team in r.json():
            resp = requests.get(team_service_url + '/teams/{}'.format(team['id']), headers=headers)
            act.progress()
            data = resp.json()
            for member in data['members']:
                uid_to_team[member] = data['id']
                teams_with_members.add(data['id'])

    headers = {"Authorization": "token {}".format(github_access_token)}

    def lookup_team_id(email):
        return 'stups'

    def request(func, url, **kwargs):
        if dry_run:
            print('**DRY-RUN** {} {}'.format(func, url))
            return MagicMock()
        else:
            return func(url, **kwargs)

    def create_github_team(name):
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

    with open(csv_file) as file:
        for line in file:
            email, github_username = line.strip().split(',')
            with Action('Checking GitHub user {}..'.format(github_username)):
                user_response = requests.get(
                    github_base_url + "users/{}".format(github_username),
                    headers=headers)

                if user_response.status_code == 200:
                    team_id = lookup_team_id(email)
                    create_github_team(team_id)
                    github_teams = get_github_teams()
                    github_team = github_teams.get(team_id)
                    add_github_team_member(github_team, github_username)
                    users_by_team[github_team['id']].add(github_username)

    github_teams = get_github_teams()
    for team_id, github_team in github_teams.items():
        if team_id not in teams_with_members:
            continue
        with Action('Removing members of team {}..'.format(team_id)):
            github_members = get_github_team_members(github_team)
            team_members = users_by_team[github_team['id']]
            members_to_be_removed = github_members - team_members
            for member in members_to_be_removed:
                remove_github_team_member(github_team, member)

if __name__ == '__main__':
    cli()

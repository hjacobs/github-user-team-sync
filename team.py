#!/usr/bin/env python3

import requests
import sys
import zign.api

team_service_url = sys.argv[1]

# we just assume we got a valid token
access_token = zign.api.get_existing_token('team-service')
access_token = access_token['access_token']

headers = {'Authorization': 'Bearer {}'.format(access_token)}
r = requests.get(team_service_url + '/teams', headers=headers)

uid_to_team = {}

for team in r.json():
    resp = requests.get(team_service_url + '/teams/{}'.format(team['id']), headers=headers)
    info = resp.json()
    for member in info['members']:
        uid_to_team[member] = info['id']

print(uid_to_team)



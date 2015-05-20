#!/usr/bin/env python3

import requests
import sys
import zign.api

team_service_url = sys.argv[1]

# we just assume we got a valid token
access_token = zign.api.get_existing_token('team-service')

r = requests.get(team_service_url + '/teams', headers={'Authorization': 'Bearer {}'.format(access_token)})

team_ids = set()

for team in r.json():
    resp = requests.get(team_service_url + '/teams/{}'.format(team['id']), headers={'Authorization': 'Bearer {}'.format(access_token)})
    info = resp.json()
    print(info)



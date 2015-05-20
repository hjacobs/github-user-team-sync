#! usr/bin/env python3

import json
import sys
import requests
import os


github_access_token = os.environ["GITHUB_ACCESS_TOKEN"]

headers = { "AUTHORIZATION" : "token {}".format(github_access_token)}

github_base_url = "https://api.github.com/"

def lookup_team_id(email):
    return 'stups'

def create_github_team(name, description):
    response = requests.post(
        github_base_url + "orgs/zalando/teams", 
        data = json.dumps({
            "name" : name, 
            "description": description,
            "permission": "admin"
            }),
        headers = headers ) 
    response.raise_for_status()
    return response.json()


path = sys.argv[1]
with open(path) as file :
    for line in file :
        email, github_username = line.strip().split(',')
        user_response = requests.get(
            github_base_url + "users/{}".format(github_username),
            headers = headers)

        if user_response.status_code == 200
            team_id = lookup_team_id(email)
            create_github_team(team_id)





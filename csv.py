#! usr/bin/env python3

import sys
import requests
import os

github_access_token = os.environ["GITHUB_ACCESS_TOKEN"]

path = sys.argv[1]
with open(path) as file : 
	for line in file : 
		email, github_username = line.strip().split(',')
		user_response = requests.get(
			"https://api.github.com/users/{}".format(github_username), 
			headers = { "AUTHORIZATION" : "token {}".format(github_access_token)})
		
		print(user_response.status_code)
		print(email, github_username) 


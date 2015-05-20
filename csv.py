#! usr/bin/env python3

import sys
import requests



path = sys.argv[1]
with open(path) as file : 
	for line in file : 
		email, github_username = line.strip().split(',')
		user_response = requests.get("https://api.github.com/users/{}".format(github_username))
		print(user_response.status_code)
			#print(email, github_username) 


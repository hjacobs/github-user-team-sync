#/usr/bin/env bash
# Reads config from ./credentials file
# Takes standard input in CSV (separated with ",")
# For each line of input takes first field (email),
#   then looks up the corresponding uid in a LDAP
#   and then appends it as a last column
# I.e.:
# name.surname@example.com,whatever,, -> name.surname@example.com,whatever,,,nsurname
# Example run:
# $ cat usernames.csv | tail -n +2 | ./ldap.sh
# Config example:
# UNAME=[username]
# PASS=[password]
# HOST="ldaps://ldap.example"
# BASE_DN="ou=whatever,dc=example,dc=com"


set -eu

# get config from a file
source ./credentials

while read line; do
    email=$(echo $line | cut -d ',' -f1)
    uid=$(ldapsearch -H "$HOST" -w $PASS \
            -D uid=$UNAME,$BASE_DN \
            -b $BASE_DN "(mail=$email)" uid \
            | grep '^uid: ' \
            | sed 's/^uid: //'
          )
    echo $line,$uid
done
exit

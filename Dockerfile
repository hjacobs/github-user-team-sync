FROM registry.opensource.zalan.do/stups/python:3.5.1-21

COPY requirements.txt /
RUN pip3 install -r /requirements.txt
RUN chmod +x /usr/local/bin/uwsgi

COPY app.py /
COPY swagger.yaml /

EXPOSE 8080

VOLUME /tmp

CMD uwsgi --http :8080 -w app --master -p 4 --locks 2 --mule --logformat 'INFO uwsgi.request: %(addr) "%(method) %(uri) %(proto)" %(status) %(size) "%(uagent)"'

COPY scm-source.json /

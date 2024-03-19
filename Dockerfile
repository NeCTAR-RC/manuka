# For more information, please refer to https://aka.ms/vscode-docker-python
FROM ubuntu:22.04

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

# Install pip requirements
COPY requirements.txt .

RUN apt update && apt install -y gcc git curl apache2 libapache2-mod-wsgi-py3 libapache2-mod-shib python3-pip && apt clean

RUN pip install -c https://releases.openstack.org/constraints/upper/zed -r requirements.txt

WORKDIR /app
COPY . /app

RUN pip install -c https://releases.openstack.org/constraints/upper/zed -e /app

EXPOSE 80
CMD ["/app/docker/docker-run.sh"]

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

# Creates a non-root user and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
#RUN useradd -u 42420 appuser && chown -R appuser /app
#USER appuser

#RUN apt install -y apache2 libapache2-mod-wsgi-py3 libapache2-mod-shib
#RUN apt clean

EXPOSE 80
CMD ["/usr/sbin/apache2ctl", "-D", "FOREGROUND"]

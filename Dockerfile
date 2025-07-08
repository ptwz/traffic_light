FROM debian:latest

USER root

RUN useradd -m ampel

RUN apt-get update ; apt-get upgrade -y

RUN apt-get install -y python3 python3-behave python3-serial python3-paho-mqtt

ADD python /opt/ampel/

USER ampel

ENTRYPOINT sh /opt/ampel/testing/run_tests.sh

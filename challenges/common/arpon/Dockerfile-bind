FROM sameersbn/bind:9.9.5-20161106

# BUILD ARPON FROM SOURCE UNTIL IT'S AVAILIBLE FROM REPO
RUN apt-get update && \
    apt-get -y install autoconf automake cmake libpcap-dev libnet1-dev libdumbnet-dev build-essential git python3-pip

ARG ARPON_REPO_URL=https://github.com/nategraf/arpon.git
ARG ARPON_REPO_BRANCH=capabilities

COPY ./make-arpon.sh ./make-arpon.sh
RUN sh ./make-arpon.sh

RUN apt-get -y remove autoconf automake cmake build-essential git python3-pip && \
    apt-get -y autoremove && \
    rm ./make-arpon.sh
#############################################

COPY ./arpon-start /sbin/arpon-start
RUN chmod +x /sbin/arpon-start

ENTRYPOINT ["/sbin/arpon-start", "/sbin/entrypoint.sh"]

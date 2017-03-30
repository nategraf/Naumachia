# Orignally written by https://github.com/jcbiellikltd/docker-dhcpd
FROM alpine:latest

RUN set -xe \
	&& apk add --update --no-progress dhcp bash gettext \
	&& rm -rf /var/cache/apk/*

EXPOSE 67/udp 67/tcp

RUN touch /var/lib/dhcp/dhcpd.leases

COPY ./entrypoint.sh /entrypoint.sh
COPY ./dhcpd.conf.template /dhcpd.conf.template
COPY ./dhcpd_envs.sh /dhcpd_envs.sh

RUN chmod +x entrypoint.sh
RUN chmod +x dhcpd_envs.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["/usr/sbin/dhcpd", "-4", "-f", "-d", "--no-pid", "-cf", "/etc/dhcp/dhcpd.conf"]

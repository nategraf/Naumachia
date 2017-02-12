FROM kylemanna/openvpn
COPY ./bridge-start /bin/bridge-start
RUN chmod +x /bin/bridge-start
COPY ./learn-address-test.sh /learn-address.sh
RUN chmod +x /learn-address.sh
COPY ./up-test.sh /up.sh
RUN chmod +x /up.sh
CMD ["bridge-start"]

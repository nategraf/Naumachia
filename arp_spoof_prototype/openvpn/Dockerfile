FROM kylemanna/openvpn
COPY ./bridge-start /bin/bridge-start
RUN chmod +x /bin/bridge-start
CMD /bin/bridge-start && ovpn_run

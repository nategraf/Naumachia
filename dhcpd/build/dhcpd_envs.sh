function split_ipaddr {
    (IFS=. read IP[0] IP[1] IP[2] IP[3] <<< "$1"; echo "${IP[@]}")
}

if [ -z "$DHCPD_DEV" ]; then
    DHCPD_DEV="eth0"
fi

INFO=($(ifconfig | grep -EA 1 "^${DHCPD_DEV}\b" | grep -oE "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b"))
export DHCPD_IPADDR="${INFO[0]}"
export DHCPD_BCAST="${INFO[1]}"
export DHCPD_NMASK="${INFO[2]}"

IP=($(split_ipaddr "$DHCPD_IPADDR"))
NM=($(split_ipaddr "$DHCPD_NMASK"))

export DHCPD_NADDR=$(printf "%d.%d.%d.%d\n" "$((IP[0] & NM[0]))" "$((IP[1] & NM[1]))" "$((IP[2] & NM[2]))" "$((IP[3] & NM[3]))")

echo "IPADDR: $DHCPD_IPADDR"
echo "BCAST:  $DHCPD_BCAST"
echo "NMASK:  $DHCPD_NMASK"
echo "NADDR:  $DHCPD_NADDR"

NA=($(split_ipaddr "$DHCPD_NADDR"))
if [ -z "$DHCPD_START" ]; then
    export DHCPD_START="0.0.0.1"
fi

STARTA=($(split_ipaddr "$DHCPD_START"))
export DHCPD_START=$(printf "%d.%d.%d.%d\n" "$(((STARTA[0] & ~NM[0]) + NA[0]))" "$(((STARTA[1] & ~NM[1]) + NA[1]))" "$(((STARTA[2] & ~NM[2]) + NA[2]))" "$(((STARTA[3] & ~NM[3]) + NA[3]))")

if [ -z "$DHCPD_STOP" ]; then
    DHCPD_STOP="255.255.255.254"
fi

STOPA=($(split_ipaddr "$DHCPD_STOP"))
export DHCPD_STOP=$(printf "%d.%d.%d.%d\n" "$(((STOPA[0] & ~NM[0]) + NA[0]))" "$(((STOPA[1] & ~NM[1]) + NA[1]))" "$(((STOPA[2] & ~NM[2]) + NA[2]))" "$(((STOPA[3] & ~NM[3]) + NA[3]))")

echo "START:  $DHCPD_START"
echo "STOP:   $DHCPD_STOP"

HOST_IP=`ip addr show eth0 | grep "inet " | awk '{ print $2 }' | awk -F "/"  '{ print $1 }'`
HOST_IPV6=`ip addr show eth0 | grep "inet6 " | awk '{ print $2 }' | awk -F "/"  '{ print $1 }'`

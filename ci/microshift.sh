#
# Installs Microshift on Docker
#
set -xe

: "${ACCT_MGT_VERSION:="master"}"
: "${ACCT_MGT_REPOSITORY:="https://github.com/cci-moc/openshift-acct-mgt.git"}"
: "${KUBECONFIG:=$HOME/.kube/config}"

test_dir="$PWD/testdata"
rm -rf "$test_dir"
mkdir -p "$test_dir"

sudo docker rm -f microshift
sudo docker volume rm -f microshift-data

echo "::group::Start microshift container"
sudo docker run -d --rm --name microshift --privileged \
    --hostname microshift \
    -v microshift-data:/var/lib \
    quay.io/microshift/microshift-aio:latest
echo "::endgroup::"

microshift_addr=$(sudo docker inspect microshift -f '{{ .NetworkSettings.IPAddress }}')
sudo sed -i '/onboarding-onboarding.cluster.local/d' /etc/hosts
echo "$microshift_addr  onboarding-onboarding.cluster.local" | sudo tee -a /etc/hosts

KUBECONFIG_FULL_PATH="$(readlink -f "$KUBECONFIG")"
mkdir -p "${KUBECONFIG_FULL_PATH%/*}"

echo "::group::Wait for Microshift"
for try in {0..10}; do
	echo "copying kubeconfig {$try}"
	sudo docker cp microshift:/var/lib/microshift/resources/kubeadmin/kubeconfig \
		"${KUBECONFIG}" && break
	sleep 2
done

sed -i "s/127.0.0.1/${microshift_addr}/g" "$KUBECONFIG"

while ! oc get route -A; do
    echo "Waiting for Microshift"
    sleep 5
done
echo "::endgroup::"

oc create sa coldfront
oc adm policy add-cluster-role-to-user cluster-admin system:serviceaccount:default:coldfront

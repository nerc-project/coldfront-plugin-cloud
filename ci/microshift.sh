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

sudo docker rm -f microshift registry

registry_port=$(( RANDOM % 1000 + 10000 ))

echo "::group::Start microshift container"
sudo docker run -d --rm --name microshift --privileged \
    --hostname microshift \
    -v microshift-data:/var/lib \
    -p "${registry_port}:5000" \
    quay.io/microshift/microshift-aio:latest
echo "::endgroup::"

microshift_addr=$(sudo docker inspect microshift -f '{{ .NetworkSettings.IPAddress }}')
sudo sed -i '/onboarding-onboarding.cluster.local/d' /etc/hosts
echo "$microshift_addr  onboarding-onboarding.cluster.local" | sudo tee -a /etc/hosts

echo "::group::Start registry container"
sudo docker run -d --name registry --network container:microshift registry:2
echo "::endgroup::"

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

# Install OpenShift Account Management
git clone "${ACCT_MGT_REPOSITORY}" "$test_dir/openshift-acct-mgt"
git -C "$test_dir/openshift-acct-mgt" config advice.detachedHead false
git -C "$test_dir/openshift-acct-mgt" checkout "$ACCT_MGT_VERSION"

echo "::group::Build openshift-acct-mgt image"
sudo docker build "$test_dir/openshift-acct-mgt" -t "127.0.0.1:${registry_port}/cci-moc/openshift-acct-mgt:latest"
sudo docker push "127.0.0.1:${registry_port}/cci-moc/openshift-acct-mgt:latest"
echo "::endgroup::"

echo "::group::Deploy openshift-acct-mgt"
oc apply -k "$test_dir/openshift-acct-mgt/k8s/overlays/crc"
oc wait -n onboarding --for=condition=available --timeout=800s deployment/onboarding
echo "::endgroup::"

sleep 60

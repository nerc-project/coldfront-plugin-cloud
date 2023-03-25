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

echo '127.0.0.1  onboarding-onboarding.cluster.local' | sudo tee -a /etc/hosts

echo "::group::Start microshift container"
sudo docker run -d --rm --name microshift --privileged \
    --network host \
    -v microshift-data:/var/lib \
    quay.io/microshift/microshift-aio:latest
echo "::endgroup::"

echo "::group::Start registry container"
sudo docker run -d --name registry --network host registry:2
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

while ! oc get route -A; do
    echo "Waiting for Microshift"
    sleep 5
done
echo "::endgroup::"

# Install OpenShift Account Management
git clone "${ACCT_MGT_REPOSITORY}" "$test_dir/openshift-acct-mgt"
git -C "$test_dir/openshift-acct-mgt" checkout "$ACCT_MGT_VERSION"

echo "::group::Build openshift-acct-mgt image"
sudo docker build "$test_dir/openshift-acct-mgt" -t "localhost:5000/cci-moc/openshift-acct-mgt:latest"
sudo docker push "localhost:5000/cci-moc/openshift-acct-mgt:latest"
echo "::endgroup::"

echo "::group::Deploy openshift-acct-mgt"
oc apply -k "$test_dir/openshift-acct-mgt/k8s/overlays/crc"
oc wait -n onboarding --for=condition=available --timeout=800s deployment/onboarding
echo "::endgroup::"

sleep 60

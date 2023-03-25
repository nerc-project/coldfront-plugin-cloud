#
# Installs Microshift on Docker
#
set -xe

: "${ACCT_MGT_VERSION:="master"}"
: "${ACCT_MGT_REPOSITORY:="https://github.com/cci-moc/openshift-acct-mgt.git"}"
: "${KUBECONFIG:=$HOME/.kube/config}"

echo '127.0.0.1  onboarding-onboarding.cluster.local' | sudo tee -a /etc/hosts

sudo docker run -d --rm --name microshift --privileged \
    --network host \
    -v microshift-data:/var/lib \
    quay.io/microshift/microshift-aio:latest

sudo docker run -d --name registry --network host registry:2

# https://github.com/nerc-project/coldfront-plugin-cloud/issues/50
sleep 30

KUBECONFIG_FULL_PATH="$(readlink -f "$KUBECONFIG")"
mkdir -p "${KUBECONFIG_FULL_PATH%/*}"
sudo docker cp microshift:/var/lib/microshift/resources/kubeadmin/kubeconfig "$KUBECONFIG"

while ! oc get all -h; do
    echo "Waiting on Microshift"
    sleep 5
done

# Install OpenShift Account Management
git clone "${ACCT_MGT_REPOSITORY}" ~/openshift-acct-mgt
cd ~/openshift-acct-mgt
git checkout "$ACCT_MGT_VERSION"
sudo docker build . -t "localhost:5000/cci-moc/openshift-acct-mgt:latest"
sudo docker push "localhost:5000/cci-moc/openshift-acct-mgt:latest"

oc apply -k k8s/overlays/crc
oc wait -n onboarding --for=condition=available --timeout=800s deployment/onboarding

sleep 60

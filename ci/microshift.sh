#
# Installs Microshift on Docker
#
set -xe

sudo apt-get update && sudo apt-get upgrade -y

if [[ ! "${CI}" == "true" ]]; then
    sudo apt-get install docker.io docker-compose python3-virtualenv -y
fi

echo '127.0.0.1  onboarding-onboarding.cluster.local' | sudo tee -a /etc/hosts

sudo docker run -d --rm --name microshift --privileged \
    --network host \
    -v microshift-data:/var/lib \
    quay.io/microshift/microshift-aio:latest

sudo docker run -d --name registry --network host registry:2

sleep 30

curl -O "https://mirror.openshift.com/pub/openshift-v4/$(uname -m)/clients/ocp/stable/openshift-client-linux.tar.gz"
sudo tar -xf openshift-client-linux.tar.gz -C /usr/local/bin oc kubectl

mkdir ~/.kube
sudo docker cp microshift:/var/lib/microshift/resources/kubeadmin/kubeconfig ~/.kube/config
oc get all

# Install OpenShift Account Management
git clone https://github.com/cci-moc/openshift-acct-mgt.git ~/openshift-acct-mgt
cd ~/openshift-acct-mgt
sudo docker build . -t "localhost:5000/cci-moc/openshift-acct-mgt:latest"
sudo docker push "localhost:5000/cci-moc/openshift-acct-mgt:latest"

oc apply -k k8s/overlays/crc
oc wait -n onboarding --for=condition=available --timeout=800s deployment/onboarding

cd ~/coldfront-plugin-openstack

sleep 60

Vagrant.configure("2") do |config|
    config.vm.synced_folder ".", "/home/vagrant/coldfront-plugin-cloud/"
    config.vm.network :private_network

    config.vm.define "openstack" do |openstack|
        openstack.vm.box = "generic/ubuntu2004"

        openstack.vm.provider "vmware_fusion" do |vb|
            vb.gui = false
            vb.memory = "9000"
            vb.cpus = "4"
        end

        openstack.vm.provision "shell", privileged: false, inline: <<-SHELL
            set -xe

            cd ~/coldfront-plugin-cloud
            ./ci/devstack.sh
            ./ci/setup.sh
            ./ci/run_functional_tests.sh
        SHELL
    end

    config.vm.define "openshift" do |openshift|
        openshift.vm.box = "generic/ubuntu2004"

        openshift.vm.provider "vmware_fusion" do |vb|
            vb.gui = false
            vb.memory = "4096"
            vb.cpus = "4"
        end

        openshift.vm.provision "shell", privileged: false, inline: <<-SHELL
            set -xe

            cd ~/coldfront-plugin-cloud
            ./ci/microshift.sh
            ./ci/setup.sh
            ./ci/run_functional_tests_openshift.sh
        SHELL
    end
end

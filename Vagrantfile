Vagrant.configure("2") do |config|
    config.vm.box = "generic/ubuntu2004"
    config.vm.synced_folder ".", "/home/vagrant/coldfront-plugin-openstack/"

    config.vm.network :private_network

    config.vm.provider "vmware_fusion" do |vb|
        vb.gui = false
        vb.memory = "9000"
        vb.cpus = "4"
    end

    config.vm.provision "shell", privileged: false, inline: <<-SHELL
        set -xe

        cd ~/coldfront-plugin-openstack
        ./ci/devstack.sh
        ./ci/setup.sh
        ./ci/run_functional_tests.sh
    SHELL
end

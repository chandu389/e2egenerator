from xml.dom.minidom import parse, Document, parseString
import os
import logging
import argparse
import subprocess
import xml.etree.ElementTree as ET
import warnings

import re

log = logging.getLogger(__name__)

class e2egenerator:
    def __init__(self):

        self.desc = "E2E payload generator"

        parser = argparse.ArgumentParser(description=self.desc)
        parser.add_argument('-vf', '--vnfdfile',
                            help="The source rfs file")
        parser.add_argument('-s', '--servicetype',
                            help="Service type ex. wsg")
        parser.add_argument('-y', '--yangfile',
                            help="Yang file where additioanl params are defined")
        parser.add_argument('-i', '--ncsdir',
                            help="Path of NCS_DIR")
        parser.add_argument('-l', '--log-level',
                            choices=['DEBUG', 'INFO', 'WARNING'], default=logging.INFO,
                            help="Set the log level for standalone logging")

        args = parser.parse_args()
        self.args = args
        self.parser = parser

        if not (args.vnfdfile and args.servicetype) :
            print("error: the following arguments are required: -vf/--vnfdfile and -s/--servicetype")
            return

        # Initialize the log and have the level set properly
        setup_logger(args.log_level)
        warnings.filterwarnings("ignore")

        #Define global variables
        self.yang_module_path = self.args.ncsdir + '/src/ncs/yang'
        self.namespaces = {'config': 'http://tail-f.com/ns/config/1.0', 'ns': 'urn:rakuten:rmno:rcs' , 'e2e' : 'urn:rakuten:rmno:e2e', 'yang' : 'urn:ietf:params:xml:ns:yang:yin:1', 'v' : 'urn:etsi:nfv:yang:etsi-nfv-descriptors'}
        self.mtu = "1450"
        self.pod = "mavenir_openstack_vim"
        self.project = "admin"
        self.provider = "mavenir"
        self.solution = "rcs"
        self.domain  = "rakuten.com"
        self.project = "admin"


        self.vnfd_dom = self.parseXML(self.args.vnfdfile)
        self.create_network_map()
        log.debug(self.network_map)
        self.service_type = self.args.servicetype
        self.create_descriptor()
        self.create_deployment()
        log.info("E2E payload created")

    def create_network_map(self):
        self.network_map = {}
        network_list = self.vnfd_dom.findall('.//v:vnfd/v:ext-cpd', self.namespaces)

        for network in network_list:
            self.network_map[network.find('./v:int-virtual-link-desc', self.namespaces).text] = network.find('./v:id',
                                                                                                 self.namespaces).text

    def create_descriptor(self):
        """

        :return:
        """
        #Create descriptor file
        self.root_descriptor = self.build_tree('config', self.namespaces['config'])
        descriptor_rmno_ele = ET.SubElement(self.root_descriptor, 'rmno')
        descriptor_rmno_ele.set("xmlns", self.namespaces['e2e'])
        nwserv_ele = ET.SubElement(descriptor_rmno_ele, 'network-service')
        descriptor_ele = ET.SubElement(nwserv_ele, 'descriptor')

        # Add elements in descriptor

        name_ele = ET.SubElement(descriptor_ele, 'name')
        name_ele.text = self.provider + "-" + self.solution + "-" + self.service_type + "-descriptor"

        type_ele = ET.SubElement(descriptor_ele, 'type')
        type_ele.text = self.provider + "-" + self.solution + "-" + self.service_type

        nf_ele = ET.SubElement(descriptor_ele, 'network-function')
        nf_type_ele = ET.SubElement(nf_ele, 'type')
        nf_type_ele.text = self.provider + "-" + self.solution + "-" + self.service_type
        nf_vnfd_ele = ET.SubElement(nf_ele, 'vnfd')
        nf_vnfd_ele.text = self.vnfd_dom.find('.//v:vnfd/v:id',self.namespaces).text

        #Create descriptor networks

        self.create_descriptor_networks(nf_ele)
        self.create_descriptor_units(nf_ele)

        # Create prettt network
        descriptor_str = ET.tostring(self.root_descriptor, 'utf-8')
        self.descriptor_dom = parseString(descriptor_str)
        self.output(self.descriptor_dom, 'descriptor.xml')

    def read_additional_params(self):
        result = subprocess.run(['pyang', self.args.yangfile, '-f', 'yin', '-p', self.yang_module_path], stdout=subprocess.PIPE , stderr=subprocess.PIPE)
        self.yang_dom = ET.fromstring(result.stdout)
        self.add_params = {}
        self.recursive_read_additional_params(self.provider + '-' + self.solution + '-' + self.service_type + '-extensions')

    def recursive_read_additional_params(self, group_name):
        grouping_dom = self.yang_dom.find('.//yang:grouping[@name="'+group_name+'"]', self.namespaces)
        log.debug(grouping_dom)
        for ele_dom in grouping_dom.getchildren():
            log.debug(ele_dom.tag)
            if ele_dom.tag == '{'+self.namespaces['yang']+'}uses':
                log.debug("additional Param : " +ele_dom.attrib['name'])
                self.recursive_read_additional_params(ele_dom.attrib['name'])
            elif ele_dom.tag == '{'+self.namespaces['yang']+'}leaf':
                key = ele_dom.attrib['name']
                self.add_params[key] = ''

    def create_deployment(self):
        """

        :return:
        """

        #Create deployment file
        self.root_deployment = self.build_tree('config', self.namespaces['config'])
        deployment_rmno_ele = ET.SubElement(self.root_deployment, 'rmno')
        deployment_rmno_ele.set("xmlns", self.namespaces['e2e'])
        nwserv_ele = ET.SubElement(deployment_rmno_ele, 'network-service')
        deployment_ele = ET.SubElement(nwserv_ele, 'deployment')

        # Add elements in deployment

        name_ele = ET.SubElement(deployment_ele, 'name')
        name_ele.text = self.provider + "-" + self.solution + "-" + self.service_type + "-deployment"

        type_ele = ET.SubElement(deployment_ele, 'type')
        type_ele.text = self.provider + "-" + self.solution + "-" + self.service_type

        descriptor_ele = ET.SubElement(deployment_ele, 'descriptor')
        descriptor_ele.text = self.provider + "-" + self.solution + "-" + self.service_type + "-descriptor"

        location_ele = ET.SubElement(deployment_ele, 'location')
        pod_ele  = ET.SubElement(location_ele, 'pod')
        pod_ele.text = self.pod

        domain_ele = ET.SubElement(deployment_ele, 'domain')
        domain_ele.text = self.domain

        nf_ele = ET.SubElement(deployment_ele, 'network-function')
        nf_ele_name = ET.SubElement(nf_ele, 'name')
        nf_ele_name.text = self.provider + "-" + self.solution + "-" + self.service_type + "-nf"
        nf_type_ele = ET.SubElement(nf_ele, 'type')
        nf_type_ele.text = self.provider + "-" + self.solution + "-" + self.service_type
        nf_project_ele = ET.SubElement(nf_ele, 'project')
        nf_project_ele.text = self.project
        nf_inslevel_ele = ET.SubElement(nf_ele, 'instantiation-level')
        nf_inslevel_ele.text = 'default'
        nf_depflavor_ele = ET.SubElement(nf_ele, 'deployment-flavor')
        nf_depflavor_ele.text = 'default'

        self.read_additional_params()
        log.debug(self.add_params)
        add_params_ele = ET.SubElement(nf_ele, self.provider + '-' + self.solution + '-' + self.service_type)
        for key in self.add_params.keys():
            param_ele = ET.SubElement(add_params_ele, key)
            param_ele.text = self.add_params[key]

        #Create deployment networks

        self.create_deployment_networks(nf_ele)
        self.create_deployment_units(nf_ele)

        # Create pretty network
        deployment_str = ET.tostring(self.root_deployment, 'utf-8')
        self.deployment_dom = parseString(deployment_str)
        self.output(self.deployment_dom, 'deployment.xml')

    def create_descriptor_networks(self, rfs_ele):
        """

        :param rfs_ele:
        :return:
        """
        network_list = self.read_elem(self.vnfd_dom, ".//v:ext-cpd")
        for network in network_list:
            network_ele = ET.SubElement(rfs_ele, 'network')
            type_ele = ET.SubElement(network_ele, 'type')
            type_ele.text = network.find('./v:id',self.namespaces).text
            extent_ele = ET.SubElement(network_ele, 'extent')
            extent_ele.text = 'external'

    def create_deployment_networks(self, rfs_ele):
        """

        :param rfs_ele:
        :return:
        """
        network_list = self.read_elem(self.vnfd_dom, ".//v:ext-cpd")
        for network in network_list:
            network_ele = ET.SubElement(rfs_ele, 'network')
            type_ele = ET.SubElement(network_ele, 'type')
            type_ele.text = network.find('./v:id', self.namespaces).text
            extent_ele = ET.SubElement(network_ele, 'extent')
            extent_ele.text = 'external'
            external_network_ele = ET.SubElement(network_ele, 'external-network')
            external_network_ele.text = ''
            external_subnet_ele = ET.SubElement(network_ele, 'external-subnet')
            external_subnet_ele.text = ''

    def create_descriptor_units(self, nf_ele):
        """

        :param rfs_ele:
        :return:
        """
        unit_list = self.read_elem(self.vnfd_dom, ".//v:vdu")
        for unit in unit_list:
            unit_ele = ET.SubElement(nf_ele, 'unit')

            #Add type
            type_ele = ET.SubElement(unit_ele, 'type')
            type_ele.text = unit.find('./v:id', self.namespaces).text

            #Add flavor
            flavor_ele = ET.SubElement(unit_ele, 'flavor')
            flavor_ele.text = '<flavorname>'

            #Add image
            image_ele = ET.SubElement(unit_ele, 'image')
            image_ele.text = '<imagename>'

            #Add connection points
            self.add_descriptor_cps(unit_ele, unit)

    def create_deployment_units(self, nf_ele):
        """

        :param rfs_ele:
        :return:
        """
        unit_list = self.read_elem(self.vnfd_dom, ".//v:vdu")
        for unit in unit_list:
            unit_ele = ET.SubElement(nf_ele, 'unit')

            # Add hostname
            hostname_ele = ET.SubElement(unit_ele, 'hostname')
            hostname_ele.text = ''

            #Add type
            type_ele = ET.SubElement(unit_ele, 'type')
            type_ele.text = unit.find('./v:id', self.namespaces).text

            #Add connection points
            self.add_deployment_cps(unit_ele, unit)

    def add_descriptor_cps(self, unit_ele , vnfd_unit):
        """

        :param unit_ele:
        :param rfs_unit:
        :return:
        """
        cp_list = self.read_elem(vnfd_unit, ".//v:int-cpd")
        for cp in cp_list:
            cp_ele = ET.SubElement(unit_ele, 'connection-point')

            # Add name
            name_ele = ET.SubElement(cp_ele, 'name')
            name_ele.text = cp.find('./v:id', self.namespaces).text

            # Add network
            network_ele = ET.SubElement(cp_ele, 'network')
            network_type = self.network_map[cp.find('.//v:int-virtual-link-desc', self.namespaces).text]
            network_ele.text = network_type

    def add_deployment_cps(self, unit_ele , vnfd_unit):
        """

        :param unit_ele:
        :param rfs_unit:
        :return:
        """
        cp_list = self.read_elem(vnfd_unit, ".//v:int-cpd")

        for cp in cp_list:
            cp_ele = ET.SubElement(unit_ele, 'connection-point')

            # Add name
            name_ele = ET.SubElement(cp_ele, 'name')
            name_ele.text = cp.find('./v:id', self.namespaces).text

            # Add ip
            ip_ele = ET.SubElement(cp_ele, 'ip')
            ip_ele.text = ''

            # Add vip layer-protocol
            vip_ele = ET.SubElement(cp_ele, 'vip')
            ip_type = cp.find('./v:layer-protocol', self.namespaces).text
            if ip_type == 'ipv6':
                vip_ele.text = "::/64"
            else:
                vip_ele.text = "0.0.0.0/0"

            # Add subnet
            subnet_ele = ET.SubElement(cp_ele, 'subnet')
            subnet_ele.text = ''

    def build_tree(self, root , namespace):
        rmno_Ele = ET.Element(root)
        if namespace:
            rmno_Ele.set("xmlns", namespace)
        return rmno_Ele

    def parseXML(self, file):
        f = open(file, 'rb')
        file_read = f.read()
        root = ET.fromstring(file_read)
        return root

    def read_elem(self, xml, path):
        ele = xml.findall(path,self.namespaces)
        return ele

    def output(self, root , file):
        # There might be better methods to properly indent a file
        with open(file, 'w') as f:
            root.writexml(writer=f, encoding='UTF-8', newl='\n', addindent='\t')
        with open(file, 'r') as f:
            file_lines = f.readlines()
        with open(file, 'w') as f:
            newfile_lines = ""
            for line in file_lines:
                if line.isspace() is False:
                    newfile_lines = newfile_lines + line
            f.write(newfile_lines)

def setup_logger(log_level=logging.INFO):
    log_format = "%(levelname)s - %(message)s"
    log_folder = "logs"
    log_filename = log_folder + "/e2egenerator.log"
    # Ensure log folder exists
    if not os.path.exists(log_filename):
        os.mkdir(log_folder)

    logging.basicConfig(level=log_level, filename=log_filename, format=log_format)
    console = logging.StreamHandler()
    console.setLevel(log_level)
    console.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(console)

if __name__ == "__main__":
    e2egenerator()


# This file is part of DroidCarve.
#
# Copyright (C) 2015, Dario Incalza <dario.incalza at gmail.com>
# All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os, argparse, fnmatch, utils
from cmd import Cmd
from subprocess import call
import hashlib

from xml.dom import minidom
from axmlparserpy.axmlprinter import AXMLPrinter
import xml.dom.minidom
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters.terminal256 import Terminal256Formatter


__author__ = 'Dario Incalza <dario.incalza@gmail.com>'

BAKSMALI_PATH = os.getcwd() + "/bin/baksmali.jar"
APK_FILE = ""
CACHE_PATH_SUFFIX = "/cache/"
UNZIPPED_PATH_SUFFIX = "/unzipped/"


class CodeParser():

    def __init__(self, code_path):
        self.code_path = code_path

    '''
    Extract class name from a smali source line. Every class name is represented
    as a classdescriptor that starts zith 'L' and ends with ';'.
    '''

    def extract_class_name(self, class_line):
        for el in class_line.split(" "):
            if el.startswith("L") and el.endswith(";"):
                return el

    def start(self):
        for subdir, dirs, files in os.walk(self.code_path):
            for file in files:
                full_path = os.path.join(subdir, file)
                with open(full_path, 'r') as f:
                    continue_loop = True;
                    for line in f:
                        if line.startswith(".class"):
                            class_line = line.strip("\n")  # extract the class line; always first line
                            class_name = self.extract_class_name(class_line)  # extract the class descriptor
                            # print class_name

                        # if line.lstrip().startswith("const-string"):
                        # print line

                    if not continue_loop:
                        continue

class AndroidManifestParser():

    def __init__(self, manifest_xml_file):
        self.manifest = manifest_xml_file
        self.permissions = []

    def start(self):
        ap = AXMLPrinter(open(self.manifest, 'rb').read())
        buff = minidom.parseString(ap.getBuff()).toxml()
        xml_code = xml.dom.minidom.parseString(buff.rstrip())  # or xml.dom.minidom.parseString(xml_string)
        pretty_xml_as_string = xml_code.toprettyxml()
        for line in pretty_xml_as_string.split("\n"):
            if not line.find("<uses-permission") == -1:
                self.permissions.append(line.split("\"")[1])

    def get_permissions(self):
        return self.permissions

class FileParser():

    def __init__(self, files_path):
        self.files_path = files_path
        self.signature_files = []
        self.xml_files = []

    def start(self):
        for subdir, dirs, files in os.walk(self.files_path):
            for file in files:
                full_path = os.path.join(subdir, file)
                if file.endswith("RSA"):
                    self.signature_files.append(full_path)
                if file.endswith("xml"):
                    self.xml_files.append(full_path)

    def get_signature_files(self):
        return self.signature_files

    def get_xml_files(self):
        return self.xml_files

    def get_xml(self, name):
        for xml_file in self.xml_files:
            if xml_file.endswith(name):
                return xml_file


class DroidCarve(Cmd):

    def __init__(self, apk_file, cache_path, unzip_path, from_cache=False):
        Cmd.__init__(self)
        self.prompt = "DC $> "
        self.apk_file = str(apk_file)
        self.cache_path = cache_path
        self.unzip_path = unzip_path
        self.file_parser = FileParser(unzip_path)
        self.code_parser = CodeParser(cache_path)
        self.from_cache = from_cache
        self.analysis = False

    def do_quit(self, arg):
        print 'Exiting, cheers!'
        exit(0)

    def do_exit(self, arg):
        self.do_quit(arg)

    def do_unzip(self, destination):
        """
        unzip

        Unzip the Android application.

        unzip [destination]

        Unzip the Android application to a given destination.
        """
        self.unzip_apk(destination)



    def do_analyze(self, arg):
        """
        analyze

        Analyze the Android application. Unzip and parse the files, disassemble and process Smali bytecode.
        This step is mandatory before using almost any of the other processing steps.
        """
        if not self.from_cache:

            self.disassemble_apk()
        else:
            print "Start analysis from cache ..."

        print "Analyzing disassembled code ..."
        self.code_parser.start()
        print "Analyzing unzipped files ..."
        self.file_parser.start()

        print "Analyzing AndroidManifest.xml ..."
        self.manifest_parser = AndroidManifestParser(self.file_parser.get_xml("/AndroidManifest.xml"))
        self.manifest_parser.start()
        self.analysis = True
        print "Analyzing ... Done"

    def do_signature(self, arg):
        """
        signature

        Print the application certificate in a human readable format.
        This requires that the Java keytool binary is installed and in PATH.

        In case no signature is found, make sure the application is signed and the 'analyze' is executed.
        """
        files = self.file_parser.get_signature_files()

        if len(files) == 0:
            print "No signature files found, see 'help signature'."
            return

        for f in files:
            print "Found signature file : " + f
            call(["keytool", "-printcert", "-file", f])

    def do_statistics(self, arg):

        if not self.analysis:
            print "Please analyze the APK before running this command."
            return

        onlyfiles = len(fnmatch.filter(os.listdir(self.cache_path), '*.smali'))
        print 'Disassembled classes = ' + str(onlyfiles)
        print 'Permissions          = ' + str(len(self.manifest_parser.get_permissions()))

    def do_manifest(self, option):
        """
        manifest
        XML dump of the AndroidManifest.xml file.

        manifest p
        List of extracted permissions.
        """
        xml_file = self.file_parser.get_xml("/AndroidManifest.xml")

        if xml_file is None:
            print "AndroidManifest.xml was not found."
            return
        if not option:
            ap = AXMLPrinter(open(xml_file, 'rb').read())
            buff = minidom.parseString(ap.getBuff()).toxml()
            xml_code = xml.dom.minidom.parseString(buff.rstrip())  # or xml.dom.minidom.parseString(xml_string)
            pretty_xml_as_string = xml_code.toprettyxml()
            lexer = get_lexer_by_name("xml", stripall=True)
            formatter = Terminal256Formatter()
            print (highlight(pretty_xml_as_string.rstrip(), lexer, formatter))

        else:
            if option == "p":
                for perm in self.manifest_parser.get_permissions():
                    if not perm.startswith("android."):
                        utils.print_purple("\t"+perm)
                    else:
                        print "\t"+perm

        return


    '''
    Use baksmali to disassemble the APK.
    '''

    def disassemble_apk(self):
        print "Disassembling APK ..."
        call(["java", "-jar", BAKSMALI_PATH, "d", self.apk_file, "-o", self.cache_path])

    def unzip_apk(self, destination = None):
        if destination is None or destination == "":
            print "Unzipping APK ..."
            call(["unzip", self.apk_file, "-d", self.unzip_path])
        else:
            print "Unzipping APK to %s ... " % destination
            call(["unzip", self.apk_file, "-d", destination])

    def extract_strings(self):
        return


'''
Parse the arguments and assign global variables that we will be using throughout the tool.
'''


def parse_arguments():
    parser = argparse.ArgumentParser(
        description='DroidCarve is capable of analyzing an Android APK file and automate certain reverse engineering tasks. For a full list of features, please see the help function.')
    parser.add_argument('-a', '--apk', type=str, help='APK file to analyze',
                        required=True)

    args = parser.parse_args()

    global APK_FILE
    APK_FILE = args.apk

    check_apk_file()


def generate_cache():
    hash = hashlib.sha1(open(APK_FILE, 'rb').read()).hexdigest();
    print "Hash of APK file = " + hash
    CACHE_PATH = os.getcwd() + "/" + hash + CACHE_PATH_SUFFIX
    UNZIPPED_PATH = os.getcwd() + "/" + hash + UNZIPPED_PATH_SUFFIX

    if os.path.exists(CACHE_PATH) or os.path.exists(UNZIPPED_PATH):
        choice = ask_question("A cached version of the application has been found, start from a fresh cache?",
                              ["Yes", "No"])
        if choice == "No":
            return CACHE_PATH, UNZIPPED_PATH, True
        else:
            return CACHE_PATH, UNZIPPED_PATH, False

    if not os.path.exists(CACHE_PATH):
        os.makedirs(CACHE_PATH)

    if not os.path.exists(UNZIPPED_PATH):
        os.makedirs(UNZIPPED_PATH)

    return CACHE_PATH, UNZIPPED_PATH, False


def ask_question(question, answers):
    while (True):
        print question
        for a in answers:
            print "- " + a
        choice = raw_input("Choice: ")
        if choice in answers:
            return choice


'''
Sanity check to see if a valid APK file is specified.

TODO: implement more specific check to see if it is a valid APK file
'''


def check_apk_file():
    if APK_FILE == "" or not os.path.isfile(APK_FILE):
        print "No APK file specified, exiting."
        exit(3)


'''
Check if there is a baksmali tool.
'''


def has_baksmali():
    return os.path.isfile(BAKSMALI_PATH)


def main():
    parse_arguments()
    (CACHE_PATH, UNZIPPED_PATH, FROM_CACHE) = generate_cache()
    droidcarve = DroidCarve(APK_FILE, CACHE_PATH, UNZIPPED_PATH, FROM_CACHE)
    droidcarve.cmdloop()


if __name__ == "__main__":

    if not has_baksmali():
        print "No baksmali.jar found in " + BAKSMALI_PATH
        exit(2)

    main()

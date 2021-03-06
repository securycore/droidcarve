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

import os, argparse, fnmatch, utils,re
from cmd import Cmd
from subprocess import call
import hashlib
from parsers import FileParser, AndroidManifestParser, CodeParser
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters.terminal256 import Terminal256Formatter

__author__ = 'Dario Incalza <dario.incalza@gmail.com>'

BAKSMALI_PATH = os.getcwd() + "/bin/baksmali.jar"
APK_FILE = ""
CACHE_PATH_SUFFIX = "/cache/"
UNZIPPED_PATH_SUFFIX = "/unzipped/"


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
        self.excludes = []

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

    def do_exclude(self, arg):

        if not arg:
            print "Exclusion list:"
            print self.excludes
            return

        args = arg.split(" ")

        if args[0] == "clear":
            self.excludes = []
            utils.print_blue("Exclusion list cleared.")
        elif utils.is_valid_regex(args[0]):
            self.excludes.append(args[0])
        else:
            utils.print_red("No valid exclusion regex provided.")

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

        print 'Disassembled classes = ' + str(len(self.code_parser.get_classes()))
        print 'Permissions          = ' + str(len(self.manifest_parser.get_permissions()))

    def do_classes(self, arg):
        args = arg.split(" ")
        classes = self.code_parser.get_classes()

        if not arg:
            utils.print_blue("Found %s classes" % str(len(classes)))

        if args[0] == "find":
            if len(args) == 1:
                utils.print_red("Please specify a regex to match a class name.")
            else:
                regex = args[1]
                if utils.is_valid_regex(regex):
                    pattern = re.compile(regex)
                    for clazz in classes:
                        if pattern.match(clazz["name"]) and not self.is_excluded(clazz["name"]):
                            print clazz["name"]
                else:
                    utils.print_red("Invalid regex.")


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
            xml_source = self.manifest_parser.get_xml()
            lexer = get_lexer_by_name("xml", stripall=True)
            formatter = Terminal256Formatter()
            print (highlight(xml_source.rstrip(), lexer, formatter))

        else:
            if option == "p":
                for perm in self.manifest_parser.get_permissions():
                    if not perm.startswith("android."):
                        utils.print_purple("\t" + perm)
                    else:
                        print "\t" + perm

        return

    '''
    Use baksmali to disassemble the APK.
    '''

    def disassemble_apk(self):
        print "Disassembling APK ..."
        call(["java", "-jar", BAKSMALI_PATH, "d", self.apk_file, "-o", self.cache_path])

    def unzip_apk(self, destination=None):
        if destination is None or destination == "":
            print "Unzipping APK ..."
            call(["unzip", self.apk_file, "-d", self.unzip_path])
        else:
            print "Unzipping APK to %s ... " % destination
            call(["unzip", self.apk_file, "-d", destination])

    def extract_strings(self):
        return

    def is_excluded(self, candidate):
        for regex in self.excludes:
            pattern = re.compile(regex)
            if pattern.match(candidate):
                return True

        return False


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

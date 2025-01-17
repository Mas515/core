"""
java.py - CellProfiler-specific JVM utilities
"""

import logging
import os
import sys
import threading

import javabridge
import prokaryote
from javabridge._javabridge import get_vm

import cellprofiler_core.preferences


JAVA_STARTED = False

LOGGER = logging.getLogger(__name__)


def get_jars():
    """
    Get the final list of JAR files passed to javabridge
    """

    class_path = []
    if "CLASSPATH" in os.environ:
        class_path += os.environ["CLASSPATH"].split(os.pathsep)
        LOGGER.debug(
            "Adding Java class path from environment variable, " "CLASSPATH" ""
        )
        LOGGER.debug("    CLASSPATH=" + os.environ["CLASSPATH"])

    pathname = os.path.dirname(prokaryote.__file__)

    jar_files = [
        os.path.join(pathname, f)
        for f in os.listdir(pathname)
        if f.lower().endswith(".jar")
    ]

    class_path += javabridge.JARS + jar_files

    if sys.platform.startswith("win") and not hasattr(sys, "frozen"):
        # Have to find tools.jar
        from javabridge.locate import find_jdk

        jdk_path = find_jdk()
        if jdk_path is not None:
            tools_jar = os.path.join(jdk_path, "lib", "tools.jar")
            class_path.append(tools_jar)
        else:
            LOGGER.warning("Failed to find tools.jar")
    return class_path


def find_logback_xml():
    """Find the location of the logback.xml file for Java logging config

    Paths to search are the current directory, the utilities directory
    and ../../java/src/main/resources
    """
    paths = [
        os.curdir,
        os.path.dirname(__file__),
        os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "java",
            "src",
            "main",
            "resources",
        ),
    ]
    for path in paths:
        target = os.path.join(path, "logback.xml")
        if os.path.isfile(target):
            return target


def start_java():
    """Start CellProfiler's JVM via Javabridge

    JVM parameters are harvested from preferences and
    the environment variables:

    CP_JDWP_PORT - port # for debugging Java within the JVM
    cpprefs.get_awt_headless() - controls java.awt.headless to prevent
        awt from being invoked
    """
    thread_id = threading.get_ident()
    if get_vm().is_active():
        javabridge.attach()
        return
    LOGGER.info("Initializing Java Virtual Machine")
    args = [
        "-Dloci.bioformats.loaded=true",
        "-Djava.util.prefs.PreferencesFactory="
        + "org.cellprofiler.headlesspreferences.HeadlessPreferencesFactory",
    ]

    logback_path = find_logback_xml()

    if logback_path is not None:
        if sys.platform.startswith("win"):
            logback_path = logback_path.replace("\\", "/")
            if logback_path[1] == ":":
                # \\localhost\x$ is same as x:
                logback_path = "//localhost/" + logback_path[0] + "$" + logback_path[2:]
        args.append("-Dlogback.configurationFile=%s" % logback_path)

    class_path = get_jars()
    awt_headless = cellprofiler_core.preferences.get_awt_headless()
    if awt_headless:
        LOGGER.debug("JVM will be started with AWT in headless mode")
        args.append("-Djava.awt.headless=true")

    if "CP_JDWP_PORT" in os.environ:
        args.append(
            (
                "-agentlib:jdwp=transport=dt_socket,address=127.0.0.1:%s"
                ",server=y,suspend=n"
            )
            % os.environ["CP_JDWP_PORT"]
        )
    javabridge.start_vm(args=args, class_path=class_path)
    #
    # Enable Bio-Formats directory cacheing
    #
    javabridge.attach()
    c_location = javabridge.JClassWrapper("loci.common.Location")
    c_location.cacheDirectoryListings(True)
    LOGGER.debug("Enabled Bio-formats directory cacheing")
    global JAVA_STARTED
    JAVA_STARTED = True


def stop_java():
    LOGGER.info("Shutting down Java Virtual Machine")
    javabridge.kill_vm()

# DrNED Examiner

A Doctor's bag of tools for examining & diagnosing your NSO NEDs

# Purpose

DrNED Examiner helps you with testing your NED or device using the DrNED
package. Using the tool's actions you can:

 * set up the environment (or at least get help with that)
 * save/import device configurations (or *states*) to be used later in tests
 * invoke DrNED tests that verify if the device transitions between those
   states smoothly
 * make DrNED generate reports on how well the state transitions cover the
   device model
 * log tools allow reviewing the communication between NSO and the device,
   debugging situations when the device configuration violates the device's
   YANG contract, and when testing transactionality properties

## Prerequisites

The tool is supported to run on Python 3.5 or newer.  It is known to run on
Python 2.7, but this is no longer actively maintained.

Apart form that, several Python packages are needed: `pytest`, `pexpect`, and
`lxml`; `pytest` version needs to be at least 3.0.  There are several options
how to install these packages:

1. Quite likely, they are available in your system distribution repositories,
   for example in Ubuntu they can be installed like

        $ sudo apt install python3-pytest python3-lxml python3-pexpect
       
   Note that these are packages that run with Python 3.  If you happen to be
   restricted to Python 2, install `python-pytest`, `python-lxm`, and
   `python-pexpect`.

   Care must be taken though if the `pytest` version meets requirements,
   namely on Ubuntu 16.04 it does not:

        $ apt show python3-pytest
        ...
        Version: 2.8.7-4

2. All three packages are published through the Python Package Inventory and
   can be installed from there; it requires that `pip` is installed (on Ubuntu
   as `python-pip`).  The requirements are enumerated in `requirements.txt`
   file that can be provided to pip:

        $ pip install --user -r requirements.txt

   or for a system-wide installation

        $ sudo pip install -r requirements.txt
       
 3. If it is required that the packages are not only user-specific but also
    project-specific, it is possible to use so called python virtual
    environments.  Using them can be greatly simplified by the tool `pipenv`
    which needs to be installed first (globally or per user):
    
        $ pip install --user pipenv
       
    or

        $ sudo pip install pipenv
       
    Have a look at the file `Pipfile` - it tells `pipenv` what packages and in
    what versions need to be installed for the project environment.  The
    environment can be created with required packages using
    
        $ pipenv install
       
    Now, so as to enter the environment, run
    
        $ pipenv shell

    This starts a new OS shell with paths pointing to the installed packages.
    NSO or at least its Python VM should be started from this shell (see also
    the command `pipenv run` for an alternative method).

DrNED Examiner and all its prerequisites is installed in this
[NSO-interoperability testing image](https://github.com/jojohans/NSO-Interop).

## What it can do

Apart from this file that presents an overview of the tool's capabilities,
the main documentation is the drned-xmnr.yang file, where each command is 
described.

Before working with this tool you need a device configured in NSO and
connected.  For doing that you may want to use the
[Pioneer](https://github.com/NSO-developer/pioneer) tool.

DrNED Examiner has two configuration parameters: `/drned-xmnr/xmnr-directory`
and `/drned-xmnr/drned-directory`.  The former sets the location where the tool
stores its data and defaults to `/tmp/xmnr`; the latter default to the built-in
DrNED version that come with this NSO package. For using a different version of
DrNED, you can point to a different DrNED installation directory than the default
one.  (As an alternative, set the environment variable `DRNED` before starting
NSO and configure the drned-directory to `env`)

The following sections briefly describe actions implemented by the tool.  All
actions have only a textual output with fields `success` (populated if the
action completed successfully), `failure` and `error` (the latter may contain
more details about the problem in case of failure).

 * **Setup**

    Run the action `drned-xmnr/setup/setup-xmnr` to prepare and populate the data
    directory.  This is needed as the first action before any further work with the
    tool, or to clean up the directory (with parameter `overwrite`).

 * **Device states**

    Once set up, you need to prepare device states.  A device state is pretty much
    a device configuration, so you can configure the device and record its state,
    or you can directly import saved device configurations from various formats.

 * **Transitions**

    The main purpose of this tool is to help you verify that the device under test
    transitions smoothly between states - you can move from state to state, or walk
    several states at once, or explore all possible transitions between several
    states.  The tool invokes DrNED for all these tasks and uses its capabilities
    to detect auto-configuration issues, problems with rollback, etc.

 * **Coverage**

    DrNED is capable of reporting how big part of the device model your tests have
    covered; the tool implements a simple wrapper around this DrNED capability, 
    including status data providing the coverage report in a structured form.

## Debugging issues

Your main tools for debugging issues are logs. 

  * First you have the DrNED log that you control the filtering of via
    `/drned-xmnr/log-detail/cli` and output via `/drned-xmnr/log-detail/redirect`. 
    In an automated test environment, you would normally set the cli detail to 
    `drned-overview` to get the DrNED reports, and you would likely want to
    redirect the output to a file. When debugging issues, you may want to remove
    the redirect to file and output everything to your CLI console with the 
    log-detail set to `all`. 
  * Equally useful is the ncs-python-vm-drned-xmnr.log that you control through
    `/python-vm/logging/vm-levels/drned-xmnr/level/`. To maximize the information
    captured by this log, set to `level-debug`. The log can be found in the
    ncs-python-vm-drned-xmnr.log.
  * It can often be helpful to look into the detailed trace of the communication
    with the (virtual/physical) device. Set the `/devices/device/<my-device>/trace`
    to `pretty` or `raw` to capture the communication between the NED and the device.
  * For other issues detected and reported by NSO, refer to the NSO administration
    guide for troubleshooting adivce. 

## Common problems

DrNED uses `py.test` as a tool for running tests.  `py.test` cannot process
correctly command line arguments containing hyphens (`-`); DrNED works around
that by translating hyphens to tildes (`~`) in file names (but not in device
names), so it should be possible to use hyphens in state names (again: not in
device names), but due to the workaround, it is not possible to use tildes
there.

## Testing the testing tool

If you intend to modify or extend the tool, you may want to test your changes -
please refer to the test [README](test/README.md); note that the tests add few
additional prerequisities, see there.

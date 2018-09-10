# DrNED Examiner - A Doctor's bag of tools for examining & diagnosing your
NSO NEDs

DrNED Examiner helps you with testing your NED or device using the DrNED
package. Using the tool's actions you can:

 * set up the environment (or at least help with that)
 * save/import device configurations (or *states*) to be used later in tests
 * invoke DrNED tests that verify if the device transitions between those
   states smoothly
 * make DrNED generate reports on how well the state transitions cover the
   device model.
 * log tools allow reviewing the communication between NSO and the device,
   debugging situations when the device configuration violates the device's
   YANG contract, and when testing transactionality properties.

## Prerequisites

The only prerequisite is the DrNED dependencies, in particular `pytest`,
`pexpect`, and `lxml`.

## What it can do

We describe an overview of the tool's capabilities; for more details, see the
package only YANG file.

Before working with this tool you need a device configured in NSO and
connected.  For doing that you may want to use the
[Pioneer](https://github.com/NSO-developer/pioneer) tool.

DrNED Examiner has two configuration parameters: `/drned-xmnr/xmnr-directory`
and `/drned-xmnr/drned-directory`.  The former sets the location where the tool
stores its data and defaults to `/tmp/xmnr`; the latter default to the built-in
DrNED version that come with this NSO package. For using a different version of
DrNED, you can point to a different DrNED installation directory than the default
one.  (As an alternative, set the environment variable `DRNED` before starting
NSO and set the drned-directory to `env`)

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
    covered; the tool implements a simple wrapper around this capability, including
    a status data providing the coverage report in a structured form.

## Debugging issues

Your main tools for debugging issues are logs. First you have the DrNED log that
you control the filtering of via `/drned-xmnr/log-detail/cli`. Set it to `all`
when debugging issues. Equally useful is the ncs-python-vm-drned-xmnr.log that you
control through `/python-vm/logging/vm-levels/drned-xmnr/level/`. To maximize the
information captured by this log, set to `level-debug`. The log can be found in
the ncs-python-vm-drned-xmnr.log. It can often be helpful to look into the
detailed trace of the communication with the (virtual) device. Set the
`/devices/device/<my-device>/trace` to `pretty` or `raw` to capture the
communication between the NED and the device.

## Common problems

DrNED uses `py.test` as a tool for running tests.  `py.test` cannot process
correctly command line arguments containing hyphens (`-`); DrNED works around
that by translating hyphens to tildes (`~`) in file names (but not in device
names), so it should be possible to use hyphens in state names (again: not in
device names), but due to the workaround, it is not possible to use tildes
there.

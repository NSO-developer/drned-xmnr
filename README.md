# DrNED Examiner

DrNED Examiner helps you with testing your NED or device using the DrNED
package.  Using the tool's actions you can:

 * set up the environment (or at least help with that)
 * save device configurations (or *states*) to be used later in tests
 * invoke DrNED tests that verify if the device transitions between those
   states smoothly
 * make DrNED generate reports on how well the state transitions cover the
   device model.

## Prerequisites

The only prerequisite is DrNED itself; you can clone it from
<ssh://git@stash.tail-f.com/ned/drned>.  Of course, DrNED has its own set of
dependencies, in particular `pytest`, `pexpect`, and `lxml`.

## What it can do

We describe an overview of the tool's capabilities; for more details, see the
package only YANG file.

Before working with this tool you need a device configured in NSO and
connected.  For doing that you may want to use the
[Pioneer](https://github.com/NSO-developer/pioneer) tool.

DrNED Examiner has two configuration parameters: `/drned-xmnr/xmnr-directory`
and `/drned-xmnr/drned-directory`.  The former sets the location where the tool
stores its data and defaults to `/tmp/xmnr`; the latter has no default and
needs to point to the DrNED installation directory.  (As an alternative, set
the environment variable `DRNED` before starting NSO.)

The following sections briefly describe actions implemented by the tool.  All
actions have only a textual output with fields `success` (populated if the
action completed successfully), `failure` and `error` (the latter may contain
more details about the problem in case of failure).

### Setup

Run the action `drned-xmnr/setup/setup-xmnr` to prepare and populate the data
directory.  This is needed as the first action before any further work with the
tool, or to clean up the directory (with parameter `overwrite`).

### Device states

Once set up, you need to prepare device states.  A device state is pretty much
a device configuration, so you can configure the device and record its state,
or you can directly import saved device configurations (provided they are in
the Cisco-CLI format).

### Transitions

The main purpose of this tool is to help you verify that the device under test
transitions smoothly between states - you can move from state to state, or walk
several states at once, or explore all possible transitions between several
states.  The tool invokes DrNED for all these tasks and uses its capabilities
to detect auto-configuration issues, problems with rollback, etc.

### Coverage

DrNED is capable of reporting how big part of the device model your tests have
covered; the tool implements a simple wrapper around this capability, including
a status data providing the coverage report in a structured form.

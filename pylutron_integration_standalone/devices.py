# Notes:
#
# Integration ids for devices appear to be stored on the devices (or at least if you
# wipe the flash on the NWK via #RESET,2 then they are not cleared).  You cannot
# set an integration id for a nonexistent device.  Setting an integration id for
# a device that does exist is quite slow.
#
# Integration ids for *outputs* seem to be rather different.  They can be set quite
# quickly, but only for devices that actually exist, but you can integration ids
# for absurdly large output numbers that do not actually exist.  Additionally,
# #RESET,2 seems to erase all the output integration ids.
#
# My hypotheses is that output integration IDs are translated in the NWK
# to/from device commands and states.  For example, Grafik Eye has documented
# DEVICE component numbers for up to 24 zone controllers.  Monitoring shows
# ~DEVICE if no integrationid is assigned and ~OUTPUT if an integration id
# is assigned.  This mapping might not even care about the device type --
# it might be the case that action 14 (light level) always maps to OUTPUT
# action 1 (light level), and that the component number maps straight through.
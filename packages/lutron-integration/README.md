# What is this? #

lutron_integration is a a client library for the Lutron Integration Protocol.
This is a protocol used by a number of different Lutron products, documented here:

https://assets.lutron.com/a/documents/040249.pdf

lutron_integration is intended to be able to support all dialects of the protocol,
but it is currently primarily targetted at the "QS Standalone" dialect.  Other dialects
are barely, if at all, implemented.

If you want to set up a QS Standalone system, you need a Lutron [QSE-CI-NWK-E](https://assets.lutron.com/a/documents/369373_qse-ci-nwk-e_eng.pdf),
at least one other Lutron device (both to make it useful and to provide power), and some appropriate wire.
Lutron's devices are generally intended for professional installation, and they provide extensive
documentation on their website.

Programming your QSE-CI-NWK-E is outside the scope of this library, but it's fairly
easy to do over Telnet.  (In general, a skilled Lutron installer will install a QS
system and will install the QSE-CI-NWK-E as well if requested to do so.  They will program
the rest of the system (which requires no proprietary software for a standalone
system and can be done by following instructions in the manual), and they may or
may not program the QSE-CI-NWK-E.)  Integrating some other system, e,g, whatever
system uses this library, is the job of whoever sets up that system, i.e. you!

To set it up, you will need a computer that allows you to control its IP and subnet
settings and to set up an IP on the subnet 192.168.250.0/24, and you'll need to connect
to 192.168.250.1/24.  You can often fudge this by connecting to the same L2 network
that the QSE-CI-NWK-E is on, even via wifi, and adding a secondary address.

- On a Mac, the command resembles `sudo ifconfig en0 alias 192.168.250.2 255.255.255.0`
- On Linux, the command resembles `sudo ip addr add 192.168.250.2/24 dev eth0`
- On Windows, you can use the GUI, painfully.  I'm sure there is some way to do it via Powershell or ipconfig

Then you can telnet to 192.168.250.1 and configure a real IP address with
commands like `#ETHERNET,0,[IP address]` and `#ETHERNET,1,[subnet mask]` --
see [page 19][lip].  The QSE-CI-NWK-E does not appear to support DHCP at all,
and Lutron recommends using static addresses even for other dialects.  Or you can
use RS232.

lutron_integration presently has no dependencies at all outside the standard library,
and I would like to keep it that way unless there is a fairly compelling reason
to add a dependency.

# Usage #

Users of this library are responsible for connecting to the integration access point
on their own, which generally involves figuring out what IP address and TCP port
(hint: 23) to connect to and using `await asyncio.open_connection(address, port)`
or doing whatever incantation is appropriate on your platform to connect to a
serial port.

(Lots more to write here)

lutron_integration is fully async and very strongly respects the idea of
structured concurrency: it does not create tasks at all.  If you want the
library do so something, you call it.  If you are not actively calling it,
it does nothing!


[lip]: https://assets.lutron.com/a/documents/040249.pdf
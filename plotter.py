#!/usr/bin/env python2.6

from __future__ import print_function
import time
import subprocess

from twisted.internet import protocol, reactor

class Plotter(object):

    def __init__(self, filename, save_filename):
        self.filename = filename
        self.save_filename = save_filename

        self.current_data = {}
        self.last_data = {}
        self.last_dump = ''

        self.stable = False
        self.points_per_sec = 20 # update this when --generic changes!
        self.n_points = 0
        self.recorded_points = 0

        self.gnuplot = None
        self.plot = None
        self.null = open('/dev/null', 'w')

        # Truncate the data file
        with open(self.filename, 'w') as fp:
            fp.truncate()

    def __del__(self):
        if self.gnuplot is not None:
            self.write('quit')
            self.gnuplot.kill()
            print('Killed gnuplot')
            print('Recorded %d points in %d seconds' % (self.recorded_points, 
                    self.n_points / float(self.points_per_sec)))
        self.null.close()

    def setup_gnuplot(self, plot):
        if plot is None:
            # we're probably exiting
            return

        splot = 'splot "%s"' % self.filename
        for n, (title, values) in enumerate(plot):
            splot += ' using %s title "%s" with lines' % (values, title)
            if n + 1 != len(plot):
                splot += ', "%s"' % self.filename

        self.gnuplot = subprocess.Popen(['gnuplot'], stdin=subprocess.PIPE, 
                stdout=self.null, stderr=self.null)
        self.write(splot)
        print('Started gnuplot and recording data points...')

    def save(self):
        if self.gnuplot is not None:
            self.write('set term postscript eps enhanced')
            self.write('set output "%s"' % self.save_filename)
            self.replot()
            time.sleep(1) # give it 1 second to flush
            print('Saved graph to %s' % self.save_filename)

    def parse_data(self, fields, line):
        if line.count('\n') != 1:
            print('This line had more than one set of data in it, discarding')
            return False

        l = line.rstrip('\n').split(',')
        if len(l) != len(fields):
            print('Discarding corrupt line: should have had %d fields, '
                    'instead had %d' % (len(fields), len(l)))
            return False

        d = {}
        for n, k in enumerate(fields):
            d[k] = l[n]

        if d != self.current_data:
            self.last_data = dict(self.current_data) # copy
            self.current_data = dict(d)
            return True

        return False

    def dump(self, fields, plot):
        self.n_points += 1

        d = ''
        for f in fields:
            d += '%s ' % self.current_data[f]
        d.rstrip()
        d += '\n'

        # Wait 3 seconds for inputs to stablise
        if not self.stable and self.n_points / self.points_per_sec == 3:
            print('3 seconds elapsed, assuming inputs are stable')
            self.stable = True

        if d != self.last_dump and self.stable:
            self.recorded_points += 1
            self.last_dump = d
            with open(self.filename, 'a') as fp:
                fp.write(d)
            self.replot(plot)

    def write(self, data):
        if self.gnuplot is None:
            print('Tried to write() to gnuplot when it\'s not running!')
        else:
            self.gnuplot.stdin.write('%s\n' % data)
            self.gnuplot.stdin.flush()

    def replot(self, plot=None):
        if plot is not None and self.plot is None:
            self.plot = plot # XXX errrrg so hacky
        if self.gnuplot is None:
            self.setup_gnuplot(plot)
        self.write('replot')

class FGProtocol(protocol.Protocol):

    def connectionMade(self):
        peer = self.transport.getPeer()
        print('Connection from %s:%d' % (peer.host, peer.port))
        self.plotter = Plotter(self.factory.points_filename, 
                self.factory.save_filename)
        print('Waiting for inputs to stabilise...')

    def connectionLost(self, reason):
        print('Lost connection with client:', reason.getErrorMessage())
        self.plotter.save()

    def dataReceived(self, data):
        if self.plotter.parse_data(self.factory.ordered_keys, data):
            self.plotter.dump(self.factory.ordered_keys, self.factory.plot)

class FGFactory(protocol.Factory):

    protocol = FGProtocol

    def __init__(self, ordered_keys, plot, points_filename, save_filename):
        self.ordered_keys = ordered_keys
        self.plot = plot
        self.points_filename = points_filename
        self.save_filename = save_filename

def setup(listen_port, ordered_keys, plot, points_filename='pos.txt',
        save_filename='out.eps'):
    """Set up the plotting server and wait for a connection from FlightGear.
    When one arrives, gnuplot will be started ready to plot the given
    data points.

    `listen_port` is the TCP port to listen on for connections from FlightGear.

    `ordered_keys` is a list of the keys that we should expect from
    FlightGear. It should match the protocol.xml file's order and names.

    `plot` is a list of tuples in the form (title, fields) to plot on the
    graph.

    For example, if ordered_keys is:
        ['latitude', 'longitude', 'altitude']
    then (indexing from 1) the plot could look like:
        [('Flight path', '1:2:3')]

    The second value in the tuple should be in a valid "using x" syntax that
    gnuplot can recognise. This would plot field 1 (latitude) as x, field 2
    (longitude) as y, and field 3 (altitude) as z.

    `points_filename` is where the data points will be written to. The file
    will be truncated before starting. It typically have an extension of
    .txt or .dat.

    `save_filename` is the filename to write the generated PostScript graph
    to when quitting. It should have an extension of .eps.
    """

    f = protocol.Factory()
    reactor.listenTCP(listen_port, FGFactory(ordered_keys, plot,
            points_filename, save_filename))
    print('Listening on TCP port %d. Start FlightGear now with '
            '--generic argument:' % listen_port)
    print('`fgfs --generic=socket,out,20,localhost,%d,tcp,position`' 
            % listen_port)
    reactor.run()


# To plot position with ground elevation as a flight path
setup(5555, ['latitude-deg', 'longitude-deg', 'altitude-ft', 'ground-elev-ft'],
        [('Flight path', '1:2:3'), ('Ground elevation', '1:2:4')])

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
        fp = open(self.filename, 'w')
        fp.truncate()
        fp.close()

    def __del__(self):
        self.write('quit')
        self.gnuplot.kill()
        print('Killed gnuplot')

        self.null.close()
        print('Recorded %d points in %d seconds' % (self.recorded_points, 
                self.n_points / float(self.points_per_sec)))

    def setup_gnuplot(self, plot):
        splot = 'splot "%s"' % self.filename
        for n, (title, values) in enumerate(plot):
            splot += ' using %s title "%s" with lines' % (values, title)
            if n + 1 != len(plot):
                splot += ', "%s"' % self.filename

        self.gnuplot = subprocess.Popen(['gnuplot'], stdin=subprocess.PIPE, 
                stdout=self.null, stderr=self.null)
        self.write(splot)
        print('Started gnuplot')

    def save(self):
        self.write('set term postscript eps enhanced')
        self.write('set output "%s"' % self.save_filename)
        self.replot()
        time.sleep(1) # give it 1 second to flush
        print('Saved graph to %s' % self.save_filename)

    def parse_data(self, fields, line):
        if line.count('\n') != 1:
            print('This line had more than one set of data in it, discarding')
            return

        d = {}

        l = line.rstrip('\n').split(',')
        for n, k in enumerate(fields):
            d[k] = l[n]

        if d != self.current_data:
            self.last_data = dict(self.current_data) # copy
            self.current_data = dict(d)

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
            fp = open(self.filename, 'a')
            fp.write(d)
            fp.close()
            self.replot(plot)

    def write(self, data):
        if self.gnuplot is not None:
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
        print('Connection from client')
        self.plotter = Plotter(self.factory.points_filename, 
                self.factory.save_filename)

    def connectionLost(self, reason):
        print('Lost connection with client:', reason.getErrorMessage())
        self.plotter.save()

    def dataReceived(self, data):
        self.plotter.parse_data(self.factory.ordered_keys, data)
        self.plotter.dump(self.factory.ordered_keys, self.factory.plot)

class FGFactory(protocol.Factory):

    protocol = FGProtocol

    def __init__(self, ordered_keys, plot, points_filename, save_filename):
        self.ordered_keys = ordered_keys
        self.plot = plot
        self.points_filename = points_filename
        self.save_filename = save_filename

def setup(port, ordered_keys, plot, points_filename, save_filename):
    """`ordered_keys` is a list of the keys that we should expect from
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
    reactor.listenTCP(port, FGFactory(ordered_keys, plot, points_filename, 
            save_filename))
    reactor.run()

setup(5555, ['latitude-deg', 'longitude-deg', 'altitude-ft', 'ground-elev-ft'],
        [('Flight path', '1:2:3'), ('Ground elevation', '1:2:4')], 
        'pos.txt', 'out.eps')

#!/usr/bin/env python2.6

from __future__ import print_function
import time
import subprocess
import sys

from twisted.internet import protocol, reactor

class FGData(object):
    _keys = ['aileron', 'elevator', 'rudder', # flight controls
            'latitude-deg', 'longitude-deg', 'altitude-ft', # position
            'roll-deg', 'pitch-deg', 'heading-deg', # orientation
            'airspeed-kt', # velocity
    ]

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
        self.null = open('/dev/null', 'w')

        fp = open(self.filename, 'w')
        fp.truncate()
        fp.close()

    def setup_gnuplot(self):
        self.gnuplot = subprocess.Popen(['gnuplot'], stdin=subprocess.PIPE, 
                stdout=self.null, stderr=self.null)
        self.write('splot "%s"' % self.filename)
        print('Started gnuplot')

    def save(self):
        self.write('set term postscript eps enhanced')
        self.write('set output "%s"' % self.save_filename)
        self.replot()
        time.sleep(1) # give it 1 second to flush
        print('Saved graph to %s' % self.save_filename)

    def __del__(self):
        self.write('quit')
        self.gnuplot.kill()
        print('Killed gnuplot')

        self.null.close()
        print('Recorded %d points in %d seconds' % (self.recorded_points, 
                self.n_points / float(self.points_per_sec)))

    def parse_data(self, line):
        if line.count('\n') != 1:
            print('This line had more than one set of data in it, discarding')
            return

        d = {}

        l = line.rstrip('\n').split(',')
        for n, k in enumerate(self._keys):
            if k == 'altitude-ft':
                d[k] = '%.1f' % float(l[n]) # truncate altitude to 1 decimal
            else:
                d[k] = l[n]

        if d != self.current_data:
            self.last_data = dict(self.current_data) # copy
            self.current_data = dict(d)
            #print(self.current_data)

    def dump(self, fields):
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
            self.replot()

    def write(self, data):
        if self.gnuplot is not None:
            self.gnuplot.stdin.write('%s\n' % data)
            self.gnuplot.stdin.flush()

    def replot(self):
        if self.gnuplot is None:
            self.setup_gnuplot()
        self.write('replot')

class FGProperty(protocol.Protocol):

    def __init__(self):
        self.parser = FGData('pos.txt', 'out.eps')
        print('Ready for connections')

    def connectionMade(self):
        print('Connection from client')

    def connectionLost(self, reason):
        print('Lost connection with client:', reason.getErrorMessage())
        self.parser.save()

    def dataReceived(self, data):
        self.parser.parse_data(data)
        self.parser.dump(['latitude-deg', 'longitude-deg', 'altitude-ft'])


if __name__ == '__main__':
    f = protocol.Factory()
    f.protocol = FGProperty
    reactor.listenTCP(int(sys.argv[1]), f)
    reactor.run()

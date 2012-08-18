import os
import sys

try:
    import DistUtilsExtra.auto
except ImportError:
    DistUtilsExtra = None

from accomplishments import exceptions


if not DistUtilsExtra:
    msg = ('To build accomplishments-daemon you need '
           'https://launchpad.net/python-distutils-extra')
    print >> sys.stderr, msg
    sys.exit(1)
elif DistUtilsExtra.auto.__version__ < '2.18':
    raise exceptions.VersionError('needs DistUtilsExtra.auto >= 2.18')


def update_config(values={}):
    oldvalues = {}
    try:
        fin = file('accomplishments/util/accomplishments-daemon-config.py', 'r')
        fout = file(fin.name + '.new', 'w')

        for line in fin:
            fields = line.split(' = ')  # Separate variable from value
            if fields[0] in values:
                oldvalues[fields[0]] = fields[1].strip()
                line = "%s = %s\n" % (fields[0], values[fields[0]])
            fout.write(line)

        fout.flush()
        fout.close()
        fin.close()
        os.rename(fout.name, fin.name)
    except (OSError, IOError), e:
        print ("ERROR: Can't find accomplishments-daemon-config.py")
        sys.exit(1)
    return oldvalues


"""def update_desktop_file(datadir):
    try:
        fin = file('ubuntu-accomplishments-daemon.desktop.in', 'r')
        fout = file(fin.name + '.new', 'w')

        for line in fin:
            if 'Icon=' in line:
                line = "Icon=%s\n" % (datadir + 'media/ubuntu-accomplishments.svg')
            fout.write(line)
        fout.flush()
        fout.close()
        fin.close()
        os.rename(fout.name, fin.name)
    except (OSError, IOError), e:
        print ("ERROR: Can't find accomplishments-daemon.desktop.in")
        sys.exit(1)"""


class InstallAndUpdateDataDirectory(DistUtilsExtra.auto.install_auto):

    def run(self):
        values = {
            '__accomplishments_daemon__data_directory__': "'%s'" % (
                self.prefix + '/share/accomplishments-daemon/'),
            '__version__': "'%s'" % self.distribution.get_version()}
        previous_values = update_config(values)
        # update_desktop_file(self.prefix + '/share/accomplishments-daemon/')
        DistUtilsExtra.auto.install_auto.run(self)
        update_config(previous_values)


setup = DistUtilsExtra.auto.setup

import os

scriptpath = os.path.abspath(__file__)
# okay, so as we have the full path, we're ready to analise it...    

# start by looking 2 levels higher. This is either the branch directory,
# or the python2.7/...-packages directory, if the application is run installed.
branchpath = os.path.split(os.path.split(os.path.split(scriptpath)[0])[0])[0]
branchdir_name = os.path.split(branchpath)[1]
if ((branchdir_name == "site-packages") or (branchdir_name == 'dist-packages')):
    installed = True
else:
    installed = False

# Great, at that level we know whether the application is run from branch, or
# has been installed. This allows us to interpret the directories further...


if installed:
    basepath = os.path.split(os.path.split(os.path.split(branchpath)[0])[0])[0]
    # basepath should equal to prefix given on installation.
    print "Daemon seems to be installed to: " + basepath
    
    # finally, setting these significant data directories...
    systemdata_dir = os.path.join(basepath, 'share/accomplishments-daemon')
    media_dir      = os.path.join(basepath, 'share/accomplishments-daemon/media')
    
    # these two may need to be set for the accomplismhents scripts, so that they
    # can use OUR accomplishments module, using this installation.
    module_dir1    = os.path.join(basepath, 'lib/python2.7/site-packages') 
    module_dir2    = os.path.join(basepath, 'lib/python2.7/dist-packages')
    
    # that's where the daemon launcher is present
    daemon_exec_dir= os.path.join(basepath, 'bin')
    
    # locale files directory
    locale_dir= os.path.join(basepath, 'share/locale')
    
else:
    # using branch root directory as the base path
    basepath = branchpath
    print "Daemon seems to be run not installed, branch base path used: " + basepath
    
    # finally, setting these significant data directories...
    systemdata_dir = os.path.join(basepath, 'data/daemon')
    media_dir      = os.path.join(basepath, 'data/media')
    module_dir1    = None # always using default
    module_dir2    = None # always using default
    
    # that's where the daemon launcher is present
    daemon_exec_dir= os.path.join(basepath, 'bin')
    
    # If the application has not been installed, the .po files has not been
    # complied to .gmo, and thus gettext will be unable to use translated
    # strings. In this case it does not matter where it will look for locales,
    # but if it's left to default there is some small chance that they are
    # present int /usr/share/locale, used by an another installation.
    locale_dir = None

class Error(Exception):
    """
    A base class for exceptions.
    """
    def __init__(self, msg=None):
        if msg == None:
            msg = self.__doc__.strip()
        super(Error, self).__init__(msg)


class PathNotFound(Error):
    """
    Could not find the specified directory.
    """


class VersionError(Error):
    """
    There is a problem with the software version.
    """


class NoSuchAccomplishment(Error):
    """
    No such accomplishment has been registered.
    """


class AccomplishmentLocked(Error):
    """
    This accomplishment requires other things to be accomplished first.
    """

import datetime
import sys, os, traceback
import logging
import yaml

asterisk_etc_dir = '/etc/asterisk'

# general directories for gsm files, in order of preference
statement_dirs = [
    '/usr/share/asterisk/sounds/futel/recordings/karl_quuux/',
    '/usr/share/asterisk/sounds/futel/recordings/tishbite/',
    '/usr/share/asterisk/sounds/en/'
    ]

# preferred submenu directories for gsm files, in order of preference
preferred_statement_dirs = [
    '/usr/share/asterisk/sounds/futel/recordings/karl-robotron/',
    '/usr/share/asterisk/sounds/futel/recordings/karl-oracle-dead/',
    '/usr/share/asterisk/sounds/futel/recordings/karl-voicemail-ivr/',
    '/usr/share/asterisk/sounds/futel/recordings/karl-wildcard-line/']

metric_filename = '/var/log/asterisk/metrics'

def read_config(config_filename):
    yfile = '/'.join((asterisk_etc_dir, config_filename))
    return yaml.load(file(yfile, 'r'))

def agi_tracebacker(agi_o, func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except:
        agi_o.verbose('ERROR')
        (exc_type, exc_value, exc_traceback) = sys.exc_info()
        for line in traceback.format_exc().splitlines():
            agi_o.verbose(line)
        raise

def sound_path(sound_name, preferred_subs=None):
    """
    Return full path without extension for file for sound_name, or None.
    If preferred_sub is given, prefer paths with it as a substring.
    """
    dirs = []
    if not preferred_subs:
        preferred_subs = []
    for preferred_sub in preferred_subs:
        dirs.extend(
            [d for d in preferred_statement_dirs if preferred_sub in d])
    dirs.extend([d for d in statement_dirs if d not in dirs])
    for statement_dir in dirs:
        path = statement_dir + sound_name
        # stream_file and Background want it without the extension
        if os.path.isfile(path + '.gsm'):
            return path
    return None

def say(agi_o, filename, preferred_subs=None, escape=False):
    if escape:
        escape_digits = '0123456789#*'
    else:
        escape_digits = ''
    path = sound_path(filename, preferred_subs)
    if path:
        return agi_o.stream_file(path, escape_digits=escape_digits)
    # this seems to be parsed into args, punctuation may break it
    return agi_o.appexec('festival', filename)

def metric(agi_o, name):
    """ Create a metric event with name and values from agi_o. """
    # A metric event is a key-value map, a plain metric is just a name and an
    # optional arbitrary value and we should probably keep it simple. But we
    # add a lot of default attributes to basically combine it with a verbose
    # log.
    items = dict(
        (var, agi_o.get_variable(var))
        for var in ('UNIQUEID', 'CHANNEL', 'CALLERID(number)'))
    items['name'] = name
    # writer is responsible for adding timestamp
    metric_agilog(agi_o, **items)
    metric_metriclog(**items)

def metric_agilog(agi_o, **kwargs):
    """ Log a formatted line to the asterisk log. """
    line = ', '.join("%s=%s" % (k, v) for (k, v) in kwargs.items())
    # we only get verbose!
    agi_o.verbose(line, 1)

def metric_metriclog(**kwargs):
    """ Log a formatted line to the metric logfile. """
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    ch = logging.FileHandler(metric_filename)
    # write a line of comma separated key=value, should quote them!
    logline = ', '.join("%s=%s" % (k, v) for (k, v) in kwargs.iteritems())
    logline = ' '.join(('%(asctime)s', logline))
    formatter = logging.Formatter(logline)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.info('')

def calling_extension(agi_o):
    """ Return the calling extension. """
    return agi_o.get_variable('calling_extension')

def timestr_to_datetime(timestr):
    try:
        return datetime.datetime.strptime(timestr, '%H:%M')
    except ValueError:
        return datetime.datetime.strptime(timestr, '%Y-%m-%dT%H:%M')
    return [int(s) for s in timestr.split(':')]

def cmp_time(dt, now):
    if dt.year != 1900:
        # includes date
        if now.year < dt.year:
            return -1
        if now.year > dt.year:
            return 1
        if now.month < dt.month:
            return -1
        if now.month > dt.month:
            return 1
    if now.hour < dt.hour:
        return -1
    if now.hour > dt.hour:
        return 1
    if now.minute < dt.minute:
        return -1
    if now.minute > dt.minute:
        return 1
    return 0

def within_timestrs(start_string, end_string, now):
    if start_string and end_string:
        start_time = timestr_to_datetime(start_string)
        if cmp_time(start_time, now) >= 0:
            end_time = timestr_to_datetime(end_string)
            if cmp_time(end_time, now) < 0:
                return True
    return False

def relevant_config(config, extension, now, context=None):
    """Return map from config corresponding to extension and now and context, or None."""
    extension = int(extension)  # normalize
    for config_map in config:
        if extension in config_map['extensions']:
            if context is None or config_map.get('context') == context:
                (start_time, end_time) = (
                    config_map.get('start_time'), config_map.get('end_time'))
                if within_timestrs(start_time, end_time, now):
                    return config_map

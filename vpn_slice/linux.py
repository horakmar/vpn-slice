import os, fcntl
import subprocess as sp
from shutil import which
from ipaddress import ip_address

def find_paths():
    global DIG, IPROUTE, HOSTS, IPTABLES, RESOLVCONF
    DIG = which('dig') or '/usr/bin/dig'
    IPROUTE = which('ip') or '/sbin/ip'
    IPTABLES = which('iptables') or '/sbin/iptables'
    RESOLVCONF = which('resolvconf') or '/sbin/resolvconf'
    HOSTS = '/etc/hosts'

    for binary in (DIG, IPROUTE, IPTABLES):
        if not os.access(binary, os.X_OK):
            raise OSError("cannot execute %s" % binary)
    if not os.access(HOSTS, os.R_OK | os.W_OK):
        raise OSError("cannot read/write %s" % HOSTS)

def pid2exe(pid):
    try:
        return os.readlink('/proc/%d/exe' % pid)
    except (OSError, IOError):
        return None

def ppidof(pid):
    try:
        return int(next(open('/proc/%d/stat'%pid)).split()[3])
    except (OSError, ValueError, IOError):
        pass

def check_tun():
    if not os.access('/dev/net/tun', os.R_OK|os.W_OK):
        raise OSError("can't read and write /dev/net/tun")

def write_hosts(host_map, tag):
    global HOSTS
    with open(HOSTS,'r+') as hostf:
        fcntl.flock(hostf, fcntl.LOCK_EX) # POSIX only, obviously
        lines = hostf.readlines()
        keeplines = [l for l in lines if not l.endswith('# %s\n'%tag)]
        hostf.seek(0,0)
        hostf.writelines(keeplines)
        for ip, names in host_map:
            print('%s %s\t\t# %s' % (ip, ' '.join(names), tag), file=hostf)
        hostf.truncate()
    return len(host_map) or len(lines)-len(keeplines)

def dig(bind, host, dns, domains=None, reverse=False):
    global DIG
    host, dns = str(host), map(str, dns)
    basecl = [DIG,'+short','+noedns']+(['-b'+str(bind)] if bind else [])+['@'+s for s in dns]
    if reverse:
        extras = (['-x'],)
    if domains is None:
        extras = ([],)
    elif isinstance(domains, str):
        extras = (['+domain=' + d],)
    else:
        extras = (['+domain=' + d] for d in domains)

    out = set()
    for extra in extras:
        #print cl
        p = sp.Popen(basecl + extra + [host], stdout=sp.PIPE)
        lines = [l.strip() for l in p.communicate()[0].decode().splitlines()]
        if lines and p.wait()==0:
            for line in lines:
                line = line.rstrip('\n.')
                if reverse:
                    n, d = line.split('.',1)
                    out.add(n if d in domains else line)
                else:
                    try:
                        out.add(ip_address(line))
                    except ValueError:
                        pass     # didn't return an IP address!
    return out or None

def resolvconf(dns, device):
    global RESOLVCONF
    cl = [RESOLVCONF, '-a', device]
    p = sp.Popen(cl, stdout=sp.PIPE, stdin=sp.PIPE, stderr=sp.STDOUT)
    dnsconf = ''
    for ip in dns:
        dnsconf += "nameserver {}\n".format(ip)
    p.communicate(input=dnsconf.encode())

def iproute(*args):
    global IPROUTE
    cl = [IPROUTE]
    for arg in args:
        if isinstance(arg, dict):
            for k,v in arg.items():
                cl += [k] if v is None else [k, str(v)]
        else:
            cl.append(str(arg))

    if args[:2]==('route','get'): get, start, keys = 'route', 1, ('via','dev','src','mtu')
    elif args[:2]==('link','show'): get, start, keys = 'link', 3, ('mtu','state')
    else: get = None

    if get is None:
        sp.check_call(cl)
    else:
        w = sp.check_output(cl).decode().split()
        return {w[ii]:w[ii+1] for ii in range(start, len(w), 2) if w[ii] in keys}

def iptables(*args):
    global IPTABLES
    cl = [IPTABLES] + list(args)
    sp.check_call(cl)

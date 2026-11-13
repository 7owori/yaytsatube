import struct
def parse(d):
    pe = struct.unpack_from('<I', d, 0x3c)[0]
    nsec = struct.unpack_from('<H', d, pe+6)[0]; optsz = struct.unpack_from('<H', d, pe+20)[0]
    opt = pe+24; magic = struct.unpack_from('<H', d, opt)[0]
    dd = opt + (112 if magic == 0x20b else 96)
    secs = []
    so = opt + optsz
    for i in range(nsec):
        name, vsz, va, rsz, rptr = struct.unpack_from('<8sIIII', d, so+i*40)
        secs.append(dict(name=name.rstrip(b'\0').decode(), vsz=vsz, va=va, rsz=rsz, rptr=rptr, hdr=so+i*40))
    return dict(pe=pe, opt=opt, dd=dd, secs=secs, magic=magic)
def rsrc_walk(d, sec):
    base = sec['rptr']; va = sec['va']; out = []
    def walk(off, path):
        nn, ni = struct.unpack_from('<HH', d, base+off+12)
        for i in range(nn+ni):
            nid, o = struct.unpack_from('<II', d, base+off+16+i*8)
            if nid & 0x80000000:
                so = base + (nid & 0x7fffffff); l = struct.unpack_from('<H', d, so)[0]
                nid = d[so+2:so+2+l*2].decode('utf-16le')
            if o & 0x80000000: walk(o & 0x7fffffff, path+[nid])
            else:
                rva, size, cp, _ = struct.unpack_from('<IIII', d, base+o)
                out.append(dict(path=path+[nid], entry=base+o, rva=rva, size=size, off=rva-va+base))
    walk(0, [])
    return out
if __name__ == '__main__':
    import sys
    d = open(sys.argv[1],'rb').read()
    p = parse(d)
    for s in p['secs']: print(s)
    print('datadirs: rsrc', struct.unpack_from('<II', d, p['dd']+2*8), 'cert', struct.unpack_from('<II', d, p['dd']+4*8))
    print('checksum', struct.unpack_from('<I', d, p['opt']+64))
    rs = [s for s in p['secs'] if s['name']=='.rsrc'][0]
    for e in rsrc_walk(d, rs):
        print(e['path'], e['off'], e['size'], d[e['off']:e['off']+8].hex())
        if e['path'][0] in (14,):
            g = d[e['off']:e['off']+e['size']]
            n = struct.unpack_from('<H', g, 4)[0]
            for i in range(n): print('   grp', struct.unpack_from('<BBBBHHIH', g, 6+i*14))
        if e['path'][0] in (24,): print(d[e['off']:e['off']+e['size']].decode('utf8','replace')[:1500])

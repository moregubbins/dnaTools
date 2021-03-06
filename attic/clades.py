#!/usr/bin/env python3
# coding: utf-8
# note:: class lib of Jef's original clades.py script

# This file in its original form is good for reference, and it's in the
# examples directory. That version creates its own database and tables, so it's
# still functional on hg19 data. 

# Some routines here have been updated with respect to the schema, so I'm
# putting this file into the attic for now. Some parts of the parsing of BED
# and VCF parsing may be usable, but it's not really useful beyond that.

import locale,time,subprocess
#import sqlite3,os,time,sys,random,argparse,locale,csv,subprocess
#from collections import defaultdict
from db import DB
from lib import *

class Clades(DB):

    def __init__(self):
        DB.__init__(self)
        self.namespace = None
        self.create = False
        self.stats1 = False
        self.stats2 = False
        self.docalls = False
        self.listfiles = False
        self.listbed = False
        self.mergeup = False
        self.querysnp = False
        self.updatesnps = False

    def do_create(self):

        def get_coverage(r1, r2):
            ids = {r1[0][0]:0, r2[0][0]:1}
            accum1 = 0
            toggles = [False, False]
            intervals = [(a,b) for (a,b,c) in r1+r2] + [(a,c) for (a,b,c) in r1+r2]
            post = None
            for r in sorted(intervals, key=lambda a: a[1]):
                toggles[ids[r[0]]] ^= True
                if post and (toggles[0] ^ toggles[1]):
                    accum1 += r[1]-post
                    post = None
                elif toggles[0] & toggles[1]:
                    post = r[1]
            if post:
                accum1 += r[1]-post
            accum2 = 0
            for id, mina, maxa in r1:
                accum2 += maxa-mina
            return accum2, accum1

        t0 = time.time()
        self.updatesnps = True

        # nranges, coverage1 (total r1), coverage2 (gated by r2)

        self.create_schema()

        # should probably go into database initialization dbo
        locale.setlocale(locale.LC_ALL, '')

        #GET THE UNZIPS

        UNZIP_DIR = os.path.join(config['REDUX_DATA'], config['unzip_dir'])
        files = sorted(os.listdir(UNZIP_DIR), key=locale.strxfrm)

        # DB METADATA

        meta = [('datadir', UNZIP_DIR),
                    ('date', ' '.join((time.asctime(), time.tzname[time.daylight]))),
                    ('locale', 'LC_ALL'),
                    ('directory', os.getcwd()),
                    ]

        #INS META

        self.dc.executemany('insert into meta values(?,?)', meta)

        ranges = []

        #INS FILES

        self.dc.execute('insert into uploadlog(kitName) VALUES("age.bed")')
        myid = self.dc.lastrowid

        #OPEN AGE.BED

        lines = open('age.bed').readlines()
        for line in lines:
            chromo, minr, maxr = line.split()
            ranges.append((myid, int(minr), int(maxr)))

        #INS BED
        self.dc.execute('drop table if exists tmpt')
        self.dc.execute('create temporary table tmpt(a,b,c)')
        self.dc.executemany('insert into tmpt values(?,?,?)', ranges)
        self.dc.execute('''insert or ignore into bedranges(minaddr,maxaddr)
                           select b,c from tmpt''')
        self.dc.execute('''insert into bed(pID, bID)
                           select t.a, br.id from bedranges br
                           inner join tmpt t on
                           t.b=br.minaddr and t.c=br.maxaddr''')
        self.dc.execute('drop table tmpt')

        cover_ranges = ranges
        trace(1, 'enter at {:.2f} seconds'.format(time.time() - t0))

        stat_list = []

        #INS FILES

        for nf,fname in enumerate(files):
            if fname.endswith('.bed'):
                self.dc.execute('insert into uploadlog(kitName,kitId,seq) VALUES(?,1,?)', (os.path.splitext(fname)[0],nf))
                myid = self.dc.lastrowid
                ranges = []
                try:
                    for line in open(os.path.join(UNZIP_DIR, fname)):
                        ychr, minr, maxr = line.split()
                        ranges.append((myid, int(minr), int(maxr)))
                except:
                    trace(0, 'FAILED on file {}'.format(fname))
                    continue

                #INS BED

                self.dc.execute('drop table if exists tmpt')
                self.dc.execute('create temporary table tmpt(a,b,c)')
                self.dc.executemany('insert into tmpt values(?,?,?)', ranges)
                self.dc.execute('''insert or ignore into bedranges(minaddr,maxaddr)
                                   select b,c from tmpt''')
                self.dc.execute('''insert into bed(pID, bID)
                               select t.a, br.id from bedranges br
                               inner join tmpt t on
                               t.b=br.minaddr and t.c=br.maxaddr''')

                tcover, pcover = get_coverage(ranges, cover_ranges)
                stat_list.append((myid, tcover, pcover, len(ranges)))

        trace(1, 'bed done at {:.2f} seconds'.format(time.time() - t0))

        #INS BEDSTATS

        self.dc.executemany('insert into bedstats values(?,?,?,?)', stat_list)

        #INS FILES

        ids={}
        self.dc.execute('insert into uploadlog(kitName) VALUES("implications")')
        myid = self.dc.lastrowid
        self.dc.execute('insert into uploadlog(kitName) VALUES("^")')
        ids['^'] = self.dc.lastrowid
        self.dc.execute('insert into uploadlog(kitName) VALUES("<")')
        ids['<'] = self.dc.lastrowid
        ll = {}
        vl = []

        #OPEN IMPLICATIONS

        with open('implications.txt') as implications:
            for line in implications:
                toks = line.split()
                if toks and toks[0] in ('^', '<'):
                    addr = toks[1]
                    ref = toks[3]
                    alt = toks[4]
                    vl.append((addr, ref, alt))
                    ll[(addr, ref, alt)] = ids[toks[0]]

        #INS VARIANTS

        self.dc.executemany('insert or ignore into variants(pos,anc,der) values (?,?,?)', ll)
        cl = []

        for tup in vl:
            tid = self.dc.execute('select id from variants where pos=? and anc=? and der=?', tup).fetchone()[0]
            cl.append((myid, tid, ll[tup]))

        #DEL VCFCALLS

        self.dc.execute ('delete from vcfcalls where pID=?', (myid,))
        trace(3, 'inserting to vcfcalls {}'.format(cl))

        #INS VCFCALLS

        self.dc.executemany('insert into vcfcalls(pid, vid) values(?,?)', [(v[2],v[1]) for v in cl])

        calls = []
        rejects = []
        stats = []
        ipos = [a for (a,b,c) in vl]

        #FOR LOOP FILES

        #print(files)
        for fname in files:
            if fname.endswith('.vcf'):
                ny = nv = ns = ni = nr = 0
                myid = self.dc.execute('select id from uploadlog where kitName = ?', (os.path.splitext(fname)[0],)).fetchone()[0]
                trace(3, 'reading file {} from {}'.format(fname,
                    UNZIP_DIR))
                with open(os.path.join(UNZIP_DIR, fname)) as lines:
                    for line in lines:
                        try:
                            chrom,pos,iid,ref,alt,qual,filt,inf,fmt,ii = line.split()
                        except:
                            continue
                        if chrom == 'chrY':
                            ny += 1
                            # keep certain rejects for swapping reference genome positions later
                            # rather than swap&call rejects, mark them dirty?
                            if filt == 'REJECTED':
                                nr += 1
                                if pos in ipos:
                                    rejects.append((myid, pos, ref, alt))
                            elif filt == 'PASS':
                                nv += 1
                                if ref != '.' and alt != '.':
                                    calls.append((myid, pos, ref, alt))
                                    if len(ref) == 1 and len(alt) == 1:
                                        ns += 1 # snps
                                    else:
                                        ni += 1 # indels
                trace(3, 'length of rejects now: {}'.format(len(rejects)))
                stats.append((myid, ny, nv, ns, ni, nr))

        #INS VCFSTATS

        self.dc.executemany('insert into vcfstats(id,ny,nv,ns,ni,nr) VALUES(?,?,?,?,?,?)', stats)
        self.commit()
        vl = []

        for iid, pos, ref, alt in rejects:
            try:
                #SEL VARIANTS
                vid = self.dc.execute('select id from variants where pos=? and anc=? and der=?', (pos,ref,alt)).fetchone()[0]
            except:
                #INS VARIANTS
                self.dc.execute('insert into variants(pos,anc,der) values (?,?,?)', (pos,ref,alt))
                vid = self.dc.lastrowid
            vl.append((iid,vid))

        #INS VCFREJ

        self.dc.executemany('insert into vcfrej(id,vid) VALUES(?,?)', vl)
        vl = []

        for iid, pos, ref, alt in calls:
            try:
                #SEL VARIANTS
                vid = self.dc.execute('select id from variants where pos=? and anc=? and der=?', (pos,ref,alt)).fetchone()[0]
            except:
                #INS VARIANTS
                self.dc.execute('insert into variants(pos,anc,der) values (?,?,?)', (pos,ref,alt))
                vid = self.dc.lastrowid
            vl.append((iid,vid))

        #INS VCFCALLS

        self.dc.executemany('insert into vcfcalls(id,vid) VALUES(?,?)', vl)
        rejects = calls = stats = vl = None
        trace(1, 'vcf done at {:.2f} seconds'.format(time.time() - t0))
        self.commit()
        trace(1, 'commit done at {:.2f} seconds'.format(time.time() - t0))
        self.commit()
        
    def docalls(self):
        
        # check for positive calls, covered, and not-covered in all kits;
        # return vector of True values if v contained in a range, else False
        # does not consider the endpoints
        # ranges must be sorted on their minaddr
        # input vector must be sorted

        def in_range(v_vect, ranges):
            c_vect = []
            ii = 0
            nmax = len(ranges)
            for v in v_vect:
                while ii < nmax and ranges[ii][0] < v:
                    ii += 1
                if ii > 0 and v > ranges[ii-1][0] and v < ranges[ii-1][1]:
                    c_vect.append(True)
                else:
                    c_vect.append(False)
            if len(c_vect) != len(v_vect):
                raise ValueError
            return c_vect

        c1 = self.db.cursor()
        c2 = self.db.cursor()

        # wishlist: redo the refpos swapping from implications
        # caution if adding new variants, might not capture all of the rejects
        # see above, in creating the database
        # redoing here permits quick edit of impl.txt & re-run without a re-build
        # best to do a re-build on final run

        # the reference assembly genome, hg19 was mainly someone U152+, so the
        # REF/ALT need to be swapped for some POSs these were read from the
        # implications file, a result of hand-correcting oddities this means people
        # who have a call for this POS in their vcf don't really have a SNP and
        # vice-versa these values are both in variants, below, and output is
        # corrected when we write at the end

        ref_swaps = {}
        swaps = c1.execute('select v.id,v.pos,v.anc,v.der from variants v, vcfcalls c where c.vid=v.id and c.origin="<"')

        for vid,pos,ref,alt in swaps:
            # ref_swaps[vid] = (ref,alt) # as specified in implications
            trace(2,'swappos id={}:{}.{}.{}'.format(vid,pos,ref,alt))
            #SEL VARIANTS
            vc =c2.dc.execute('select id from variants where pos=? and anc=? and der=?', (pos,alt,ref)) # swapped version versus what's in implications
            for (vid,) in vc: # swapped version appears in variants
                trace(2,'swappos id={}:{}.{}.{}'.format(vid,pos,alt,ref))
                ref_swaps[vid] = (ref,alt)

        inserted = {}

        #SEL VCFCALLS
        ins = c1.execute('select c.vid from vcfcalls c where c.origin="^"')

        for (vid,) in ins:
            trace(2,'inserted:variant id {}'.format(vid))
            inserted[vid] = None

        # list and count variants from the kits and uncount the inserted ones
        vcounts = {}
        #SEL VCFCALLS
        vl = c1.execute('select count(id), vid from vcfcalls group by vid')

        for count, vid in vl:
            trace(3,'{}: {}'.format(vid,count))
            vcounts[vid] = count
        #SEL VCFCALLS
        vl = c1.execute('select vid from vcfcalls where origin in ("^","<")')

        for (vid,) in vl:
            vcounts[vid] -= 1

        # which variants are SNPS
        snps = {}
        #SEL VARIANTS
        vl = c1.execute('select id from variants where length(anc)=1 and length(der)=1')

        for (vid,) in vl:
            snps[vid] = True

        # which variants are indels
        indels = {}
        #SEL VARIANTS
        vl = c1.execute('select id from variants where (length(anc)>1 or length(der)>1)')

        for (vid,) in vl:
            indels[vid] = True

        trace(2, '{} snps and {} indels'.format(len(snps), len(indels)))
        trace(1, 'variants gathered at {:.2f} seconds'.format(time.time() - t0))

        # algo
        # get all of the cbu, cbl, and cblu - this is fast
        # for each tester id
        #   get the calls for that id
        #   get the bed ranges for that id
        #   check coverage
        #      ';cbu' ';cbu' ';cblu'
        #      if not covered append ';nc'

        calls = defaultdict(dict)

        #CREATE TMP TBL TPOS
        c1.execute('create temporary table tpos (pos int)')
        #INS TPOS
        c1.execute('insert into tpos select distinct pos from variants')

        # these run fast - gather cbu,cbl,cblu all at once, and they do not depend
        # on REF,POS

        #SEL TPOS
        cbu = 'select id,maxaddr from bed where maxaddr in (select * from tpos)'
        #SEL TPOS
        cbl = 'select id,minaddr from bed where minaddr in (select * from tpos)'
        #SEL TPOS
        cblu = 'select id,maxaddr from bed where maxaddr=minaddr and maxaddr in (select * from tpos)'

        call_strings = ['', ';cblu', ';cbu', ';cbl', ';nc']

        for ii,pos in c1.execute(cblu):
            calls[ii][pos] = 1
        trace(1, 'cblu found at {:.2f} seconds'.format(time.time() - t0))

        for ii,pos in c1.execute(cbu):
            calls[ii][pos] = 2
        trace(1, 'cbu found at {:.2f} seconds'.format(time.time() - t0))

        for ii,pos in c1.execute(cbl):
            calls[ii][pos] = 3
        trace(1, 'cbl found at {:.2f} seconds'.format(time.time() - t0))

        # get list of ids for the kits, in their original listing order

        iids = []
        #SEL FILES
        files = c1.execute('select id,name,seq from files where kit=1 order by 3')

        for ii,fname,seq in files:
            iids.append(ii)

        # track the pos,ref,alt,id of the variants

        vrai_vector = []
        trace(3,'vcounts: {}'.format(vcounts))

        for vid in vcounts:
            #SEL VARIANTS
            c1 = c1.execute('select pos,anc,der from variants where id=?', (vid,))
            pos,ref,alt = next(c1)
            vrai_vector.append((pos,ref,alt,vid))
            trace(3,'{}'.format(vrai_vector[-1]))

        vrai_vector.sort()
        vra_vector = [(a,b,c) for (a,b,c,d) in vrai_vector]
        v_vector = [a for (a,b,c,d) in vrai_vector]
        vid_vector = [d for (a,b,c,d) in vrai_vector]

        # all of the calls across the kits

        kit_calls = defaultdict(dict)
        #SEL VCFCALLS
        kcalls = c1.execute('select id,vid from vcfcalls')

        for ID,vid in kcalls:
            kit_calls[ID][vid] = None
        trace(1, 'raw variants done at {:.2f} seconds'.format(time.time() - t0))

        # find if variant was covered (note cbu/cbl already handled above)

        ist = 0
        for ii in iids:

            ist += 1
            #SEL BED
            ranges = c1.execute('select minaddr,maxaddr from bed where id=? order by minaddr', (ii,))
            kit_ranges = []

            for minaddr,maxaddr in ranges:
                kit_ranges.append((minaddr,maxaddr))

            coverage_vector = in_range(v_vector, kit_ranges)

            for iv,v in enumerate(v_vector): # index,address
                if vid_vector[iv] in kit_calls[ii]:
                    continue # will write in output below
                if not coverage_vector[iv] and v not in calls[ii]:
                    calls[ii][v] = 4 # ;nc

            if (ist % 250) == 249:
                trace(2, '250 people done at {:.2f} seconds'.format(time.time() - t0))

        trace(1, '{} rows done at {:.2f} seconds'.format(len(vra_vector), time.time() - t0))

        # rejects across all of the kits

        rejects = defaultdict(dict)
        #SEL VCFREJ
        rej = self.dc.execute('select id,vid from vcfrej')
        for iid,vid in rej:
            rejects[iid][vid] = None

        # write the output

        out = ''
        for iiv, vid in enumerate(vid_vector):
            vname = '{}'.format(v_vector[iiv])
            if vid in ref_swaps and vcounts[vid] > 0:
                nvar = 0
                for ii in iids:
                    # a kit that was not called for this variant...reverse
                    if vid not in kit_calls[ii] and ((v_vector[iiv] not in calls[ii]) or (calls[ii][v_vector[iiv]] != 4)):
                        if vid not in rejects[ii]:
                            nvar += 1
                ref,alt = ref_swaps[vid]
                trace(2,'swapping variant id={}; nvar={}'.format(vid,nvar))
            else:
                nvar = vcounts[vid]
                xx,ref,alt = vra_vector[iiv]
            if nvar == 0 and vid not in inserted:
                continue # skip over swap variants, but keep inserted variants
            ref = ref.replace(',', '|') # cleanse any commas
            alt = alt.replace(',', '|')
            out += vname+',,'+ref+','+alt+','
            if vid in snps:
                out += 'SNP,'
            elif vid in indels:
                out += 'Indel,'
            out += '{},,,,,,,,,,,'.format(nvar)
            for ii in iids:
                out += ','
                if vid in ref_swaps and vcounts[vid] > 0:
                    if vid in kit_calls[ii]:
                        tcall = ''
                    elif (v_vector[iiv] not in calls[ii] or calls[ii][v_vector[iiv]] != 4):
                        if vid not in rejects[ii]:
                            tcall = vname+'.'+ref+'.'+alt
                        else:
                            tcall = ';rej' # mark rejects differently
                            tcall = '' # compatibility with existing script
                    else:
                        tcall = ''
                elif vid in kit_calls[ii]:
                    tcall = vname+'.'+ref+'.'+alt
                else:
                    tcall = ''
                out += tcall
                if v_vector[iiv] in calls[ii]:
                    out += call_strings[calls[ii][v_vector[iiv]]]
            print(out)
            out = ''

        self.dbo.commit()
        trace (1, 'all done at {:.2f} seconds'.format(time.time() - t0))
        
    def stats1(self):
        # STATS1 in redux.bash
        c = self.dc.execute('select id, coverage1, coverage2, nranges from bedstats')
        for row in c:
            print(row[1], row[2], row[3])
        
    def stats2(self):
        # STATS2 in redux.bash
        c = self.dc.execute('select id, ny, nv, ns, ni from vcfstats')
        for row in c:
            print(row[1], row[2], row[3], 0,0,0, row[4], 0,0)
        
    def listfiles(self):
        # list out which files are stored, in sort order
        c = self.dc.execute('select kitName,seq from uploadlog where kit=1 order by 2')
        for row in c:
            print(row[0])
        
    def listbed(self):
        # list out full path bed files, in sort order
        c = self.dc.execute('select kitName,seq from uploadlog where kit=1 order by 2')
        for row in c:
            print(os.path.join(UNZIP_DIR,row[0])+'.bed')
        self.dbo.commit()

    def updatesnps(self):
        # update the snp defs and names from hg19
        with open('snps_hg19.csv') as snpfile:
            reader = csv.DictReader(snpfile)
            snps = defaultdict(list)
            for row in reader:
                snpdef = (row['start'], row['allele_anc'], row['allele_der'])
                snps[snpdef].append(row['Name'])
            for snp in snps:
                #INS VARIANTS
                self.dc.execute('insert or ignore into variants(pos,anc,der) values(?,?,?)', snp)
                #SEL VARIANTS
                c1 = self.dc.execute('select id from variants where pos=? and anc=? and der=?', snp)
                vid = c1.fetchone()[0]
                for n in snps[snp]:
                    #INS SNPNAMES
                    #print('insert into snpnames values(?,?)', (vid, n))
                    self.dc.execute('insert into snpnames values(?,?)', (vid, n))
        
    def querysnp(self):

        # namespace stuff
        if self.namespace.snp:
            self.querysnp = vars(self.namespace)['snp'][0]
        else:
            self.querysnp = False

        # print info about a snp by name or addr
        trace(2, 'looking for details about {}...'.format(self.querysnp))

        ids = set()
        #SEL VARIANTS
        c1r = self.dc.execute('select * from variants where pos=?', (self.querysnp,))

        for row in c1r:
            ids.add(row[0])

        # wildcard version - usually not useful
        #c1 = self.dbo.c1.execute('select * from snpnames where name like ?', (self.querysnp+'%',))

        #SEL SNPNAMES

        c1r = self.dc.execute('select id from snpnames where name=?', (self.querysnp.upper(),))
        for row in c1r:
            ids.add(row[0])

        poss = set()
        nams = set()

        for id in ids:

            #SEL VARIANTS

            c1r = self.dc.execute('select distinct pos from variants where id=?', (id,))
            for row in c1r:
                poss.add('{}'.format(row[0]))

            #SEL SNPNAMES

            c1r = self.dc.execute('select distinct name from snpnames where id=?', (id,))
            for row in c1r:
                nams.add(row[0])

        for pos in poss:

            #SEL VARIANTS

            c1r = self.dc.execute('select pos,anc,der,id from variants where pos=?', (pos,))
            for row in c1r:
                print('{:>8}.{}.{} - {} (id={})'.format(row[0], row[1], row[2], '/'.join(nams),row[3]))

        if not ids:
            print('No data on', self.querysnp)

        kitids = set()

        if vars(self.namespace)['kits']:

            kitids = set()
            for iid in ids:
                #SEL VCFCALLS
                c1r = self.dc.execute('select distinct id from vcfcalls where vid=?', (iid,))
                for row in c1r:
                    kitids.add(row[0])
            print('Found in', len(kitids), 'kits')

            for iid in kitids:
                #SEL FILES
                c1r = self.dc.execute('select kitName from uploadlog where id=?', (iid,))
                print(c1r.fetchone()[0])

        if vars(self.namespace)['implications']:
            if poss:
                print('\n--- implications.txt ---')
                #GREP
                io = subprocess.run(['egrep', '-iw', '|'.join(poss), 'implications.txt'],
                                stdout=subprocess.PIPE)
                print(io.stdout.decode('utf-8'))

        if vars(self.namespace)['tree']:
            if poss:
                print('--- tree.csv ---')
                #GREP
                io = subprocess.run(['egrep', '-iw', '|'.join(poss), 'tree.csv'],
                                    stdout=subprocess.PIPE)
                print(io.stdout.decode('utf-8'))

        if vars(self.namespace)['badlist']:
            if poss:
                print('--- badlist.txt ---')
                #GREP
                io = subprocess.run(['egrep', '-iw', '|'.join(poss), 'badlist.txt'],
                                    stdout=subprocess.PIPE)
                print(io.stdout.decode('utf-8'))

                print('--- recurrencies.txt ---')
                #GREP
                io = subprocess.run(['egrep', '-iw', '|'.join(poss), 'recurrencies.txt'],
                                    stdout=subprocess.PIPE)
                print(io.stdout.decode('utf-8'))

        
    def mergeup(self):

        #incomplete

        c1 = self.db.cursor()
        c2 = self.db.cursor()
        c3 = self.db.cursor()

        # populate tree from the rows in tree csv
        # store the variants associated with the row (column 5, semicolon sep'd)

        #CREATE TMP TBL TREE

        c1.execute('CREATE TEMPORARY TABLE tree(e INTEGER PRIMARY KEY, a INTEGER, b INTEGER, c INTEGER, d INTEGER, f INTEGER, g TEXT, h TEXT, i INTEGER)')

        #CREATE TMP TBL TREEVARS

        c1.execute('CREATE TEMPORARY TABLE treevars(ID INTEGER REFERENCES tree(e), snpid INTEGER REFERENCES variants(id), unique(id,snpid))')

        with open('tree.csv') as csvfile:
            fieldnames=['a','b','c','d','e','f','g','h','i']
            reader = csv.DictReader(csvfile, fieldnames=fieldnames)
            for row in reader:
                tup=(row['a'],row['b'],row['c'],row['d'],
                         row['f'],row['g'],row['h'],row['i'])
                c1.execute('insert into tree(a,b,c,d,f,g,h,i) values (?,?,?,?,?,?,?,?)', tup)
                treeid = c1.lastrowid
                snplist = row['e'].split(';')

                for snp in snplist:
                    if '/' in snp:
                        poss = set()
                        for sname in snp.split('/'):
                            #SEL SNPNAMES
                            c1 = c1.execute('select id from snpnames where name=?', (sname,))
                            r1 = next(c1)
                            if r1:
                                #INS TREEVARS
                                c1.execute('insert or ignore into treevars values(?,?)', (treeid,snpid))
                    else:
                        #SEL VARIANTS
                        s = c1.execute('select id from variants where pos=?', (snp,))
                        try:
                            snpid = s.fetchone()[0]
                        except:
                            #INS VARIANTS
                            c1.execute('insert into variants(pos) values(?)', (snp,))
                            snpid = c1.lastrowid
                        #INS TREEVARS
                        c1.execute('insert or ignore into treevars values(?,?)', (treeid,snpid))

        # Each row in the tree carries a range [minkit, maxkit] (col3 & col4)
        # Those are the column indices in the variant-not-shared.txt array.
        # Columns represent people, so it's a range of people in the clade.
        # For a sub-node to be merged up, it is necessary that all of the
        # people grouped in the sub-node's range are also in the parent.
        # So we have to check the parent range of people against all of the snps
        # that define the child clade, and if any such snp is NOT
        # called for some portion of the people in the parent range,
        # it precludes merging.
        # example:
        # kits k2,k3,k4,k5 are part of a parent clade
        # kits k4,k5 have snps S1,S2 that k2,k3 don't have
        # snps S1,S2 define a child clade that can't be merged up to the parent

        # in this table, let's make person id = column number

        #CREATE TMP TBL VARS

        c1.execute('CREATE TEMPORARY TABLE vars(snp INTEGER REFERENCES variants(id), pid INTEGER)')
        tups = []

        with open('variant-not-shared.txt') as varfile:
            c = csv.reader(varfile)
            for row in c:
                rowsnp = row[0]
                try:
                    #SEL VARIANTS
                    rowsnpid = c2.execute('select id from variants where pos=?', (rowsnp,)).fetchone()[0]
                except:
                    # insert variant since we don't have it yet
                    trace(2, 'pos = {} added'.format(row[0]))
                    #INS VARIANTS
                    c2.execute('insert into variants(pos) values(?)', (rowsnp,))
                    rowsnpid = c2.lastrowid
                for col in range(17,len(row)):
                    if row[col]:
                        tups.append((rowsnpid, col+1))

        #INS VARS

        c1.executemany('insert into vars values(?,?)', tups) 
        # tables populated

        #SEL TREE

        c1r = c1.execute('select * from tree where g!="0"')

        for row in c1r:
            par = os.path.splitext(row[6])[0]
            #SEL TREE
            prow = next(c2.execute('select e,c,d from tree where g=?', (par,)))
            minidx = prow[1]
            maxidx = prow[2]
            trace(3,'id:{}; max/min:{}/{}'.format(prow[0], minidx, maxidx))
            #SEL TREEVARS
            c2r = c2.execute('select snpid from treevars where id=?', (row[0],))
            for r1 in c2r:
                for kit in range(minidx,maxidx+1):
                    trace(3,'checking kit {} for snpid {}'.format(kit,r1[0]))
                    #SEL VCFCALLS
                    hasit = c3.execute('select id from vcfcalls where vid=? and id=(select id from uploadlog where seq=?)', (r1[0], kit))
                    try:
                        snpid = next(hasit)
                        continue
                    except:
                        break # cannot be merged up
                else:
                    continue
                break
            else:
                print(row[6], 'into its parent')
                continue # on to the next row

        
if __name__ == '__main__':
    c = Clades()
    c.do_create()

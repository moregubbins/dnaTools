#!/bin/python

# legacy redux.bash steps {{{

# [prep]

# (1) BACKUPS
# (2) CHECK NECESSARY FILES EXIST
# (3) UNZIP FILES
# (4) EXTRACT RAW DATA

# [data]

# (5) POST-PROCESSING OF RAW RESULTS FOR ODDITIES
# (6) DATA CATEGORISATION (FORM TABLES)
# (7) DATA ORDERING
# (8) NAMES TO SNPS
# (9) STATISTICS GENERATION

# [form+tree]

# (10) FORM REPORT
# (11) TREE STRUCTURE

# [qc] 

# (12) CONSISTENCY CHECKING
# (13) FLAG CLADES THAT CAN BE MERGED
# (14) IDENTIFY FORCED POSITIVES : CLADES THAT SHOULDN'T BE MERGED?

# [rpts]

# (15) INSERT TREE INTO REPORT
# (16) SHORT REPORT
# (17) HTML REPORT

# [ages/tmrca]

# (18) INITIAL AGE ANALYSIS

# [output]

# (19) TREE MERGING
# (20) AGE REPORT WRITING
# (21) TREE SVG WRITING

# }}}

import sys,argparse, yaml

config=yaml.load(open('config.yaml'))

parser = argparse.ArgumentParser()
parser.add_argument('-b', '--backup', help='do a backup', action='store_true')
parser.add_argument('-p', '--prep', help='prep file structure', action='store_true')
args = parser.parse_args()

#print ('\n'+sys.argv[0]+' version: '+config['VERSION']+'\n')
print "\n"

if args.backup:
    print "** performing backup."
    print "** backup done."

if args.prep:
    print "** preparing file structure."
    print "** prep done."

print "\nscript complete.\n"

#!/usr/bin/env python

import argparse
from os.path import isfile
from scipy.stats import binom, hypergeom, chi2_contingency
from pprint import pprint
from py2neo import *
from py2neo.matching import *
import numpy as np

# SCRIPT PARAMETERS
parser = argparse.ArgumentParser(description='Search enriched terms/categories in the provided (gene) set')
parser.add_argument('-q', '--query', required=True, help='Query set.')
parser.add_argument('-t', '--sets', required=True, help='Target sets node type.')
parser.add_argument('-s', '--species', required=True, type=int, help='Taxon id.')
parser.add_argument('-a', '--alpha', required=False, type=float, default=0.05, help='Significance threshold.')
parser.add_argument('-c', '--adjust', required=False, action="store_true", help='Adjust for multiple testing (FDR).')
parser.add_argument('-m', '--measure', required=False, default='binomial', help='Dissimilarity index: binomial (default), hypergeometric, chi2 or coverage. chi2 and coverage are NOT YET IMPLEMENTED')
parser.add_argument('-l', '--limit', required=False, type=int, default=0, help='Maximum number of results to report.')
parser.add_argument('-v', '--verbose', required=False, action="store_true", help='Talk a lot.')
param = parser.parse_args()

# LOAD QUERY
text = param.query
query = set()
if isfile(text):
	with open(text) as f:
		content = ' '.join(f.read().split('\n')).split()
		query |= set(content)
else: # parse string
	query |= set(text.split())

if param.verbose:
  print(f'query set: {query}')

# CONNECT TO Neo4J
neo = Graph("bolt://localhost:7687", auth=("neo4j", "a"))
nodes = NodeMatcher(neo)

# COMPUTE POPULATION SIZE
population_size = nodes.match('Gene', taxon_id=param.species).count()
if param.verbose:
	print("population_size: ", population_size)

# RETRIEVE TARGET SETS FOR QUERYc
path = '[:is_a|part_of|annotates*]' if param.sets=='GOTerm' else ''
cypher = f"MATCH (t:{param.sets})-{path}->(n:Gene {{taxon_id:{param.species} }}) WHERE n.id IN ['"+"', '".join(query)+"'] RETURN DISTINCT t"
if param.verbose:
	print(cypher)
sets = neo.run(cypher)
#cypher = f"MATCH (t:{param.sets})-{path}->(n:Gene {{taxon_id:{param.species} }}) WHERE n.id IN ['"+"', '".join(query)+"'] RETURN count(DISTINCT t)"
#aze = neo.run(cypher).to_table()
#print(aze[0][0])

# EVALUATE SETS
i = 0
results = []
query_size = len(query)

for s in sets: #_ids:
	sid = s['t']['id']
	# RETRIEVE TARGET SET ELEMENTS
	path = '[:is_a|part_of|annotates*1..20]' if param.sets=='GOTerm' else ''
	cypher = "MATCH (t:{})-{}->(n:Gene {{taxon_id:{} }}) WHERE t.id='{}' RETURN n.id".format(param.sets, path, param.species, sid)
	if param.verbose:
		print(cypher)
	table = neo.run(cypher).to_table()
	elements = set(map(lambda x: x[0], table))
	i += 1
	print(i)
	common_elements = elements.intersection(query)
	if len(common_elements) < 2:
		next
	if param.measure == 'coverage':
		measure = (len(common_elements)/len(query)) * (len(common_elements)/len(elements))
	if param.measure =='binomial': # binom.cdf(>=success, attempts, proba)
		# prendre le probleme à l'envers
		# quelle est la probabilité qu'il y ait x elements pas en commun, 
		# sachant un tirage de z elements et que la probabilité de tiré des elements 
		# pas en commun est 1 - proba de tiré des elements en commun
		measure = binom.cdf(query_size - len(common_elements), query_size, 1 - float(len(elements))/population_size)
	if param.measure =='hypergeometric':
	measure = hypergeom.cdf(query_size - len(common_elements),population_size, int((1 - float(len(elements))/population_size)*population_size), query_size)
	if param.measure =='chi2':
		a = len(common_elements)
		b = len(query) - len(common_elements)
		c = len(elements) - len(common_elements)
		d =  population_size - len(query) - len(elements) + len(common_elements)
		contengency_table = np.array([
			[a, b],
			[c, d]
			])
		z, measure, e, r = chi2_contingency(contengency_table)
	#else:
	#	print(f'sorry, {param.measure} not (yet) implemented')
	#	exit(1)
	r = { 'id': sid, 'desc': s['t']['desc'], 'common.n':len(common_elements), 'target.n': len(elements), 'measure': measure, 'elements.target': elements, 'elements.common': common_elements }
	results.append( r )
if param.verbose:
  print(results)

# PRINT SIGNIFICANT RESULTS
results.sort(key=lambda an_item: an_item['measure'])
i=1
for r in results:
	# FDR
	if param.adjust and r['measure'] > param.alpha * i / len(results): break
	# limited output
	
	if param.limit > 0 and i>param.limit: break
	# alpha threshold
	
	elif r['measure'] > param.alpha: break
	# OUTPUT
	pval = "{:.4f}".format(r['measure']) if r['measure']>0.01 else "{:.2e}".format(r['measure'])
	
	print("{}\t{}\t{}/{}\t{}\t{}".format( r['id'], pval, r['common.n'], r['target.n'], r['desc'], ', '.join(r['elements.common'])))
	i+=1


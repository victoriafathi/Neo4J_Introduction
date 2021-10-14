#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from py2neo import Graph
import argparse
from os.path import isfile
import json
from scipy.stats import binom, hypergeom

################################################################################################
parser = argparse.ArgumentParser(description='Search enriched terms/categories in the provided (gene) set')
parser.add_argument('-q', '--query', required=True, help='Query set.')
parser.add_argument('-t', '--sets', required=True, help='Target sets filename.')
parser.add_argument('-a', '--alpha', required=False, type=float, default=0.05, help='Significance threshold.')
parser.add_argument('-c', '--adjust', required=False, action="store_true", help='Adjust for multiple testing (FDR).')
parser.add_argument('-m', '--measure', required=False, default='binomial', help='Dissimilarity index: binomial (default), hypergeometric, chi2 or coverage. chi2 and coverage are NOT YET IMPLEMENTED')
parser.add_argument('-l', '--limit', required=False, type=int, default=0, help='Maximum number of results to report.')
parser.add_argument('-s', '--species', required=True, type=int, help='Taxon id.')

param = parser.parse_args()
################################################################################################

# Connection to Neo4J
try:
    graph = Graph("bolt://localhost:7687", auth=("neo4j", "a"))
except:
    print("Connection to the database failed!\nPlease check your password and try again.\n--help for more information")
    exit()

# LOAD QUERY
text = param.query
query = set()
if isfile(text):
    with open(text) as f:
        content = ' '.join(f.read().split('\n')).split()
        query |= set(content)
else: # parse string
    query |= set(text.split())

# LOAD REFERENCE SETS
sets = json.loads(open(param.sets).read())
#if param.verbose:
#    print('first target sets: ', sets[0:2])

# COMPUTE POPULATION SIZE
q =(f"MATCH (n:GENE) return length(n) ")
population_size = graph.run(q).to_table()
print(f"population size is {population_size}")

# Get keyword associated to the genes query 
kw_query = (f"MATCH (k:Keyword) -[]-> (n:Gene {{taxon_id:{param.species} }})"
            f"WHERE g.id IN ['"+"', '".join(query)+"']"
            f"RETRUN DISTINCT t.id")

kw_query = graph.run(q).to_table()


#EVALUATE SETS
results = []
query_size = len(query)
for kw in kw_query:
    q_genes = (f"MATCH (k:Keyword {{k.id:{kw}}}) -[]-> (n:Gene) " #Genes associated to this keyword in the query
               f"WITH k.id, COLLECT (distinct(g.bnumbers)) AS q_genes"
               f"WHERE g.id IN ['"+"', '".join(query)+"'] "
               f"RETURN q_genes")
    q_genes = graph.run(q_genes).to_table()   

    r_genes = (f"MATCH (k:Keyword {{k.id:{kw}}}) -[]-> (n:Gene) " #Genes associated to this keyword in the query
               f"WITH k.id, COLLECT (distinct(g.bnumbers)) AS q_genes"
               f"RETURN q_genes" )#genes associated to this keyword in reality
    r_genes = graph.run(r_genes).to_table()
    
    common_elements = r_genes.intersection(q_genes)
    if param.measure=='binomial': # binom.cdf(>=success, attempts, proba)
        pvalue = binom.cdf(query_size - len(common_elements), query_size, 1 - float(len(elements))/len(population))
        #prendre le probleme à l'envers
        #quelle est la probabilité qu'il y ait x elements pas en commun, sachant un tirage de z elements et que la probabilité de tiré des elements pas en commun est 1 - proba de tiré des elements en commun
    else:
        print(f'sorry, {param.measure} not (yet) implemented')
        exit(1)
    r = { 'id': s['id'], 'desc': s['desc'], 'common.n':len(common_elements), 'target.n': len(elements), 'p-value': pvalue, 'elements.target': elements, 'elements.common': common_elements }
    results.append( r )
    if param.verbose:
        print(results)
    
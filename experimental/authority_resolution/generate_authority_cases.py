#!/usr/bin/env python3
"""GovKM synthetic authority-fixture generator; no scoring or product execution."""
import argparse
import hashlib
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

VERSION = '0.2.0'
SCHEMA_VERSION = '2.0'
MAX_SEED = 2**63 - 1
PATTERNS = ('AR-01', 'AR-02', 'AR-03', 'AR-04', 'AR-05', 'AR-06')
NAMES = ('Aster', 'Birch', 'Cobalt', 'Delta', 'Elm', 'Fable', 'Garnet', 'Harbor', 'Ibis', 'Juniper', 'Kestrel', 'Lumen')
VALUES = ('Amber', 'Blue', 'Copper', 'Dawn', 'Ember', 'Fern', 'Granite', 'Indigo', 'Jade', 'Lilac', 'Moss', 'Pearl')
LOCATIONS = ('Northgate', 'Westhaven', 'Stonefield', 'Ashport', 'Silverbank', 'Redcliff')


def iso(dt):
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def canonical(obj):
    return (json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def make_case(rng, pattern, idx, seed):
    a, b = rng.sample(VALUES, 2)
    principal, outsider = rng.sample(NAMES, 2)
    project = rng.choice(LOCATIONS)
    base = datetime(2031 + rng.randrange(8), rng.randrange(1, 12), rng.randrange(1, 20), 12, tzinfo=timezone.utc)
    t1, t2, t3, t4 = (base + timedelta(days=d) for d in (0, 3, 9, 15))
    case_id = f'{pattern}-S{seed}-V{idx:04d}'
    grants = [{ 'grant_id':'G1','issuer':'Synthetic Council', 'grantee':principal, 'capability':'approve', 'scope':project, 'valid_from':iso(t1-timedelta(days=1)), 'valid_to':iso(t4+timedelta(days=5)), 'source_ref':'SOURCE-G1'}]
    if pattern == 'AR-03':
        grants.append({'grant_id':'G2','issuer':'Synthetic Council','grantee':outsider,'capability':'approve','scope':project,'valid_from':iso(t1-timedelta(days=1)),'valid_to':iso(t4+timedelta(days=5)),'source_ref':'SOURCE-G2'})
    if pattern == 'AR-06':
        grants = []
    events = []
    def event(eid, when, who, operation, value, grant_ids, target=None, recorded_lag=1):
        events.append({'event_id':eid,'recorded_at':iso(when+timedelta(days=recorded_lag)), 'valid_at':iso(when), 'principal_id':who, 'authority_grant_ids':grant_ids,'operation':operation,'target_id':target,'value':value,'claim':f'{who} {operation} configuration {value} for {project}', 'source_ref':f'SOURCE-{eid}'})
    status='RESOLVED'; operative=[]; required=[]; conflict=[]; historical=[]; supersession=[]
    if pattern == 'AR-01':
        event('E1',t1,principal,'approve',a,['G1'], recorded_lag=14)
        event('E2',t3,principal,'supersede',b,['G1'],target='E1')
        operative=[b]; required=['E2']; historical=['E1']; supersession=['E2']; query=t4
    elif pattern == 'AR-02':
        event('E1',t1,principal,'approve',a,['G1'])
        event('E2',t3,outsider,'approve',b,[])
        operative=[a]; required=['E1']; historical=[]; query=t4
    elif pattern == 'AR-03':
        event('E1',t1,principal,'approve',a,['G1'])
        event('E2',t1,outsider,'approve',b,['G2'])
        status='CONFLICT_UNRESOLVED'; required=['E1','E2']; conflict=['E1','E2']; query=t2
    elif pattern == 'AR-04':
        event('E1',t1,principal,'approve',a,['G1'])
        event('E2',t3,principal,'revoke',a,['G1'],target='E1')
        status='NO_AUTHORITY'; required=['E1','E2']; historical=['E1']; supersession=['E2']; query=t4
    elif pattern == 'AR-05':
        event('E1',t1,principal,'approve',a,['G1'])
        event('E2',t3,principal,'supersede',b,['G1'],target='E1')
        operative=[a]; required=['E1']; query=t2
    else:
        event('E1',t1,principal,'approve',a,[])
        status='NO_AUTHORITY'; required=['E1']; query=t2
    case={'case_id':case_id,'schema_version':SCHEMA_VERSION,'generator_version':VERSION,'pattern':pattern,'variant_index':idx,'query_at':iso(query),'query_text':f'Which configuration governs {project} at {iso(query)}, and what source evidence establishes it?', 'grants':grants,'events':events}
    # Only fictional source inventory. This is input to a memory under test, NEVER scored delivery.
    lines=[f'Case {case_id} / Scope {project}', 'Authority grants:']
    for g in grants: lines.append(f"[{g['source_ref']}] {g['grantee']} may {g['capability']} in {project}, {g['valid_from']} through {g['valid_to']}")
    if not grants: lines.append('No authority grants recorded for this scope.')
    lines.append('Event records:')
    for e in events:
        lines.append(f"[{e['source_ref']}] {e['event_id']} {e['claim']}; effective={e['valid_at']}; recorded={e['recorded_at']}; grants={','.join(e['authority_grant_ids']) or 'NONE'}; target={e['target_id'] or 'NONE'}")
    case['source_inventory_text']='\n'.join(lines)+'\n'
    case['source_coverage']={'grant_registry_complete': True, 'event_log_complete_through':iso(query), 'scope':project, 'registry_source_ref':'SOURCE-REGISTRY', 'coverage_declared_at':iso(query)}
    case['evidence_inventory_role']='unscored_source_input; not delivered_text_after_cut'
    oracle={'case_id':case_id,'expected_resolution':status,'operative_values':operative, 'required_event_ids':required,'conflicting_event_ids':conflict,'historical_event_ids':historical,'supersession_event_ids':supersession, 'required_grant_ids':sorted(set(g for e in events if e['event_id'] in required for g in e['authority_grant_ids'])), 'interpretation_note':'Expected event and authority evidence pertains to delivered text after cut, not retrieval pool or final model answer.'}
    if pattern == 'AR-01':
        oracle['required_event_ids']=['E1','E2']
        oracle['required_grant_ids']=['G1']
    if pattern == 'AR-04':
        oracle['required_event_ids']=['E1','E2']
        oracle['required_grant_ids']=['G1']
    if pattern == 'AR-06':
        oracle['expected_resolution']='NO_AUTHORITY_IF_COVERAGE_PROVEN'
        oracle['required_coverage_refs']=['SOURCE-REGISTRY']
        oracle['incomplete_coverage_resolution']='AUTHORITY_UNRESOLVED'
    if pattern == 'AR-02': oracle['disallowed_event_ids']=['E2']
    if pattern == 'AR-05': oracle['future_event_ids']=['E2']
    oracle['delivery_boundary']='ADEBench measured delivered_text_after_cut only; source_inventory_text never scores'
    oracle['independent_dimensions']=['operative_value','authority_outcome','source_event_delivery']
    oracle['temporal_basis']='valid_at; recorded_at provenance only'
    return case, oracle


def generate(seed, count):
    if count < 1 or count > 10000: raise ValueError('count must be between 1 and 10000')
    if isinstance(seed,bool) or not isinstance(seed,int) or seed < 0 or seed > MAX_SEED: raise ValueError('seed must be an integer between 0 and 2**63-1')
    rng=random.Random(seed)
    cases=[]; oracles=[]
    for pattern in PATTERNS:
        for i in range(1,count+1):
            case, oracle=make_case(rng,pattern,i,seed)
            cases.append(case); oracles.append(oracle)
    return cases, oracles


def write_set(seed,count,outdir):
    out=Path(outdir)
    if out.exists(): raise ValueError('output directory must not exist (no overwrite)')
    if out.is_symlink(): raise ValueError('symlink output not allowed')
    cases, oracles=generate(seed,count)
    out.mkdir(parents=True,exist_ok=True)
    assets={'cases.json':cases,'expected_outcomes.json':oracles,'metadata.json':{'generator_version':VERSION,'schema_version':SCHEMA_VERSION,'seed':seed,'count_per_pattern':count,'patterns':list(PATTERNS),'case_count':len(cases),'classification':'PUBLIC_SYNTHETIC','python_version':__import__('sys').version.split()[0],'prng':'python.random.Random','source_inventory_is_not_measured_delivery':True}}
    hashes={}
    for name,data in assets.items():
        buf=canonical(data)
        (out/name).write_bytes(buf)
        hashes[name]=hashlib.sha256(buf).hexdigest()
    for codefile in (Path(__file__),Path(__file__).parent/'tests'/'test_generator.py'):
        hashes[codefile.relative_to(Path(__file__).parent).as_posix()]=hashlib.sha256(codefile.read_bytes()).hexdigest()
    manifest={'algorithm':'SHA-256','files':hashes,'generator_version':VERSION,'scope':'public fixture files and local generator/test sources only'}
    (out/'sha256_manifest.json').write_bytes(canonical(manifest))
    return hashes


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',type=int,required=True)
    p.add_argument('--count',type=int,required=True,help='N variants PER pattern (total 6*N)')
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--set',choices=('public','holdout'),default='public')
    args=p.parse_args()
    if args.set=='holdout': p.error('private holdout generation and persistence are reserved for ADEBench; no holdout export supported')
    hashes=write_set(args.seed,args.count,args.output_dir)
    print(f'Generated {6*args.count} PUBLIC SYNTHETIC fixtures; SHA-256 cases.json={hashes["cases.json"]}')

if __name__=='__main__': main()

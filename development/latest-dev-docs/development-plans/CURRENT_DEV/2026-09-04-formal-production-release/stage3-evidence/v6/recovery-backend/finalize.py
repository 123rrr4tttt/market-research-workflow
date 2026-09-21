import pathlib,json,hashlib,xml.etree.ElementTree as ET,subprocess,sys
p=pathlib.Path('/Users/wangyiliang/market-research-workflow/development/latest-dev-docs/development-plans/CURRENT_DEV/2026-09-04-formal-production-release/stage3-evidence/v6/recovery-backend')
rows=[]
for log in sorted(p.glob('*.log')):
 t=log.read_text(); x=p/(log.stem+'.xml'); suites=[]
 if x.exists(): suites=[s.attrib for s in ET.parse(x).getroot().iter('testsuite')]
 rows.append({'id':log.stem,'summary_lines':[l for l in t.splitlines() if ' passed' in l or ' failed' in l or ' deselected' in l or ' skipped' in l or ' warnings' in l],'junit_suites':suites,'failures':[{'node':s.attrib,'detail':c.text} for s in ET.parse(x).getroot().iter('testcase') for c in s if c.tag in ('failure','error','skipped')] if x.exists() else []})
(p/'counts-and-failure-inventory.v1.json').write_text(json.dumps(rows,indent=2)+'\n')
for name in ('run','finalize','retry'):
 src=pathlib.Path('/private/tmp/mrw-stage3-v6-backend-recovery-20260907-run.py' if name=='run' else '/private/tmp/mrw-stage3-v6-backend-recovery-retry.py' if name=='retry' else __file__)
 with (p/(name+'.py')).open('x') as f:f.write(src.read_text())
with (p/'dependencies.log').open('x') as f:subprocess.run([sys.executable,'-m','pip','list','--format=json'],stdout=f,stderr=subprocess.STDOUT)
with (p/'clone-final-status.log').open('x') as f:subprocess.run(['git','status','--porcelain'],cwd='/private/tmp/mrw-stage3-v6-backend-recovery-20260907',stdout=f,stderr=subprocess.STDOUT)
import importlib.metadata
with (p/'functorial-kit-provenance.json').open('x') as f:f.write(importlib.metadata.distribution('functorial-kit').read_text('direct_url.json'))
idx=[{'path':str(f),'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in sorted(p.iterdir()) if f.is_file()]
with (p/'hash-index.v1.json').open('x') as f:json.dump(idx,f,indent=2);f.write('\n')
print(json.dumps(rows,indent=2))

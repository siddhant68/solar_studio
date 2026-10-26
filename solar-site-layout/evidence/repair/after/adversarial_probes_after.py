# Copy of reviews/module-01/2026-10-26/adversarial_probes.py for the post-repair observation.
# Changes: the staging writer is now exports._write_staged (was _atomic_write), and the
# controlled interleaving calls exports._build_unlocked, bypassing the new publication
# lock; through the service the lock serializes the two writers, so the barrier inside
# the staging write could never be reached by both. Everything else is unchanged.
import json,tempfile,copy,concurrent.futures,threading,hashlib,pathlib,os
from solar_layout.service import SolarService
from solar_layout.validation import validate_layout_request
from solar_layout.layout import compute_layout
from solar_layout.result import ResultRecords
from solar_layout.verify import verify_records
import solar_layout.exports as ex
BASE=pathlib.Path(os.environ.get('SOLAR_REVIEW_REPO', '/Users/sidhandsome/solar-restart/solar_studio'));OUT=pathlib.Path(os.environ.get('SOLAR_REVIEW_OUT', str(pathlib.Path(__file__).resolve().parent)))
req=json.loads((BASE/'handoffs/module-01/fixtures/rectangle.request.json').read_text())
report={}
with tempfile.TemporaryDirectory(prefix='solar-review-') as temp:
 svc=SolarService(temp);r=svc.generate_layout(request=req);rid=r['result_id']
 # Two real export threads share the normal service, without an injected barrier.
 def export_call(_):
  try:return {'ok':True,'result':svc.export_layout(rid,'csv')}
  except Exception as e:return {'ok':False,'error_type':type(e).__name__,'message':str(e)}
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
  report['natural_parallel_exports']=list(pool.map(export_call,range(24)))
 # Controlled scheduling forces the supported interleaving after both temp files are opened.
 barrier=threading.Barrier(2);original=ex._write_staged
 def controlled(path,writer,binary):
  def gated(handle):
   barrier.wait(timeout=10);writer(handle)
  return original(path,gated,binary)
 ex._write_staged=controlled
 try:
  def unlocked_call(_):
   try:return {'ok':True,'result':ex._build_unlocked(svc.store,rid,'csv')}
   except Exception as e:return {'ok':False,'error_type':type(e).__name__,'message':str(e)}
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:report['controlled_parallel_exports']=list(pool.map(unlocked_call,range(2)))
 finally:ex._write_staged=original
 before=svc.export_layout(rid,'json');before_data=(svc.store.export_root/before['path']).read_bytes()
 p=svc.create_project(req,name='Second project');again=svc.generate_layout(project_id=p['project_id'])
 after=svc.export_layout(rid,'json');after_data=(svc.store.export_root/after['path']).read_bytes()
 report['export_after_new_project_source']={'same_result_id':rid==again['result_id'],'same_payload_digest':r['payload_digest']==again['payload_digest'],'same_path':before['path']==after['path'],'same_bytes':before_data==after_data,'before_sha256':before['sha256'],'after_sha256':after['sha256'],'before_sources':json.loads(before_data).get('project_sources'),'after_sources':json.loads(after_data).get('project_sources')}
 # A consistently corrupted area and ratio can evade verifier checks.
 row=svc.store.get_result_row(rid);summary=copy.deepcopy(row['summary']);q=summary['quantities'];q['gross_site_area_m2']=999999;q['buildable_area_m2']=999999;q['module_ground_coverage_gross']=q['projected_module_area_m2']/999999;q['module_ground_coverage_buildable']=q['projected_module_area_m2']/999999
 report['corrupt_area_verifier']=verify_records(row['request'],summary,svc.store.iter_records(rid,'tables'),svc.store.iter_records(rid,'modules'))
 # Tiny positive keepout around a region containing all tables.
 tiny=copy.deepcopy(req);tiny['exclusions']=[{'id':'CONTAINING','geometry':copy.deepcopy(req['boundary']),'keepout_m':1e-12}]
 val=validate_layout_request(tiny)
 try:
  comp=compute_layout(val);rr=ResultRecords(comp);vr=verify_records(val.normalized,rr.summary,rr.table_records(),rr.module_records());report['tiny_keepout']={'generator_table_count':rr.summary['quantities']['table_count'],'verifier_ok':vr['ok']}
  try:svc.generate_layout(request=tiny);report['tiny_keepout']['service']='success'
  except Exception as e:report['tiny_keepout']['service']={'type':type(e).__name__,'code':getattr(e,'code',None),'message':str(e)}
 except Exception as e:report['tiny_keepout']={'error':str(e),'type':type(e).__name__}
(OUT/'adversarial-results.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'natural_export_failures':sum(not x['ok'] for x in report['natural_parallel_exports']),'controlled_exports':report['controlled_parallel_exports'],'export_mutability':report['export_after_new_project_source'],'corrupt_area_verifier_passed':report['corrupt_area_verifier']['ok'],'tiny_keepout':report['tiny_keepout']},indent=2))

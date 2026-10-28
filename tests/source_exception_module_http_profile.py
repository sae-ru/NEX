"""Joined real HTTP runs with one checked profile registry cohort."""
import hashlib,json
from pathlib import Path
import source_exception_module_http as modules
from source_exception_module_profile import check_profile

def observe(binary,row):
 modules.observe(binary,row)
 plan=json.loads((binary.parent/'plan.json').read_text());file=Path(row['profile_file']);raw,functions=check_profile(file,plan)
 assert raw['build']['host']=='http' and raw['build']['limits_scope']=='common-per-request'
 assert raw['task_execution']['effective']['workers']==4
 roots=[task for task in raw['tasks'] if not task['spawning_invocation_id']]
 disconnected=int('request 1: E_CANCELLED' in row['stderr'])
 assert len(roots)==row['completed_requests']+disconnected,(len(roots),row['completed_requests'],row['stderr'])
 assert functions['app::handle']['calls']==len(roots)
 aborted=sum(task['outcome']=='aborted' for task in roots);cancelled=sum(task['outcome']=='cancelled' for task in roots)
 assert aborted+cancelled<=len(roots)
 if 'E_SOURCE_EXCEPTION' not in row['stderr'] and 'NEX_SOURCE_EXCEPTION ' not in row['stderr'] and not any(key in row['stderr'] for key in ['E_TIMEOUT','E_LIMIT','E_CANCELLED','E_ASSERT']):assert not aborted and not cancelled
 expectation=file.with_name('profile-expectation.json');expectation.write_text(json.dumps({'source_hash':plan['source_hash'],'profiling':plan['profiling']},ensure_ascii=False,indent=2)+'\n')
 row['profile_validation']={'ok':True,'profile_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'expectation_file':str(expectation),'expectation_sha256':hashlib.sha256(expectation.read_bytes()).hexdigest(),'functions':len(functions),'tasks':len(raw['tasks']),'HTTP_roots':len(roots),'aborted_HTTP_roots':aborted,'cancelled_HTTP_roots':cancelled,'disconnected_request':bool(disconnected),'request_ID_correlation_supported':False}

def main():
 state=modules.main(True,False,observe);report=state['report']
 assert all(row['profile_validation']['ok'] for row in report['servers'])
 report.update(ok=True,private_module_HTTP_profiling=True,profiled_native_images=len(report['images']),profiled_server_runs=len(report['servers']),HTTP_request_ID_profile_correlation=False,public_profile_CLI=False)
 state['save']();print(json.dumps({'ok':True,'images':len(report['images']),'profiled_servers':len(report['servers']),'requests':len(report['requests'])}))

if __name__=='__main__':main()

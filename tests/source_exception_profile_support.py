"""Shared native flags and exact private profile host identity for test drivers."""
import json

FLAGS=['-DNEX_PROFILE_ENABLED','-DNEX_TASK_PROFILE_ENABLED','-DNEX_SHARED_PROFILE_RUNTIME',
       *['-D'+name for name in ['TRACY_ENABLE','TRACY_ON_DEMAND','TRACY_DELAYED_INIT','TRACY_MANUAL_LIFETIME','TRACY_ONLY_LOCALHOST','TRACY_NO_BROADCAST','TRACY_NO_CODE_TRANSFER','TRACY_NO_CALLSTACK','TRACY_NO_SYSTEM_TRACING','TRACY_NO_SAMPLING','TRACY_NO_CRASH_HANDLER','TRACY_NO_FRAME_IMAGE']]]
EXTRA_RUNTIME=['nex_task_profile.cpp','nex_profile.cpp','third_party/tracy/public/TracyClient.cpp']

def host_identity(plan):
 registries=[row['profiling']['registry_accessor'] for _,row in sorted(plan['components'].items())]
 code=['#include "nex_task_profile_site.h"','#include <dlfcn.h>']
 code+=['static const nexrt::TaskProfileCodeRegistry *private_profile_registry(const char *name){using Accessor=const nexrt::TaskProfileCodeRegistry *(*)();auto function=reinterpret_cast<Accessor>(dlsym(RTLD_DEFAULT,name));return function?function():nullptr;}']
 code+=['extern "C" void nex_task_profile_prepare_application_v1(){const nexrt::TaskProfileCodeRegistry *registries[]={'+','.join('private_profile_registry('+json.dumps(name)+')' for name in registries)+'};nex_task_profile_prepare_registries(registries,'+str(len(registries))+');}']
 identity={'schema':'nex.private-module-profile-build/1','archived':False,'language':'0.25-prototype','host':plan['host'],'limits_scope':'common-per-request' if plan['host']=='http' else 'root-application','source_hash':plan['source_hash'],'profiling':plan['profiling']}
 code+=['extern "C" const char *nex_profile_build_info(){return '+json.dumps(json.dumps(identity,ensure_ascii=True,separators=(',',':')))+';}']
 return '\n'.join(code)+'\n'
